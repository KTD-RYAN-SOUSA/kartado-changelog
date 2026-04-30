import logging
import uuid
from copy import deepcopy
from datetime import datetime
from itertools import product
from typing import Dict, Iterable, List, Tuple, Union

import sentry_sdk
from django.utils.timezone import now
from rest_framework_json_api import serializers
from simple_history.utils import bulk_create_with_history
from zappa.asynchronous import task

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Company
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import (
    RecordMenu,
    Reporting,
    ReportingFile,
    ReportingInReporting,
    ReportingInReportingAsyncBatch,
    ReportingRelation,
)
from apps.reportings.signals import add_last_monitoring_files
from apps.service_orders.models import ServiceOrderActionStatusSpecs
from apps.users.models import User
from apps.work_plans.const.async_batches import BATCH_SIZE, FILTERED, MANUAL
from apps.work_plans.models import Job, JobAsyncBatch
from helpers.forms import clean_form_data, merge_monitoring_and_therapy_data
from helpers.histories import bulk_update_with_history
from helpers.permissions import PermissionManager
from helpers.signals import auto_add_number
from helpers.strings import get_obj_from_path, to_camel_case


def process_reporting_from_inventory(
    inventory: Reporting,
    occurrence_type: OccurrenceType,
    job: Job,
    in_job_status: ServiceOrderActionStatusSpecs,
    user: User,
    inventory_to_reporting_id: dict,
    approval_step: Union[ApprovalStep, None],
    found_at: datetime,
    menu: RecordMenu,
    is_manual: bool,
) -> Union[Reporting, None]:
    """
    Create the Reporting instance according to the Inventory instance and set the
    Inventory as the Reporting parent.

    NOTE: The returned instance is not going to be created in the DB. You should do this
    using a bulk create call to optimize the process.

    Args:
        inventory (Reporting): The Inventory the Reporting will be based on
        occurrence_type (OccurrenceType): The OccurrenceType of the new Reporting
        job (Job): Job the new Reporting will be added to
        in_job_status (ServiceOrderActionStatusSpecs): Which status is considered "in a job"
        user (User): User doing the request
        inventory_to_reporting_id (dict): Inventory ID to Reporting ID reference dict
        is_manual (bool): Check if the creation is MANUAL or FILTERED

    Returns:
        Union[Reporting, None]: The new Reporting instance if successful, None if not
    """

    try:
        if occurrence_type.deadline:
            due_at = found_at + occurrence_type.deadline
        else:
            due_at = None
        new_rep = deepcopy(inventory)
        new_rep.parent = inventory
        new_rep.pk = (
            uuid.uuid4() if is_manual else inventory_to_reporting_id[str(inventory.pk)]
        )
        new_rep.number = None
        new_rep.occurrence_type = occurrence_type
        new_rep.form_data = clean_form_data(new_rep.form_data, occurrence_type)
        new_rep.firm = job.firm
        new_rep.status = in_job_status
        new_rep.created_by = user
        new_rep.approval_step = approval_step
        new_rep.executed_at = None
        new_rep.found_at = found_at
        new_rep.due_at = due_at
        new_rep.menu = menu

        auto_add_number(new_rep, "RP_name_format")
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logging.error(
            "process_reporting_from_inventory: There was a problem while creating the new Reporting"
        )
        return None
    else:
        return new_rep


def get_manual_inventory_qs(
    inventories_ids: Iterable[uuid.UUID], occurrence_types_ids: Iterable[uuid.UUID]
) -> Tuple[Iterable[Reporting], Iterable[OccurrenceType]]:
    """
    Fetch the Inventory and OccurrenceType instances using the provided IDs
    and validate them.

    Args:
        inventories_ids (Iterable[uuid.UUID]): IDs of the input Inventory items
        occurrence_types_ids (Iterable[uuid.UUID]): IDs of the input OccurrenceType items

    Returns:
        Tuple[Iterable[Reporting], Iterable[OccurrenceType]]: Validated manual querysets according to the IDs
    """

    try:
        # Ensure required data is provided
        if not inventories_ids:
            raise serializers.ValidationError(
                "kartado.error.inventory.inventory_list_is_required"
            )
        if not occurrence_types_ids:
            raise serializers.ValidationError(
                "kartado.error.inventory.occurrence_type_list_is_required_with_manual_inventory_qs"
            )

        inventories = Reporting.objects.filter(pk__in=inventories_ids)
        occurrence_types = OccurrenceType.objects.filter(pk__in=occurrence_types_ids)

        # Ensure all items exist
        inv_not_found = inventories.count() != len(inventories_ids)
        occ_type_not_found = occurrence_types.count() != len(occurrence_types_ids)
        if inv_not_found or occ_type_not_found:
            raise serializers.ValidationError(
                "kartado.error.inventory.at_least_one_provided_inventory_or_occ_type_does_not_exist"
            )

        # Ensure correct kind
        if occurrence_types.filter(occurrence_kind="2").exists():
            raise serializers.ValidationError(
                "kartado.error.inventory.occurrence_type_has_invalid_occurrence_kind"
            )
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logging.error(
            "get_inventory_occ_type_pairs: Manual usage does not provide a valid items list"
        )
    else:
        return inventories, occurrence_types


def get_filtered_inventory_qs(
    filters: dict, user: User, company: Company
) -> Iterable[Reporting]:
    """
    Fetch the permissioned Inventory queryset by applying the provided filters.

    Args:
        filters (dict): Filters to narrow down the queryset
        user (User): User used to check the Inventory permissions
        company (Company): Company used to check Inventory permissions

    Returns:
        Iterable[Reporting]: Inventory items according to the provided filters
    """
    # To avoid circular imports :(
    from django.db.models import Q

    from apps.reportings.views import ReportingFilter

    inventory_allowed_qs = PermissionManager(
        user=user, company_ids=company, model="Inventory"
    ).get_allowed_queryset()

    # Base queryset according to permissions
    permission_query = Q()
    if "none" in inventory_allowed_qs:
        return Reporting.objects.none()

    if "self" in inventory_allowed_qs:
        permission_query |= Q(created_by=user, occurrence_type__occurrence_kind="2")

    if "all" in inventory_allowed_qs:
        permission_query |= Q(company_id=company, occurrence_type__occurrence_kind="2")

    if not permission_query:
        user_companies = user.companies.all()
        base_queryset = Reporting.objects.filter(
            company__in=user_companies,
            occurrence_type__occurrence_kind="2",
        )
    else:
        base_queryset = Reporting.objects.filter(permission_query)

    # Apply the request filters to the base_queryset
    filtered_inventory_qs = ReportingFilter(filters, base_queryset).qs
    origins, _ = get_mapped_occ_type_uuids(company)

    return filtered_inventory_qs.filter(occurrence_type__in=origins)


def reportings_from_inventory(
    job: Job,
    inventories_ids: Iterable[uuid.UUID],
    occurrence_types_ids: Iterable[uuid.UUID],
    user: User,
    company: Company,
    menu: RecordMenu,
    filters: dict = None,
):
    """
    Validate and break the input in smaller pieces (batches) that are going to be processed by
    a scheduled task called process_job_async_batch.

    NOTE: This async task is only the trigger for the whole operation. The actual creation happens
    in the scheduled task process_job_async_batch.

    Args:
        job_id (uuid.UUID): The Job the new Reporting instances will be related to
        inventories_ids (Iterable[uuid.UUID]): Inventory input for the manual method
        occurrence_types_ids (Iterable[uuid.UUID]): OccurrenceType input for the manual method
        user_id (uuid.UUID): User doing the request
        company_id (uuid.UUID): Related Company
        filters (dict, optional): Contains the filters to automatically find the input Inventory items.
        Defaults to None. Not providing the filters will trigger manual method.
    """

    start_time = now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info(
        f"reportings_from_inventory: [{start_time}] Started inventory data batching"
    )

    try:
        mappers = company.metadata.get(
            "sheet_inventory_occurrence_type_mapper_for_inspection", []
        )
        in_job_status = (
            ServiceOrderActionStatusSpecs.objects.filter(company=company, order=2)
            .first()
            .status
        )
        approval_step = ApprovalStep.objects.filter(
            approval_flow__company=company,
            approval_flow__target_model="reportings.Reporting",
            previous_steps__isnull=True,
        ).first()

        # Don't let the process continue if we are using filters but there are no maps
        if bool(filters) and not bool(mappers):
            raise serializers.ValidationError(
                "kartado.error.job.mapper_parametrization_is_required_when_using_filters_method"
            )
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logging.error(
            "reportings_from_inventory: Error while validating the provided IDs"
        )

    # Basic requirements were met, so we can start batching data
    else:
        job.creating_batches = True
        bulk_update_with_history([job], Job, use_django_bulk=True, user=user)

        inventories, occurrence_types = [], []
        new_rep_in_reps = []

        # Filter method
        if filters:
            inventories = get_filtered_inventory_qs(filters, user, company)

            # Serialize ReportingInReporting if any (before adding the children)
            ser_rep_in_reps = inventories.values_list(
                "reporting_relation_parent__parent",
                "reporting_relation_parent__child",
                "reporting_relation_parent__reporting_relation",
            )

            # Merge QuerySet of the Inventory items related to the original queryset
            origins, _ = get_mapped_occ_type_uuids(company)
            children_ids = ReportingInReporting.objects.filter(
                parent__in=inventories
            ).values("child_id")
            relation_children = Reporting.objects.filter(
                pk__in=children_ids,
                occurrence_type__in=origins,
            )
            inventories = inventories.union(relation_children)

            # Determine new Reporting items UUIDs
            inventory_to_reporting_id = {
                str(inv_id): str(uuid.uuid4())
                for inv_id in inventories.values_list("uuid", flat=True)
            }
            job.pending_inventory_to_reporting_id = inventory_to_reporting_id

            # Determine the IDs of the new ReportingInReporting items
            comb_tmpl = "{},{},{}"
            for parent, child, relation in ser_rep_in_reps:
                parent_in_qs = str(parent) in inventory_to_reporting_id
                child_in_qs = str(child) in inventory_to_reporting_id

                # Only consider if both are part of the final queryset
                if parent_in_qs and child_in_qs:
                    parent_rep_id = inventory_to_reporting_id[str(parent)]
                    child_rep_id = inventory_to_reporting_id[str(child)]
                    new_comb = comb_tmpl.format(parent_rep_id, child_rep_id, relation)

                    if new_comb not in new_rep_in_reps:
                        new_rep_in_reps.append(new_comb)

        # Manual method
        else:
            inventories, occurrence_types = get_manual_inventory_qs(
                inventories_ids, occurrence_types_ids
            )

            # Determine new Reporting items UUIDs
            inventory_to_reporting_id = {
                str(inv_id): str(uuid.uuid4())
                for inv_id in inventories.values_list("uuid", flat=True)
            }
            job.pending_inventory_to_reporting_id = inventory_to_reporting_id

        # Create the async Inventory batches
        inv_batch_count = 0
        if inventories:
            for batch_start in range(0, inventories.count(), BATCH_SIZE):
                try:
                    batch_end = batch_start + BATCH_SIZE
                    batch_inventories = inventories[batch_start:batch_end]

                    if batch_inventories:
                        job_async_batch = JobAsyncBatch.objects.create(
                            batch_type=FILTERED if filters else MANUAL,
                            job=job,
                            created_by=user,
                            company=company,
                            in_job_status=in_job_status,
                            approval_step=approval_step,
                            menu=menu,
                        )

                        job_async_batch.inventories.set(batch_inventories)
                        if occurrence_types:
                            job_async_batch.occurrence_types.set(occurrence_types)
                except Exception as e:
                    sentry_sdk.capture_exception(e)
                    logging.error(
                        "reportings_from_inventory: Problem found while creating Inventory async batch"
                    )
                else:
                    inv_batch_count += 1

            logging.info(
                f"reportings_from_inventory: {inv_batch_count} Inventory batches were created"
            )

        # Create the async ReportingInReporting batches (if any)
        rep_in_rep_batch_count = 0
        if new_rep_in_reps:
            for batch_start in range(0, len(new_rep_in_reps), BATCH_SIZE):
                batch_end = batch_start + BATCH_SIZE
                batch_rep_in_reps = new_rep_in_reps[batch_start:batch_end]

                if batch_rep_in_reps:
                    try:
                        ReportingInReportingAsyncBatch.objects.create(
                            pending_batch_items=batch_rep_in_reps,
                            job=job,
                            company=company,
                            created_by=user,
                        )
                    except Exception as e:
                        sentry_sdk.capture_exception(e)
                        logging.error(
                            "reportings_from_inventory: Problem found while creating ReportingInReporting async batch"
                        )
                    else:
                        rep_in_rep_batch_count += 1

            logging.info(
                f"reportings_from_inventory: {rep_in_rep_batch_count} ReportingInReporting batches were created"
            )

    # Record the inital totals
    job.total_inventory_batches = inv_batch_count
    job.total_reporting_in_reporting_batches = rep_in_rep_batch_count

    # Mark the batch creation as done
    job.creating_batches = False
    bulk_update_with_history([job], Job, use_django_bulk=True, user=user)

    end_time = now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info(
        f"reportings_from_inventory: [{end_time}] Finished inventory data batching"
    )


def has_sheet_occurrence_type(inventory: Reporting, company: Company) -> bool:
    """
    Does the provided Inventory's OccurrenceType match the metadata's field
    sheet_inventory_occurrence_type?

    Args:
        inventory (Reporting): Inventory we are going to check
        company (Company): Provider of the metadata

    Returns:
        bool: If it's a match or not (will return False if field is not configured)
    """

    sheet_inventory_occurrence_type = company.metadata.get(
        "sheet_inventory_occurrence_type", None
    )
    occ_type_id = str(inventory.occurrence_type.pk)

    return (
        occ_type_id == sheet_inventory_occurrence_type
        if sheet_inventory_occurrence_type
        else False
    )


def get_mapped_occ_type_uuids(
    company: Company,
) -> Tuple[Iterable[uuid.UUID], Iterable[uuid.UUID]]:
    """
    Convert the mapped OccurrenceType UUIDs into two easy to access lists.

    Args:
        company (Company): Company where the mapping is configured

    Returns:
        Tuple[Iterable[uuid.UUID], Iterable[uuid.UUID]]: Lists with the origins and targets
        IDs respectively.
    """

    origins, targets = [], []
    mappers = company.metadata.get(
        "sheet_inventory_occurrence_type_mapper_for_inspection", []
    )
    if mappers:
        origins = [mapper["origin"] for mapper in mappers]
        targets = [mapper["target"] for mapper in mappers]

    return origins, targets


def create_recuperation_items(
    reportings,
    recuperation_occurrence_types,
    company,
    user,
    reporting_relation_metadata,
    menu,
    job=None,
):
    if job:
        try:
            in_job_status = (
                ServiceOrderActionStatusSpecs.objects.filter(company=company, order=2)
                .first()
                .status
            )
        except Exception:
            raise serializers.ValidationError("kartado.error.job.status_not_found")

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

    new_reps = []
    new_reporting_in_reportings = []
    updated_reps = []
    found_at = now()

    inspection_occurrence_kind = get_obj_from_path(
        company.metadata, "inspection_occurrence_kind"
    )
    if isinstance(inspection_occurrence_kind, str):
        inspection_occurrence_kind = [inspection_occurrence_kind]

    for rep, occ_type in list(product(reportings, recuperation_occurrence_types)):
        if rep.occurrence_type.occurrence_kind not in inspection_occurrence_kind:
            raise serializers.ValidationError(
                "kartado.error.reporting.reporting_not_inspection"
            )

        if occ_type.deadline:
            due_at = found_at + occ_type.deadline
        else:
            due_at = None

        new_rep = deepcopy(rep)
        new_rep.pk = uuid.uuid4()
        new_rep.number = None
        new_rep.editable = True
        new_rep.occurrence_type = occ_type
        new_rep.form_data = clean_form_data(new_rep.form_data, occ_type)
        if not job:
            new_rep.job = None
        if job:
            new_rep.firm = job.firm
            new_rep.status = in_job_status
        new_rep.created_by = user
        new_rep.executed_at = None
        new_rep.found_at = found_at
        new_rep.due_at = due_at
        new_rep.approval_step = approval_step
        new_rep.menu = menu
        auto_add_number(new_rep, "RP_name_format")

        new_reps.append(new_rep)

        new_reporting_in_reportings.append(
            ReportingInReporting(
                parent=rep, child=new_rep, reporting_relation=reporting_relation
            )
        )
    for item in reportings:
        item.created_recuperations_with_relation = True
        updated_reps.append(item)

    bulk_create_with_history(new_reps, Reporting, default_user=user)
    if job:
        job.reportings.add(*new_reps)
    bulk_create_with_history(
        new_reporting_in_reportings, ReportingInReporting, default_user=user
    )
    bulk_update_with_history(
        updated_reps, Reporting, use_django_bulk=True, user=user, batch_size=250
    )
    if job:
        return job


def separate_reportings_by_therapy(
    reportings: Iterable[Reporting],
) -> Tuple[List[Reporting], List[Reporting]]:

    reportings_with_therapy = []
    reportings_without_therapy = []

    for reporting in reportings:
        therapy = reporting.form_data.get("therapy")

        # Regra: Apontamentos sem therapy (ou com therapy vazia) vão para a lista without_therapy.
        if not therapy:
            reportings_without_therapy.append(reporting)
            continue

        # A partir daqui, a therapy existe e não está vazia.
        occurrence_type_uuid_list = [
            item.get("occurrence_type", "") for item in therapy
        ]

        has_any_occurrence_type = any(occurrence_type_uuid_list)
        has_all_occurrence_types = all(occurrence_type_uuid_list)

        # Regra: TODOS os itens da therapy têm occurrence_type.
        if has_all_occurrence_types:
            reportings_with_therapy.append(reporting)
        # Regra: NENHUM item da therapy tem occurrence_type.
        elif not has_any_occurrence_type:
            reportings_without_therapy.append(reporting)
        # Regra: Há uma mistura de itens com e sem occurrence_type (pelo menos um com e um sem).
        else:
            raise serializers.ValidationError(
                "kartado.error.reporting.reportings_at_least_one_therapy_without_occurrence_type"
            )

    return reportings_with_therapy, reportings_without_therapy


def create_recuperation_from_inspections(rep_list, company, user, menu, job=None):
    inspection_occurrence_kind = get_obj_from_path(
        company.metadata, "inspection_occurrence_kind"
    )
    if isinstance(inspection_occurrence_kind, str):
        inspection_occurrence_kind = [inspection_occurrence_kind]
    reporting_relation_metadata = get_obj_from_path(
        company.metadata, "recuperation_reporting_relation"
    )
    initial_status = None
    if job:
        try:
            in_job_status = (
                ServiceOrderActionStatusSpecs.objects.filter(company=company, order=2)
                .first()
                .status
            )
        except Exception:
            raise serializers.ValidationError("kartado.error.job.status_not_found")
    else:
        try:
            initial_status = (
                ServiceOrderActionStatusSpecs.objects.filter(
                    company=company, order__lt=2
                )
                .order_by("-order")
                .first()
                .status
            )
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.inventory.create_recuperation_from_inspections.status_lower_than_2_not_found"
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

    new_reps = []
    new_reporting_in_reportings = []
    updated_reps = []
    new_reporting_files = []
    found_at = now()
    for item in rep_list:
        if item.occurrence_type.occurrence_kind not in inspection_occurrence_kind:
            raise serializers.ValidationError(
                "kartado.error.reporting.reporting_not_inspection"
            )
        therapy = item.form_data.get("therapy", [])
        if therapy:
            occurrence_type_uuid_list = [a.get("occurrence_type", "") for a in therapy]
            if all(occurrence_type_uuid_list):
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
                    occ = OccurrenceType.objects.get(
                        uuid=item_therapy["occurrence_type"]
                    )
                    if occ.deadline:
                        due_at = found_at + occ.deadline
                    else:
                        due_at = None
                    new_rep = deepcopy(item)
                    new_rep.pk = uuid.uuid4()
                    new_rep.occurrence_type = occ
                    new_rep.number = None
                    new_rep.editable = True

                    new_rep.form_data = merge_monitoring_and_therapy_data(
                        item.form_data, item_therapy, occ
                    )

                    new_rep.created_by = user
                    new_rep.executed_at = None
                    new_rep.found_at = found_at
                    new_rep.due_at = due_at
                    if not job:
                        new_rep.job = None
                    new_rep.menu = menu
                    new_rep.approval_step = approval_step
                    if job:
                        new_rep.firm = job.firm
                        new_rep.status = in_job_status
                    else:
                        new_rep.status = initial_status

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
                    "kartado.error.reporting.reportings_at_least_one_therapy_without_occurrence_type"
                )
        else:
            raise serializers.ValidationError(
                "kartado.error.reporting.reporting_not_inspection"
            )
    bulk_create_with_history(new_reps, Reporting, default_user=user)
    bulk_create_with_history(
        new_reporting_in_reportings, ReportingInReporting, default_user=user
    )
    bulk_update_with_history(
        updated_reps, Reporting, use_django_bulk=True, user=user, batch_size=250
    )
    bulk_create_with_history(new_reporting_files, ReportingFile, default_user=user)
    if job:
        job.reportings.add(*new_reps)
        return job


def return_inventory_fields(company: Company) -> List[Dict[str, str]]:

    FILTERED_DATATYPES = ["string", "textarea", "number", "float", "timestamp"]

    data = [{"id": "uuid", "name": "ID"}, {"id": "number", "name": "Serial"}]

    occs = OccurrenceType.objects.filter(
        company=company,
        next_version__isnull=True,
        active=True,
        occurrence_kind="2",
    )

    for occ in occs:
        for field in occ.form_fields["fields"]:
            if (
                get_obj_from_path(field, "datatype")
                and get_obj_from_path(field, "datatype").lower() in FILTERED_DATATYPES
            ):
                field_info = {
                    "id": to_camel_case(get_obj_from_path(field, "apiname")),
                    "name": get_obj_from_path(field, "displayname"),
                }
                if field_info not in data:
                    data.append(field_info)
    data.sort(key=lambda x: x["name"])
    return data


@task
def add_last_monitoring_files_async(rep_id):

    rep = Reporting.objects.get(uuid=rep_id)
    add_last_monitoring_files(sender=Reporting, instance=rep, created=True)
