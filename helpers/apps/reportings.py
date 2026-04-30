import logging
import uuid
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from typing import Iterable, Optional

import pytz
import sentry_sdk
from django.contrib.gis.geos import GeometryCollection, Point
from django.db.models import ExpressionWrapper, Func, OuterRef, Subquery
from django.db.models.fields import FloatField
from django.db.models.functions import Cos, Radians
from django.db.models.signals import post_save
from django.utils import timezone
from django.utils.timezone import now
from django_bulk_update.helper import bulk_update
from rest_framework_json_api import serializers
from simple_history.utils import bulk_create_with_history
from zappa.asynchronous import task

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Company, Firm
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import (
    RecordMenu,
    Reporting,
    ReportingBulkEdit,
    ReportingFile,
    ReportingInReporting,
    ReportingRelation,
)
from apps.service_orders.models import ServiceOrderActionStatusSpecs
from apps.users.models import User
from apps.work_plans.models import Job
from helpers.apps.json_logic import apply_json_logic
from helpers.dates import date_tz
from helpers.forms import clean_form_data
from helpers.histories import bulk_update_with_history
from helpers.km_converter import get_road_coordinates
from helpers.signals import auto_add_job_number, auto_add_number
from helpers.strings import get_obj_from_path, keys_to_snake_case, to_snake_case


def reportings_from_inspection(
    job_instance: Job, inspection: Reporting, user: User, menu: RecordMenu
):
    """
    Creates new Reportings in a Job based on therapies defined in an inspection Reporting.

    This function processes therapy data from an inspection Reporting to create corresponding
    treatment Reportings, maintaining relationships and copying relevant data.

    Args:
        job_instance (Job): The Job instance to add the new Reportings to
        inspection (Reporting): The inspection Reporting containing therapy data
        user (User): User creating the Reportings
        menu (RecordMenu): RecordMenu instance to associate with new Reportings

    Raises:
        ValidationError: If:
            - Inspection has invalid therapy data
            - Therapy has invalid OccurrenceType
            - ServiceOrderActionStatus not found in Company configuration

    Notes:
        - Only processes valid therapy entries from inspection form_data
        - Copies relevant fields from inspection to new Reportings
        - Sets proper ApprovalStep and ServiceOrderActionStatus based on Company config
        - Copies treatment images to new Reportings
        - Uses bulk operations for creation
        - Sets Job's inspection and parent_inventory references
    """

    FIXED_FIELDS = [
        "km",
        "end_km",
        "project_km",
        "project_end_km",
        "direction",
        "lane",
        "occurrence_type",
    ]
    company = inspection.company

    for therapy in inspection.form_data.get("therapy", [{}]):
        if not all(k in therapy.keys() for k in ["occurrence_type", "description"]):
            raise serializers.ValidationError(
                "kartado.error.job.invalid_inspection_therapies"
            )

    try:
        in_job_status = ServiceOrderActionStatusSpecs.objects.get(
            company=company, order=2
        ).status
    except Exception:
        raise serializers.ValidationError("kartado.error.job.status_not_found")
    therapys = []
    for therapy in inspection.form_data["therapy"]:
        try:
            occurrence_type = OccurrenceType.objects.get(pk=therapy["occurrence_type"])
            if occurrence_type.occurrence_kind == "2":
                raise Exception()
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.job.invalid_inspection_therapy_occurrence_type"
            )

        treatment_images = []
        if "treatment_images" in therapy.keys():
            for image_pk in therapy["treatment_images"]:
                try:
                    reporting_file = ReportingFile.objects.get(pk=image_pk)
                except ReportingFile.DoesNotExist:
                    sentry_sdk.capture_message(
                        "ReportingFile with {} uuid does not exist in the database".format(
                            str(image_pk)
                        ),
                        "warning",
                    )
                else:
                    treatment_images.append(reporting_file)

        therapys.append(
            {
                "occ_type": occurrence_type,
                "description": therapy["description"],
                "treatment_images": treatment_images,
                "km": therapy.get("km", inspection.km),
                "end_km": therapy.get("end_km", inspection.end_km),
                "project_km": therapy.get("project_km", inspection.project_km),
                "project_end_km": therapy.get(
                    "project_end_km", inspection.project_end_km
                ),
                "direction": therapy.get("direction", inspection.direction),
                "lane": therapy.get("lane", inspection.lane),
                "variable_fields": {
                    key: value
                    for (key, value) in therapy.items()
                    if key not in FIXED_FIELDS
                },
            }
        )
    job_instance.inspection = inspection
    job_instance.parent_inventory = inspection.parent
    reporting_list = []
    image_list = []

    for therapy in therapys:
        appointment = deepcopy(inspection)
        appointment.parent = inspection.parent
        appointment.pk = uuid.uuid4()
        appointment.number = None
        appointment.occurrence_type = therapy["occ_type"]
        appointment.firm = job_instance.firm
        appointment.status = in_job_status
        appointment.created_by = user
        appointment.job = job_instance
        appointment.found_at = timezone.now()
        appointment.created_at = timezone.now()
        appointment.executed_at = None
        appointment.due_at = None
        appointment.km = therapy["km"]
        appointment.end_km = therapy["end_km"]
        appointment.project_km = therapy["project_km"]
        appointment.project_end_km = therapy["project_end_km"]
        appointment.direction = therapy["direction"]
        appointment.lane = therapy["lane"]
        appointment.form_data.update(therapy["variable_fields"])
        appointment.menu = menu

        # "Copy" signals here to avoid N+1
        auto_add_number(appointment, "RP_name_format")
        appointment.point, appointment.road = get_road_coordinates(
            appointment.road_name,
            appointment.km,
            appointment.direction,
            appointment.company,
        ) or (Point(0, 0), None)
        if not appointment.manual_geometry:
            appointment.geometry = GeometryCollection(appointment.point)
        if appointment.road:
            appointment.lot = apply_json_logic(
                appointment.road.lot_logic, {"data": {"km": appointment.km}}
            )
        altimetry_enable = company.metadata.get("altimetry_enable", False)
        if altimetry_enable:
            try:
                appointment.set_altimetry()
            except Exception:
                pass

        reporting_list.append(appointment)

        for treatment_image in therapy["treatment_images"]:
            image = deepcopy(treatment_image)
            image.pk = uuid.uuid4()
            image.reporting = appointment
            image_list.append(image)

    # And use bulk_create

    bulk_create_with_history(reporting_list, Reporting)
    bulk_create_with_history(image_list, ReportingFile)

    job_instance.reportings.add(*reporting_list)


def refine_direction(direction_number_reference, company):
    default_direction_value = get_obj_from_path(
        company.custom_options,
        "reporting__fields__direction__defaultvalue",
    )
    possible_direction_path = "reporting__fields__direction__selectoptions__options"
    possible_directions = get_obj_from_path(
        company.custom_options, possible_direction_path
    )
    direction_to_value = {
        option["name"]: option["value"]
        for option in possible_directions
        if "value" in option and "name" in option
    }

    if direction_number_reference in direction_to_value:
        return direction_to_value[direction_number_reference]
    elif default_direction_value:
        return default_direction_value
    else:
        return None


def get_lane(lane_reference, company):
    possible_lane_path = "reporting__fields__lane__selectoptions__options"
    lanes = get_obj_from_path(company.custom_options, possible_lane_path)

    for item in lanes:
        if "value" in item and "name" in item:
            if item["value"] == lane_reference:
                return item["name"]
    return ""


def get_occurrence_kind(occurrence_type_number_reference, company):
    possible_lane_path = "reporting__fields__occurrence_kind__selectoptions__options"
    occurrence_types = get_obj_from_path(company.custom_options, possible_lane_path)

    for item in occurrence_types:
        if "value" in item and "name" in item:
            if item["value"] == occurrence_type_number_reference:
                return item["name"]
    return ""


def return_select_value(key, reporting, reference_values):
    occurrence_type = reporting.occurrence_type
    snake_case_key = to_snake_case(key)
    if snake_case_key in reporting.form_data:
        value = reporting.form_data[snake_case_key]
    else:
        return ""

    # If falsy return empty
    if not value:
        return ""

    form_fields = get_obj_from_path(occurrence_type.form_fields, "fields")
    field = ""
    for item in form_fields:
        if item.get("apiName") == key:
            field = item
            break
    if field == "":
        return ""
    data_type = field.get("dataType")
    if data_type in ["select", "selectMultiple"]:
        first_path = "selectoptions"
        select_options = get_obj_from_path(field, first_path)
        if "reference" not in select_options:
            second_path = "options"
            field_to_options = {
                option["value"]: option["name"]
                for option in get_obj_from_path(select_options, second_path)
            }
        else:
            field_to_options = reference_values
        if data_type == "selectMultiple" or isinstance(value, list):
            if not isinstance(value, list):
                value = [value]
            return ", ".join(
                [field_to_options.get(a, "") or "" for a in value if a is not None]
            )
        else:
            return field_to_options.get(value)
    else:
        return ""


def return_select_value_array(inner_item, export_key, value, reference_values):
    # If falsy return empty
    if not value:
        return ""

    inner_fields = get_obj_from_path(inner_item, "innerFields")
    field = ""
    for item in inner_fields:
        if item.get("apiName") == export_key:
            field = item
            break
    if field == "":
        return ""
    data_type = field.get("dataType")
    if data_type in ["select", "selectMultiple"]:
        first_path = "selectoptions"
        select_options = get_obj_from_path(field, first_path)
        if "reference" not in select_options:
            second_path = "options"
            field_to_options = {
                option["value"]: option["name"]
                for option in get_obj_from_path(select_options, second_path)
            }
        else:
            field_to_options = reference_values
        if data_type == "selectMultiple" or isinstance(value, list):
            if not isinstance(value, list):
                value = [value]
            return ", ".join(
                [field_to_options.get(a, "") or "" for a in value if a is not None]
            )
        else:
            return field_to_options.get(value)
    else:
        return ""


def return_array_values(item, reporting, reference_values):
    occurrence_type = reporting.occurrence_type

    key = item.get("key", "")
    max_repetitions = item.get("maxRepetitions", 5)
    fields_to_export = item.get("fields", [])
    snake_case_key = to_snake_case(key)

    return_values = {
        f"{key}{str(i)}{export_field.get('field')}": ""
        for i in range(0, max_repetitions)
        for export_field in fields_to_export
    }
    if snake_case_key in reporting.form_data:
        array_value = reporting.form_data[snake_case_key]
    else:
        return return_values
    form_fields = get_obj_from_path(occurrence_type.form_fields, "fields")
    field = ""
    for item in form_fields:
        if item.get("apiName") == key:
            field = item
            break
    if field == "":
        return return_values
    for i in range(0, max_repetitions):
        for export_field in fields_to_export:
            is_image = export_field.get("isImage", False)
            if is_image:
                continue
            is_select = export_field.get("isSelect", False)
            export_key = export_field.get("field")
            snake_case_field = to_snake_case(export_key)
            if not is_select:
                try:
                    value = array_value[i][snake_case_field]
                except (KeyError, IndexError):
                    value = ""
                finally:
                    return_values.update({f"{key}{str(i)}{export_key}": value})
            else:
                try:
                    value = array_value[i][snake_case_field]
                except (KeyError, IndexError):
                    value = ""
                else:
                    value = return_select_value_array(
                        field, export_key, value, reference_values
                    )
                finally:
                    return_values.update({f"{key}{str(i)}{export_key}": value})

    return return_values


def create_recuperation_reportings_jobs(
    company: Company,
    user: User,
    menu: RecordMenu,
    inspection_data: dict,
    job_data: dict,
):
    """
    Creates recuperation Reportings and Jobs from inspection Reportings, maintaining relationships between them.

    This function creates new Jobs and recuperation Reportings based on therapies defined in inspection Reportings.
    It handles bulk creation of all related objects and their relationships.

    Args:
        company (Company): Company instance for metadata and validation
        user (User): User creating the recuperations
        menu (RecordMenu): RecordMenu instance to associate with new Reportings
        inspection_data (dict): Dictionary mapping inspection UUIDs to Job titles
        job_data (dict): Dictionary containing Job creation data with fields:
            - firm (UUID): Firm ID for the Job
            - start_date (str): Job start date (YYYY-MM-DDThh:mm:ss format)
            - end_date (str, optional): Job end date
            - worker (UUID): Worker user ID
            - watcher_users (List[UUID], optional): List of User IDs to access the Job
            - watcher_firms (List[UUID], optional): List of Firm IDs to access the Job
            - watcher_subcompanies (List[UUID], optional): List of SubCompany IDs to access the Job

    Raises:
        ValidationError: If:
            - Required relations not found
            - Invalid inspection data
            - ServiceOrderActionStatus not found
            - ApprovalStep not found

    Notes:
        - Creates Jobs for each inspection with valid therapies
        - Creates recuperation Reportings for each therapy
        - Sets up parent-child relationships via ReportingInReporting
        - Copies treatment ReportingFiles to new Reportings
        - Uses bulk operations for all creations and updates
        - Sets "created_recuperations_with_relation" as True in original Reportings
    """

    # Get basic components
    inspection_occurrence_kind = get_obj_from_path(
        company.metadata, "inspection_occurrence_kind"
    )
    if isinstance(inspection_occurrence_kind, str):
        inspection_occurrence_kind = [inspection_occurrence_kind]
    reporting_relation_metadata = get_obj_from_path(
        company.metadata, "recuperation_reporting_relation"
    )
    try:
        reporting_relation = ReportingRelation.objects.get(
            pk=reporting_relation_metadata
        )
    except Exception:
        raise serializers.ValidationError("kartado.error.reporting_relation_not_found")

    try:
        approval_step = ApprovalStep.objects.filter(
            approval_flow__company=company,
            approval_flow__target_model="reportings.Reporting",
            previous_steps__isnull=True,
        ).first()
    except Exception:
        approval_step = None

    try:
        in_job_status = ServiceOrderActionStatusSpecs.objects.get(
            company=company, order=2
        ).status
    except Exception:
        raise serializers.ValidationError("kartado.error.job.status_not_found")

    # Initialize base variables
    updated_reps = []
    found_at = now()

    # Common variables for all items
    firm = Firm.objects.get(uuid=job_data["firm"])
    job_kwargs = {
        "company": company,
        "start_date": datetime.strptime(
            job_data["start_date"].split(".")[0],
            "%Y-%m-%dT%H:%M:%S",
        ).replace(tzinfo=pytz.UTC),
        "worker": User.objects.get(uuid=job_data["worker"]),
        "firm": firm,
        "created_by": user,
    }
    if job_data["end_date"]:
        job_kwargs.update(
            {
                "end_date": datetime.strptime(
                    job_data["end_date"].split(".")[0],
                    "%Y-%m-%dT%H:%M:%S",
                ).replace(tzinfo=pytz.UTC),
            }
        )
    # Get Reporting and OccurrenceType list
    rep_list = list(inspection_data.keys())
    rep_qs = Reporting.objects.filter(uuid__in=rep_list).prefetch_related(
        "occurrence_type", "company", "parent"
    )
    occ_list = list(
        OccurrenceType.objects.filter(company=company).only(
            "uuid", "occurrence_kind", "deadline", "form_fields"
        )
    )
    # Create new items

    created_jobs = []
    new_reporting_files = []
    new_reporting_in_reportings = []
    new_reps = []
    new_jobs = []
    for item in rep_qs:
        job_uuid = uuid.uuid4()
        create_job = False

        if item.occurrence_type.occurrence_kind not in inspection_occurrence_kind:
            raise serializers.ValidationError(
                "kartado.error.reporting.reporting_not_inspection"
            )
        therapy = item.form_data.get("therapy", [])
        if therapy:
            occurrence_type_uuid_list = [a.get("occurrence_type", "") for a in therapy]
            if all(occurrence_type_uuid_list):
                create_job = True
                reporting_count = len(therapy)
                for item_therapy in therapy:
                    treatment_images = []
                    if "treatment_images" in item_therapy:
                        for image_pk in item_therapy["treatment_images"]:
                            try:
                                reporting_file = ReportingFile.objects.get(pk=image_pk)
                            except ReportingFile.DoesNotExist:
                                sentry_sdk.capture_message(
                                    "ReportingFile with {} uuid does not exist in the database".format(
                                        str(image_pk)
                                    ),
                                    "warning",
                                )
                            else:
                                treatment_images.append(reporting_file)
                    occ = next(
                        obj
                        for obj in occ_list
                        if str(obj.pk) == item_therapy["occurrence_type"]
                    )
                    if occ.deadline:
                        due_at = found_at + occ.deadline
                    else:
                        due_at = None
                    new_rep = deepcopy(item)
                    new_rep.pk = uuid.uuid4()
                    new_rep.occurrence_type = occ
                    new_rep.status = in_job_status
                    new_rep.firm = firm
                    new_rep.number = None
                    new_rep.editable = True
                    new_rep.form_data = clean_form_data(new_rep.form_data, occ)
                    if "description" in item_therapy:
                        new_rep.form_data["description"] = item_therapy["description"]
                    new_rep.created_by = user
                    new_rep.executed_at = None
                    new_rep.found_at = found_at
                    new_rep.due_at = due_at
                    new_rep.job_id = job_uuid
                    new_rep.menu = menu
                    new_rep.approval_step = approval_step
                    new_rep.active_inspection = None
                    new_rep.created_recuperations_with_relation = None
                    auto_add_number(new_rep, "RP_name_format")

                    for treatment_image in treatment_images:
                        image = deepcopy(treatment_image)
                        image.uuid = None
                        image.reporting = new_rep
                        new_reporting_files.append(image)

                    new_reps.append(new_rep)
                    new_reporting_in_reportings.append(
                        ReportingInReporting(
                            parent=item,
                            child=new_rep,
                            reporting_relation=reporting_relation,
                        )
                    )
                item.created_recuperations_with_relation = True
                updated_reps.append(item)
            else:
                raise serializers.ValidationError(
                    "kartado.error.reporting.reporting_not_inspection"
                )
        else:
            raise serializers.ValidationError(
                "kartado.error.reporting.reporting_not_inspection"
            )

        if create_job:

            job_kwargs.update(
                {
                    "number": auto_add_job_number(company),
                    "title": f"{inspection_data.get(str(item.uuid))} - {item.parent.number}",
                    "reporting_count": reporting_count,
                    "inspection": item,
                    "parent_inventory": item.parent,
                    "uuid": job_uuid,
                }
            )

            new_jobs.append(Job(**job_kwargs))
            created_jobs.append(job_uuid)

    bulk_create_with_history(new_jobs, Job, default_user=user)
    bulk_create_with_history(new_reps, Reporting, default_user=user)
    bulk_create_with_history(
        new_reporting_in_reportings, ReportingInReporting, default_user=user
    )
    bulk_create_with_history(new_reporting_files, ReportingFile, default_user=user)
    bulk_update_with_history(
        updated_reps, Reporting, use_django_bulk=True, user=user, batch_size=250
    )

    if job_data["watcher_users"]:
        UserThrough = Job.watcher_users.through
        UserThrough.objects.bulk_create(
            [
                UserThrough(job_id=job_id, user_id=user_id)
                for job_id in created_jobs
                for user_id in job_data["watcher_users"]
            ]
        )
    if job_data["watcher_subcompanies"]:
        SubcompanyThrough = Job.watcher_subcompanies.through
        SubcompanyThrough.objects.bulk_create(
            [
                SubcompanyThrough(job_id=job_id, subcompany_id=subcompany_id)
                for job_id in created_jobs
                for subcompany_id in job_data["watcher_subcompanies"]
            ]
        )
    if job_data["watcher_firms"]:
        FirmThrough = Job.watcher_firms.through
        FirmThrough.objects.bulk_create(
            [
                FirmThrough(job_id=job_id, firm_id=firm_id)
                for job_id in created_jobs
                for firm_id in job_data["watcher_firms"]
            ]
        )


@task
def bulk_edit(reporting_bulk_edit_pk):
    instance = ReportingBulkEdit.objects.get(pk=reporting_bulk_edit_pk)
    updated_by = instance.updated_by
    request_data = instance.edit_data
    reportings = instance.reportings.all()

    # Disable the update_reporting_inventory_candidates signal during bulk edit
    # since we'll update inventory candidates in bulk at the end
    from apps.reportings.signals import update_reporting_inventory_candidates_on_save

    post_save.disconnect(
        update_reporting_inventory_candidates_on_save, sender=Reporting
    )

    try:
        for reporting in reportings:
            found_at = reporting.found_at
            if "occurrence_type" in request_data:
                occurrence_type = OccurrenceType.objects.filter(
                    pk=request_data["occurrence_type"]["id"]
                ).first()
            else:
                occurrence_type = reporting.occurrence_type

            for field in request_data.keys():
                try:
                    Reporting._meta.get_field(field)
                except Exception:
                    pass
                else:
                    if (
                        field == "end_km"
                        and request_data[field] is not None
                        and request_data[field] != reporting.end_km
                    ):
                        reporting.end_km_manually_specified = True
                        reporting.end_km = request_data[field]
                    elif (
                        field == "project_end_km"
                        and request_data[field] is not None
                        and request_data[field] != reporting.project_end_km
                    ):
                        reporting.project_end_km_manually_specified = True
                        reporting.project_end_km = request_data[field]
                    elif (
                        field == "due_at"
                        and request_data[field] is not None
                        and request_data[field] != reporting.due_at
                    ):
                        reporting.due_at_manually_specified = True
                        reporting.due_at = date_tz(request_data[field])
                    elif field == "found_at":
                        found_at = date_tz(request_data[field])
                        reporting.found_at = found_at
                    elif field == "executed_at":
                        reporting.executed_at = date_tz(request_data[field])
                    elif field == "form_data":
                        fields = occurrence_type.form_fields["fields"]
                        new_form_data = {}
                        for key, value in dict(request_data["form_data"]).items():
                            try:
                                form_field = [
                                    x
                                    for x in fields
                                    if (
                                        "api_name" in x
                                        and to_snake_case(x["api_name"]) == key
                                    )
                                    or (
                                        "apiName" in x
                                        and to_snake_case(x["apiName"]) == key
                                    )
                                ][0]
                            except Exception:
                                pass
                            else:
                                if "__behavior" in key:
                                    continue
                                form_field = keys_to_snake_case(form_field)
                                data_type = (
                                    to_snake_case(form_field["data_type"])
                                    if "data_type" in form_field
                                    else ""
                                )
                                if data_type and data_type != "array_of_objects":
                                    if data_type in ["text_area", "string"]:
                                        behavior = key + "__behavior"
                                        if behavior in request_data["form_data"]:
                                            if (
                                                request_data["form_data"][behavior]
                                                == "replace"
                                            ):
                                                new_form_data[key] = value
                                            elif (
                                                request_data["form_data"][behavior]
                                                == "add"
                                            ):
                                                if key in reporting.form_data:
                                                    new_form_data[key] = (
                                                        reporting.form_data[key]
                                                        + " "
                                                        + value
                                                    )
                                                else:
                                                    new_form_data[key] = value

                                    else:
                                        new_form_data[key] = value
                        # update form_data
                        reporting.form_data.update(new_form_data)

                    elif field == "occurrence_type":
                        reporting.occurrence_type = occurrence_type
                    else:
                        # ForeignKey
                        if Reporting._meta.get_field(field).many_to_one:
                            new_field = field + "_id"
                            field_value = request_data[field]["id"]
                        else:
                            new_field = field
                            field_value = request_data[field]

                        try:
                            setattr(reporting, new_field, field_value)
                        except Exception as e:
                            logging.warning("Exception setting model fields", str(e))

            if "clear_due_at" in request_data and request_data["clear_due_at"]:
                reporting.due_at = None
            if (
                "clear_executed_at" in request_data
                and request_data["clear_executed_at"]
            ):
                reporting.executed_at = None
            if ("found_at" in request_data or "occurrence_type" in request_data) and (
                not reporting.due_at_manually_specified
            ):
                if occurrence_type.deadline:
                    reporting.due_at = found_at + occurrence_type.deadline
                else:
                    reporting.due_at = None

            # save reporting to call signals and save method
            reporting.save()
            if updated_by:
                hist = reporting.history.first()
                if hist and not hist.history_user:
                    hist.history_user = updated_by
                    hist.save()

        # Update inventory candidates for all edited reportings
        # Get company from first reporting (all reportings should belong to the same company)
        if reportings.exists():
            company = reportings.first().company
            update_reporting_inventory_candidates(reportings, company)
            update_reporting_inventory_candidates_from_inventories(reportings, company)
    finally:
        # Reconnect the signal after bulk edit is complete
        post_save.connect(
            update_reporting_inventory_candidates_on_save, sender=Reporting
        )


def get_inspections(
    reportings: Iterable[Reporting], company: Company
) -> Iterable[Reporting]:
    inspections = Reporting.objects.none()
    if not reportings or not company:
        return inspections

    reporting_relation_metadata = get_obj_from_path(
        company.metadata, "recuperation_reporting_relation"
    )

    inspection_occurrence_kinds = get_obj_from_path(
        company.metadata, "inspection_occurrence_kind"
    )
    if isinstance(inspection_occurrence_kinds, str):
        inspection_occurrence_kinds = [inspection_occurrence_kinds]
    if not inspection_occurrence_kinds or not reporting_relation_metadata:
        return inspections

    rr_qs = ReportingInReporting.objects.filter(
        child__in=reportings,
        parent__occurrence_type__occurrence_kind__in=inspection_occurrence_kinds,
        reporting_relation__uuid=reporting_relation_metadata,
    )
    inspections = Reporting.objects.filter(
        uuid__in=rr_qs.values_list("parent", flat=True)
    )

    return inspections


def update_created_recuperations_with_relation(
    inspections: Iterable[Reporting], company: Company
):
    if not inspections or not company:
        return

    reporting_relation_metadata = get_obj_from_path(
        company.metadata, "recuperation_reporting_relation"
    )

    inspection_occurrence_kinds = get_obj_from_path(
        company.metadata, "inspection_occurrence_kind"
    )
    if isinstance(inspection_occurrence_kinds, str):
        inspection_occurrence_kinds = [inspection_occurrence_kinds]
    if not inspection_occurrence_kinds or not reporting_relation_metadata:
        return

    inspections_to_update = []
    recuperation_relationships = ReportingInReporting.objects.filter(
        parent__in=inspections,
        parent__occurrence_type__occurrence_kind__in=inspection_occurrence_kinds,
        reporting_relation__uuid=reporting_relation_metadata,
    )
    relationships_by_parent = defaultdict(list)
    for relationship in recuperation_relationships:
        relationships_by_parent[str(relationship.parent.uuid)].append(relationship)

    for inspection in inspections:
        if len(relationships_by_parent[str(inspection.uuid)]) == 0:
            inspection.created_recuperations_with_relation = None
            inspections_to_update.append(inspection)

    if inspections_to_update:
        bulk_update(
            inspections_to_update,
            batch_size=1000,
            update_fields=["created_recuperations_with_relation"],
        )


class MakeArray(Func):
    # This is a workaround for array agregation limitations of django over postgres
    # Can be removed when django is updated to support ArraySubquery
    # Taken from https://forum.djangoproject.com/t/fetch-similar-django-objects-in-one-query-if-the-objects-have-no-direct-relation/10886/4
    function = "ARRAY"


class ST_X(Func):
    function = "ST_X"
    output_field = FloatField()


class ST_Y(Func):
    function = "ST_Y"
    output_field = FloatField()


DEFAULT_RADIUS = 100.0


def get_compatible_inventory_classes_for_reporting(
    reporting_class_uuid: str, reporting_kind: str, mapping: dict
) -> list:
    """
    Given a reporting (apontamento) class UUID and occurrence_kind, returns the list
    of compatible inventory class UUIDs based on the mapping.

    The mapping format is:
    {
        inv_class_uuid: {
            "occurrence_types": [apt_class_uuid, ...],
            "occurrence_kinds": ["1", "2", ...]
        }
    }

    A reporting is compatible with an inventory class if:
    - Its occurrence_type is in the "occurrence_types" list, OR
    - Its occurrence_kind is in the "occurrence_kinds" list

    Args:
        reporting_class_uuid: UUID of the reporting's occurrence_type
        reporting_kind: The occurrence_kind of the reporting's occurrence_type
        mapping: Dict mapping inventory class UUIDs to compatibility config

    Returns:
        List of compatible inventory class UUIDs, or None if no mapping exists
        (None means fallback to previous behavior - no class filter)
    """
    if not mapping:
        return None

    if not reporting_class_uuid and not reporting_kind:
        return None

    compatible = []
    reporting_class_str = str(reporting_class_uuid) if reporting_class_uuid else None
    reporting_kind_str = str(reporting_kind) if reporting_kind else None

    for inv_class, config in mapping.items():
        # Handle new format: config is a dict with occurrence_types and occurrence_kinds
        if not isinstance(config, dict):
            continue

        occurrence_types = config.get("occurrence_types", [])
        occurrence_kinds = config.get("occurrence_kinds", [])

        # Convert to string lists for comparison
        occurrence_types_str = [str(c) for c in occurrence_types]
        occurrence_kinds_str = [str(k) for k in occurrence_kinds]

        # OR logic: match if class is in occurrence_types OR kind is in occurrence_kinds
        class_matches = (
            reporting_class_str and reporting_class_str in occurrence_types_str
        )
        kind_matches = reporting_kind_str and reporting_kind_str in occurrence_kinds_str

        if class_matches or kind_matches:
            compatible.append(inv_class)

    if not compatible:
        return None  # No mapping for this class/kind - fallback

    return compatible


def get_compatible_reporting_criteria_for_inventory(
    inventory_class_uuid: str, mapping: dict
) -> dict:
    """
    Given an inventory class UUID, returns the compatibility criteria
    (occurrence_types and occurrence_kinds) for reportings.

    The mapping format is:
    {
        inv_class_uuid: {
            "occurrence_types": [apt_class_uuid, ...],
            "occurrence_kinds": ["1", "2", ...]
        }
    }

    Args:
        inventory_class_uuid: UUID of the inventory's occurrence_type
        mapping: Dict mapping inventory class UUIDs to compatibility config

    Returns:
        Dict with "occurrence_types" and "occurrence_kinds" lists, or None if no mapping exists
        (None means fallback to previous behavior - no class filter)
    """
    if not mapping or not inventory_class_uuid:
        return None

    inventory_class_str = str(inventory_class_uuid)
    config = mapping.get(inventory_class_str)

    if not config or not isinstance(config, dict):
        return None  # No mapping for this class - fallback

    occurrence_types = config.get("occurrence_types", [])
    occurrence_kinds = config.get("occurrence_kinds", [])

    # Return None if both lists are empty (no criteria defined)
    if not occurrence_types and not occurrence_kinds:
        return None

    return {
        "occurrence_types": [str(c) for c in occurrence_types],
        "occurrence_kinds": [str(k) for k in occurrence_kinds],
    }


def get_candidate_inventory_subquery(company: Company) -> Subquery:
    """
    Returns a subquery that finds inventory candidates for a reporting (apontamento)
    based on geographic criteria (road, km, direction, lane, coordinates).

    Note: Class-based filtering is applied separately in the main function
    using the inventory_candidates_class_mapping from company.metadata.
    """
    m_radius = get_obj_from_path(company.metadata, "inventory_radius") or DEFAULT_RADIUS
    km_radius = float(m_radius) * 0.001

    lat_delta = m_radius / 111320.0

    has_roads = company.company_roads.exists()
    subquery = (
        Reporting.objects.filter(
            company=company,
        )
        .filter(
            direction=OuterRef("direction"),
            lane=OuterRef("lane"),
            road_name=OuterRef("road_name"),
        )
        .filter(
            km__gt=OuterRef("km") - km_radius,
            km__lt=OuterRef("km") + km_radius,
        )
        .filter(
            occurrence_type__occurrence_kind="2",
        )
    )

    if not has_roads:
        subquery = subquery.annotate(lat1=ST_Y("point"), lon1=ST_X("point"),).filter(
            lat1__gte=OuterRef("lat0") - lat_delta,
            lat1__lte=OuterRef("lat0") + lat_delta,
            lon1__gte=OuterRef("lon0") - OuterRef("lon_delta"),
            lon1__lte=OuterRef("lon0") + OuterRef("lon_delta"),
        )

    return Subquery(subquery.values("uuid"))


def get_bond_occurrence_types(company: Company) -> Optional[set]:
    """
    Returns the set of OccurrenceType UUIDs that should receive inventory suggestions.

    A class is considered mapped if its UUID appears in occurrence_types OR if its
    occurrence_kind appears in occurrence_kinds in any entry of inventory_candidates_class_mapping.

    Returns None when no filtering should be applied (V0 behavior):
    - disable_inventory_class_filter is set
    - inventory_candidates_class_mapping is absent or empty
    """
    if get_obj_from_path(company.metadata, "disable_inventory_class_filter"):
        return None

    class_mapping = (
        get_obj_from_path(company.metadata, "inventory_candidates_class_mapping") or {}
    )
    if not class_mapping:
        return None

    bond_uuids = set()
    mapped_kinds = set()

    for inv_config in class_mapping.values():
        if not isinstance(inv_config, dict):
            continue
        for ot in inv_config.get("occurrence_types", []):
            bond_uuids.add(str(ot))
        for kind in inv_config.get("occurrence_kinds", []):
            mapped_kinds.add(str(kind))

    if mapped_kinds:
        kind_uuids = OccurrenceType.objects.filter(
            company=company, occurrence_kind__in=mapped_kinds
        ).values_list("uuid", flat=True)
        bond_uuids.update(str(u) for u in kind_uuids)

    return bond_uuids


def update_reporting_inventory_candidates(
    reportings: Iterable[Reporting], company: Company
) -> None:
    """
    Updates inventory_candidates for a collection of reportings.

    An inventory is considered a candidate for a reporting if:
    - road, direction, and lane are equal
    - km distance is at most inventory_radius (from company.metadata)
    - point distance is at most inventory_radius meters (from company.metadata)
    - inventory class is compatible with reporting class/kind (based on mapping)

    Class compatibility is defined in company.metadata["inventory_candidates_class_mapping"]
    with format:
    {
        inventory_class_uuid: {
            "occurrence_types": [reporting_class_uuid, ...],
            "occurrence_kinds": ["1", "2", ...]
        }
    }

    A reporting is compatible if its class is in occurrence_types OR its kind is in occurrence_kinds.

    If no mapping exists for a reporting class/kind, falls back to geographic-only filtering.
    The entire class filter can be disabled via company.metadata["disable_inventory_class_filter"].
    """
    # Extract UUIDs from the iterable
    reporting_uuids = [r.uuid if hasattr(r, "uuid") else r for r in reportings]

    if not reporting_uuids:
        return

    candidate_inventory_subquery = get_candidate_inventory_subquery(
        company,
    )
    m_radius = get_obj_from_path(company.metadata, "inventory_radius") or DEFAULT_RADIUS
    has_roads = company.company_roads.exists()

    # Get class mapping configuration
    disable_class_filter = (
        get_obj_from_path(company.metadata, "disable_inventory_class_filter") or False
    )
    class_mapping = (
        get_obj_from_path(company.metadata, "inventory_candidates_class_mapping") or {}
    )
    bond_types = get_bond_occurrence_types(company)

    reportings_with_candidates = (
        Reporting.objects.filter(uuid__in=reporting_uuids, parent__isnull=True)
        .exclude(occurrence_type__occurrence_kind="2")
        .prefetch_related("occurrence_type")  # Need occurrence_type for class filtering
        .only("uuid", "occurrence_type")
    )

    if not has_roads:
        reportings_with_candidates = reportings_with_candidates.annotate(
            lat0=ST_Y("point"),
            lon0=ST_X("point"),
            # dynamic longitude delta (because longitude degrees shrink as cos(lat))
            lon_delta=ExpressionWrapper(
                m_radius / (111320.0 * Cos(Radians(ST_Y("point")))),
                output_field=FloatField(),
            ),
        )

    reportings_with_candidates = reportings_with_candidates.annotate(
        candidate_inventory_uuids=MakeArray(
            candidate_inventory_subquery,
        )
    )

    # Collect all candidate inventory UUIDs for batch lookup of their classes
    all_candidate_uuids = set()
    reportings_list = list(reportings_with_candidates)
    for reporting in reportings_list:
        if reporting.candidate_inventory_uuids:
            all_candidate_uuids.update(reporting.candidate_inventory_uuids)

    # Build lookup dict: inventory_uuid -> occurrence_type_uuid
    inventory_class_lookup = {}
    if all_candidate_uuids and class_mapping and not disable_class_filter:
        inventory_classes = Reporting.objects.filter(
            uuid__in=all_candidate_uuids
        ).values("uuid", "occurrence_type_id")
        for inv in inventory_classes:
            inventory_class_lookup[str(inv["uuid"])] = (
                str(inv["occurrence_type_id"]) if inv["occurrence_type_id"] else None
            )

    through_model = Reporting.inventory_candidates.through

    # Prefetch all through model relationships in one query
    through_relationships = through_model.objects.filter(
        from_reporting_id__in=reporting_uuids
    )
    # Group by from_reporting_id for efficient lookup
    relationships_by_reporting = defaultdict(dict)
    for rel in through_relationships:
        from_id = str(rel.from_reporting_id)
        to_id = str(rel.to_reporting_id)
        relationships_by_reporting[from_id][to_id] = str(rel.pk)

    create_entries = []
    delete_entries = []
    for reporting in reportings_list:
        curr_suggestions = relationships_by_reporting.get(str(reporting.uuid), {})

        # Get compatible inventory classes for this reporting
        reporting_class_uuid = (
            str(reporting.occurrence_type_id) if reporting.occurrence_type_id else None
        )
        reporting_kind = (
            reporting.occurrence_type.occurrence_kind
            if reporting.occurrence_type
            else None
        )
        if bond_types is not None and reporting_class_uuid not in bond_types:
            delete_entries.extend(curr_suggestions.values())
            continue

        compatible_inv_classes = None
        if not disable_class_filter and class_mapping:
            compatible_inv_classes = get_compatible_inventory_classes_for_reporting(
                reporting_class_uuid, reporting_kind, class_mapping
            )

        for candidate_uuid in reporting.candidate_inventory_uuids or []:
            candidate_uuid_str = str(candidate_uuid)

            # Apply class filter if mapping exists
            if compatible_inv_classes is not None:
                candidate_class = inventory_class_lookup.get(candidate_uuid_str)
                if candidate_class not in compatible_inv_classes:
                    # Skip this candidate - class not compatible
                    continue

            curr_suggestions.pop(candidate_uuid_str, None)
            create_entries.append(
                through_model(
                    from_reporting_id=reporting.uuid,
                    to_reporting_id=candidate_uuid,
                )
            )

        delete_entries.extend(curr_suggestions.values())
    # Bulk create the relationships
    if create_entries:
        through_model.objects.bulk_create(create_entries, ignore_conflicts=True)
    # Bulk delete the relationships
    if delete_entries:
        through_model.objects.filter(pk__in=delete_entries).delete()


def get_reportings_for_inventory_subquery(
    company: Company, bond_types: Optional[set] = None
) -> Subquery:
    """
    Returns a subquery that finds reporting candidates for an inventory
    based on geographic criteria (road, km, direction, lane, coordinates).

    Note: Class-based filtering is applied separately in the main function
    using the inventory_candidates_class_mapping from company.metadata.
    """
    m_radius = get_obj_from_path(company.metadata, "inventory_radius") or DEFAULT_RADIUS
    km_radius = float(m_radius) * 0.001

    lat_delta = m_radius / 111320.0

    has_roads = company.company_roads.exists()
    subquery = Reporting.objects.filter(
        company=company,
        parent__isnull=True,
        road_name=OuterRef("road_name"),
        direction=OuterRef("direction"),
        lane=OuterRef("lane"),
        km__gt=OuterRef("km") - km_radius,
        km__lt=OuterRef("km") + km_radius,
    ).exclude(occurrence_type__occurrence_kind="2")

    if bond_types is not None:
        subquery = subquery.filter(occurrence_type_id__in=bond_types)

    if not has_roads:
        subquery = subquery.annotate(lat1=ST_Y("point"), lon1=ST_X("point"),).filter(
            lat1__gte=OuterRef("lat0") - lat_delta,
            lat1__lte=OuterRef("lat0") + lat_delta,
            lon1__gte=OuterRef("lon0") - OuterRef("lon_delta"),
            lon1__lte=OuterRef("lon0") + OuterRef("lon_delta"),
        )

    return Subquery(subquery.values("uuid"))


def update_reporting_inventory_candidates_from_inventories(
    inventories: Iterable[Reporting], company: Company
) -> None:
    """
    Updates inventory_candidates for a collection of reportings that are inventories.

    This is the reverse operation of update_reporting_inventory_candidates.
    When an inventory is saved, this function finds reportings (apontamentos)
    that should have this inventory as a candidate.

    A reporting is considered a candidate for an inventory if:
    - road, direction, and lane are equal
    - km distance is at most inventory_radius (from company.metadata)
    - point distance is at most inventory_radius meters (from company.metadata)
    - reporting class/kind is compatible with inventory class (based on mapping)

    Class compatibility is defined in company.metadata["inventory_candidates_class_mapping"]
    with format:
    {
        inventory_class_uuid: {
            "occurrence_types": [reporting_class_uuid, ...],
            "occurrence_kinds": ["1", "2", ...]
        }
    }

    A reporting is compatible if its class is in occurrence_types OR its kind is in occurrence_kinds.

    If no mapping exists for an inventory class, falls back to geographic-only filtering.
    The entire class filter can be disabled via company.metadata["disable_inventory_class_filter"].
    """
    # Extract UUIDs from the iterable
    inventory_uuids = [r.uuid if hasattr(r, "uuid") else r for r in inventories]

    if not inventory_uuids:
        return

    m_radius = get_obj_from_path(company.metadata, "inventory_radius") or DEFAULT_RADIUS
    has_roads = company.company_roads.exists()

    # Get class mapping configuration
    disable_class_filter = (
        get_obj_from_path(company.metadata, "disable_inventory_class_filter") or False
    )
    class_mapping = (
        get_obj_from_path(company.metadata, "inventory_candidates_class_mapping") or {}
    )
    bond_types = get_bond_occurrence_types(company)
    reportings_subquery = get_reportings_for_inventory_subquery(company, bond_types)

    inventories_with_reportings = (
        Reporting.objects.filter(uuid__in=inventory_uuids)
        .filter(occurrence_type__occurrence_kind="2")
        .prefetch_related("occurrence_type")  # Need occurrence_type for class filtering
        .only("uuid", "occurrence_type")
    )

    if not has_roads:
        inventories_with_reportings = inventories_with_reportings.annotate(
            lat0=ST_Y("point"),
            lon0=ST_X("point"),
            # dynamic longitude delta (because longitude degrees shrink as cos(lat))
            lon_delta=ExpressionWrapper(
                m_radius / (111320.0 * Cos(Radians(ST_Y("point")))),
                output_field=FloatField(),
            ),
        )

    inventories_with_reportings = inventories_with_reportings.annotate(
        reportings_uuids=MakeArray(
            reportings_subquery,
        )
    )

    # Collect all candidate reporting UUIDs for batch lookup of their classes
    all_reporting_uuids = set()
    inventories_list = list(inventories_with_reportings)
    for inventory in inventories_list:
        if inventory.reportings_uuids:
            all_reporting_uuids.update(inventory.reportings_uuids)

    # Build lookup dict: reporting_uuid -> {class_uuid, kind}
    reporting_class_lookup = {}
    if all_reporting_uuids and class_mapping and not disable_class_filter:
        reporting_classes = Reporting.objects.filter(
            uuid__in=all_reporting_uuids
        ).values("uuid", "occurrence_type_id", "occurrence_type__occurrence_kind")
        for rpt in reporting_classes:
            reporting_class_lookup[str(rpt["uuid"])] = {
                "class_uuid": (
                    str(rpt["occurrence_type_id"])
                    if rpt["occurrence_type_id"]
                    else None
                ),
                "kind": rpt.get("occurrence_type__occurrence_kind"),
            }

    through_model = Reporting.inventory_candidates.through

    # Prefetch all through model relationships in one query
    through_relationships = through_model.objects.filter(
        to_reporting_id__in=inventory_uuids
    )
    # Group by from_reporting_id for efficient lookup
    relationships_by_inventory = defaultdict(dict)
    for rel in through_relationships:
        from_id = str(rel.from_reporting_id)
        to_id = str(rel.to_reporting_id)
        relationships_by_inventory[to_id][from_id] = str(rel.pk)

    create_entries = []
    delete_entries = []
    for inventory in inventories_list:
        curr_suggestions = relationships_by_inventory.get(str(inventory.uuid), {})

        # Get compatible reporting criteria for this inventory
        inventory_class_uuid = (
            str(inventory.occurrence_type_id) if inventory.occurrence_type_id else None
        )

        for reporting_uuid in inventory.reportings_uuids or []:
            reporting_uuid_str = str(reporting_uuid)

            # Apply class/kind filter if mapping exists
            if not disable_class_filter and class_mapping:
                reporting_info = reporting_class_lookup.get(reporting_uuid_str, {})
                reporting_class = reporting_info.get("class_uuid")
                reporting_kind = reporting_info.get("kind")

                compatible_inv_classes = get_compatible_inventory_classes_for_reporting(
                    reporting_class, reporting_kind, class_mapping
                )

                if (
                    compatible_inv_classes is not None
                    and inventory_class_uuid not in compatible_inv_classes
                ):
                    continue

            curr_suggestions.pop(reporting_uuid_str, None)
            create_entries.append(
                through_model(
                    from_reporting_id=reporting_uuid,
                    to_reporting_id=inventory.uuid,
                )
            )
        delete_entries.extend(curr_suggestions.values())

    if create_entries:
        through_model.objects.bulk_create(create_entries, ignore_conflicts=True)

    # Bulk delete the relationships
    if delete_entries:
        through_model.objects.filter(pk__in=delete_entries).delete()
