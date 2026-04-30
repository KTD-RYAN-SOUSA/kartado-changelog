import logging
from functools import reduce
from operator import __and__ as AND
from operator import __or__ as OR
from typing import Iterable

import sentry_sdk
from django.conf import settings
from django.contrib.gis.geos import GeometryCollection
from django.core.exceptions import FieldError
from django.db.models import Q
from django.db.models.query import QuerySet
from django.utils import timezone
from django_bulk_update.helper import bulk_update
from fnc.mappings import get
from rest_framework_json_api import serializers

from apps.monitorings.models import MonitoringCycle, MonitoringPlan
from apps.occurrence_records.models import (
    CustomDashboard,
    OccurrenceRecord,
    RecordPanelShowList,
)
from apps.reportings.helpers.default_menus import rebalance_visible_panels_orders
from apps.reportings.models import RecordMenu
from apps.service_orders.const import kind_types
from apps.service_orders.models import ServiceOrder
from apps.users.models import UserNotification
from helpers.apps.json_logic import apply_json_logic
from helpers.apps.service_orders import create_procedure_objects
from helpers.apps.users import add_debounce_data
from helpers.fields import FeatureCollectionField, get_nested_fields
from helpers.strings import get_obj_from_path, to_snake_case


def get_collection(obj):
    collection = None
    if obj.monitoring_plan and obj.monitoring_points.exists():
        points = [
            a
            for item in obj.monitoring_points.all().values_list("coordinates")
            for a in item
        ]
        collection = GeometryCollection(points)

    feature_collection = FeatureCollectionField(
        geometry_field="geometry",
        properties_field="properties",
        collection=collection,
    )
    collection = feature_collection.to_representation(obj)
    return collection


def execute_transition(new_data, transitions, occurrence_record, source):
    error = True
    data = {"request": new_data, "source": source}

    for transition in transitions:
        if apply_json_logic(transition.condition, data):
            occurrence_record.approval_step = transition.destination
            origin = transition.origin

            # Handle required fields
            required_options = origin.field_options.get("required", [])
            validation_passed = True
            for required_option in required_options:
                if type(required_option) is str:
                    path = to_snake_case(required_option).replace(".", "__")
                    field_value = get_obj_from_path(source, path)

                    field_is_empty = (
                        not field_value
                        and field_value != 0  # False positive falsy value
                    )
                    if field_is_empty:
                        # The field is not present, therefore the next transition should
                        # be attempted and the error variable keeps its value
                        validation_passed = False

                elif type(required_option) is dict:
                    variable_path = to_snake_case(
                        required_option["variable"].replace(".", "__")
                    )
                    variable_value = get_obj_from_path(source, variable_path)
                    validation_required = variable_value in required_option["values"]
                    if validation_required:
                        for field in required_option["fields"]:
                            path = to_snake_case(field).replace(".", "__")
                            field_value = get_obj_from_path(source, path)

                            field_is_empty = (
                                not field_value
                                and field_value != 0  # False positive falsy value
                            )
                            if field_is_empty:
                                # The field is not present, therefore the next transition should
                                # be attempted and the error variable keeps its value
                                validation_passed = False

            if not validation_passed:
                continue

            for key, callback in transition.callback.items():
                if key == "change_fields":
                    for field in callback:
                        try:
                            value = get_nested_fields(field["value"], occurrence_record)
                            if value == "timezone.now()":
                                setattr(
                                    occurrence_record, field["name"], timezone.now()
                                )
                            else:
                                setattr(occurrence_record, field["name"], value)
                        except Exception as e:
                            print("Exception setting model fields", e)
                elif key == "create_objects" and callback is True:
                    (
                        occurrence_record,
                        error_message,
                    ) = create_procedure_objects(occurrence_record)
                    if error_message:
                        raise serializers.ValidationError(error_message)
                elif key == "is_approved" and callback is True:
                    occurrence_record.is_approved = True

            occurrence_record.save()
            error = False
            break

    if error:
        raise serializers.ValidationError(
            "kartado.error.occurrence_record.no_approval_condition"
        )
    else:
        return occurrence_record


def get_record_type(record, search_tags_uuids):
    metadata = get("company.metadata", record, default={})
    land_used_ids = get("land_used_search_tags", metadata, default=[])
    land_ids = get("land_search_tags", metadata, default=[])
    environment_ids = get("environment_search_tags", metadata, default=[])
    if get("operational_control", record, default={}):
        return "operational"
    elif get("monitoring_plan", record, default={}):
        return "monitoring"
    elif search_tags_uuids:
        # land_used needs to be the first one
        if land_used_ids and all([item in search_tags_uuids for item in land_used_ids]):
            return "land_used"
        elif land_ids and all([item in search_tags_uuids for item in land_ids]):
            return "land"
        elif environment_ids and all(
            [item in search_tags_uuids for item in environment_ids]
        ):
            return "environment"
        else:
            return "other"
    else:
        return "old"


def remove_procedure_objects(validated_data):
    land_used_ids = get(
        "company.metadata.land_used_search_tags", validated_data, default=[]
    )
    search_tags_uuids = [
        str(item.uuid) for item in validated_data.get("search_tags", [])
    ]
    if land_used_ids and search_tags_uuids:
        is_land_used = [item in search_tags_uuids for item in land_used_ids]
        if all(is_land_used):
            validated_data["form_data"]["procedure_objects"] = []
            validated_data["form_data"]["include_procedures"] = False
    return validated_data


def kind_errors(
    kind,
    record_type,
    main_property,
    intersections,
    process_type_is_land_used,
    method,
):
    if kind == kind_types.ENVIRONMENT and record_type in ["land", "land_used"]:
        raise serializers.ValidationError(
            "kartado.error.service_order.environment_service_needs_environment_record_{}".format(
                method
            )
        )
    elif kind == kind_types.LAND and process_type_is_land_used:
        if record_type not in ["land", "land_used"]:
            raise serializers.ValidationError(
                "kartado.error.service_order.land_service_needs_land_record_{}".format(
                    method
                )
            )
        elif not main_property:
            raise serializers.ValidationError(
                "kartado.error.service_order.record_needs_main_property_{}".format(
                    method
                )
            )
    elif kind == kind_types.LAND and not process_type_is_land_used:
        if record_type in ["land", "land_used", "environment"]:
            raise serializers.ValidationError(
                "kartado.error.service_order.land_service_needs_different_record_{}".format(
                    method
                )
            )
        elif not intersections:
            raise serializers.ValidationError(
                "kartado.error.service_order.record_needs_properties_{}".format(method)
            )
    return


def create_services(validated_data, user):
    mandatory_fields = [
        "firm_id",
        "to_do",
        "done_at",
        "service_order_action_status_id",
        "deadline",
    ]
    new_procedure_objs = []
    procedure_objs = get("form_data.procedure_objects", validated_data, default=[])
    include_procedures = get(
        "form_data.include_procedures", validated_data, default=False
    )
    intersections = get("form_data.property_intersections", validated_data, default=[])
    main_property = get(
        "form_data.shape_file_property_is_specified",
        validated_data,
        default=False,
    )
    search_tags_uuids = [
        str(item.uuid) for item in get("search_tags", validated_data, default=[])
    ]
    record_type = get_record_type(validated_data, search_tags_uuids)

    if procedure_objs:
        for procedure_data in procedure_objs:
            # Validate procedure_data
            if not set(mandatory_fields).issubset(procedure_data.keys()):
                raise serializers.ValidationError(
                    "kartado.error.occurrence_record.no_procedure"
                )

            # Create service_order
            service_order = procedure_data.get("service_order", {})
            if service_order and "id" not in service_order:
                kind = service_order.pop("kind", "")
                process_type = service_order.pop("process_type", "")
                responsibles = service_order.pop("responsibles", {})
                managers = service_order.pop("managers", {})

                process_type_is_land_used = (
                    get("company.metadata.land_used_value", validated_data)
                    == process_type
                )

                kind_errors(
                    kind,
                    record_type,
                    main_property,
                    intersections,
                    process_type_is_land_used,
                    "create",
                )

                try:
                    new_service_order = ServiceOrder.objects.create(
                        company=validated_data["company"],
                        created_by=user,
                        kind=kind,
                        process_type=process_type,
                        **service_order,
                    )
                    new_service_order.responsibles.add(*responsibles.get("data", []))
                    new_service_order.managers.add(*managers.get("data", []))
                except Exception:
                    pass
                else:
                    procedure_data["service_order"] = {
                        "id": str(new_service_order.uuid)
                    }
                    new_procedure_objs.append(procedure_data)
            else:
                new_procedure_objs.append(procedure_data)
        validated_data["form_data"]["procedure_objects"] = new_procedure_objs
    elif include_procedures and not procedure_objs:
        raise serializers.ValidationError(
            "kartado.error.occurrence_record.no_procedure"
        )
    return validated_data


def validate_records(validated_data, records, method):
    kind = validated_data.get("kind", "")
    process_type = validated_data.get("process_type", "")
    process_type_is_land_used = (
        get("company.metadata.land_used_value", validated_data) == process_type
    )

    if kind == kind_types.LAND and process_type_is_land_used:
        if records.count() > 1:
            raise serializers.ValidationError(
                "kartado.error.service_order.land_service_needs_more_than_one_record_{}".format(
                    method
                )
            )
        else:
            shape_file_property = records.first().form_data.get(
                "shape_file_property", ""
            )
            validated_data["shape_file_property"] = shape_file_property

    for record in records:
        intersections = get("form_data.property_intersections", record, default=[])
        main_property = get(
            "form_data.shape_file_property_is_specified", record, default=False
        )
        search_tags_uuids = [str(item.uuid) for item in record.search_tags.all()]
        record_type = get_record_type(record, search_tags_uuids)
        kind_errors(
            kind,
            record_type,
            main_property,
            intersections,
            process_type_is_land_used,
            method,
        )

    return validated_data


def is_responsible_approval_monitoring_record(obj, user_firms, can_approve):
    filters = get("field_options.filter", obj.approval_step, default=[])
    # Check if MonitoringPlan is in final status
    monitoring = MonitoringPlan.objects.filter(
        pk=obj.monitoring_plan.pk, status__is_final=True
    )
    if not monitoring.exists():
        return False

    # Create filter for MonitoringCycle
    filter_dict = {}
    if "executers" in filters:
        filter_dict["executers__in"] = user_firms
    elif "evaluators" in filters:
        filter_dict["evaluators__in"] = user_firms
    elif "approvers" in filters:
        filter_dict["approvers__in"] = user_firms
    elif "homologator" in filters and can_approve:
        return True

    # Check if user is in an active Cycle
    now = timezone.now()
    is_in_active_cycle = MonitoringCycle.objects.filter(
        monitoring_plan=obj.monitoring_plan,
        start_date__date__lte=now.date(),
        end_date__date__gte=now.date(),
        **filter_dict,
    ).exists()
    return is_in_active_cycle


def handle_custom_filters(var_name, var_value):
    if var_name == "has_service":
        return {"service_orders__isnull": not var_value}

    if var_name == "service_is_done":
        if var_value is True:
            return {"service_orders__is_closed": var_value}
        else:
            return {
                "service_orders__is_closed": var_value,
                "service_orders__isnull": True,
            }

    if var_name == "search_tag":
        return {"search_tags": var_value}

    if var_name == "parameter_group":
        return {"occurrence_type": var_value}

    if var_name == "occurrence_kind":
        return {"occurrence_type__occurrence_kind": var_value}

    if var_name == "occurrence_kind_tags":
        return {"search_tags": var_value}

    if "." in var_name:
        return {var_name.replace(".", "__"): var_value}

    if var_name == "has_resource":
        return {"services__isnull": not var_value}

    if var_name == "has_resource_reporting":
        return {"reporting_resources__isnull": not var_value}

    if var_name == "has_images_reporting":
        return {"reporting_files__isnull": not var_value}

    if var_name == "has_rdo":
        return {"reporting_multiple_daily_reports__isnull": not var_value}

    if var_name == "has_parent":
        return {"parent__isnull": not var_value}

    if var_name == "reporting_quality_samples":
        return {"reportings_quality_samples__isnull": not var_value}

    if var_name == "quality_sample_quality_assays":
        return {"reporting_quality_assays__isnull": not var_value}

    return {var_name: var_value}


def convert_conditions_to_query_params(conditions: dict):
    try:
        if type(conditions) is not dict:
            raise serializers.ValidationError(
                "kartado.error.record_panel.record_panel_conditions_field_needs_to_be_a_dict"
            )

        for oper, value in conditions.items():
            if oper in ["==", "!=", "in", "not in", "<", ">"]:
                if isinstance(value[0], dict):
                    var_name = value[0]["var"]
                    var_value = value[1]
                else:
                    var_name = value[1]["var"]
                    var_value = value[0]

                if "form_data" in var_name:
                    var_name = "form_data__" + var_name.split("form_data_")[1]

                if oper == "==":
                    condition = handle_custom_filters(var_name, var_value)
                    if var_name == "service_is_done":
                        custom_filter = Q()
                        for k, v in condition.items():
                            custom_filter |= Q(**{k: v})
                        return Q(custom_filter)
                    return Q(**condition)
                elif oper == "!=":
                    condition = handle_custom_filters(var_name, var_value)
                    return ~Q(**condition)
                elif oper == "in":
                    if isinstance(var_value, list) and len(var_value) > 1:
                        non_empty_values = [val for val in var_value if val]
                        if not non_empty_values:
                            return Q()
                        conditions = [
                            Q(**{"{}__icontains".format(var_name): val})
                            for val in non_empty_values
                        ]
                        return reduce(OR, conditions)
                    elif isinstance(var_value, list) and len(var_value) == 1:
                        if not var_value[0]:
                            return Q()
                        condition = {"{}__icontains".format(var_name): var_value[0]}
                        return Q(**condition)
                    else:
                        if not var_value:
                            return Q()
                        condition = {"{}__icontains".format(var_name): var_value}
                        return Q(**condition)
                elif oper == "not in":
                    if isinstance(var_value, list) and len(var_value) > 1:
                        non_empty_values = [val for val in var_value if val]
                        if not non_empty_values:
                            return Q()
                        conditions = [
                            ~Q(**{"{}__icontains".format(var_name): val})
                            for val in non_empty_values
                        ]
                        return reduce(AND, conditions)
                    elif isinstance(var_value, list) and len(var_value) == 1:
                        if not var_value[0]:
                            return Q()
                        condition = {"{}__icontains".format(var_name): var_value[0]}
                        return ~Q(**condition)
                    else:
                        if not var_value:
                            return Q()
                        condition = {"{}__icontains".format(var_name): var_value}
                        return ~Q(**condition)
                elif oper == "<":
                    condition = {"{}__lt".format(var_name): var_value}
                    return Q(**condition)
                elif oper == ">":
                    condition = {"{}__gt".format(var_name): var_value}
                    return Q(**condition)
                elif oper == "<=":
                    condition = {"{}__lte".format(var_name): var_value}
                    return Q(**condition)
                elif oper == ">=":
                    condition = {"{}__gte".format(var_name): var_value}
                    return Q(**condition)
                else:
                    return None
            elif oper in ["and", "or"]:
                # Convert all operands
                converted_query_params = [
                    convert_conditions_to_query_params(operand) for operand in value
                ]

                # Filter out falsy values
                converted_query_params = [
                    operand for operand in converted_query_params if operand
                ]

                if oper == "and":
                    return reduce(
                        AND,
                        converted_query_params,
                    )
                elif oper == "or":
                    return reduce(
                        OR,
                        converted_query_params,
                    )
                else:
                    return None
            else:
                return None

    except Exception as e:
        sentry_sdk.capture_exception(e)
        raise serializers.ValidationError(
            "kartado.error.record_panel.problem_found_while_converting_conditions_to_query"
        )


def apply_conditions_to_query(
    conditions: dict, queryset: QuerySet, menu: RecordMenu = None, default_to_empty=True
) -> QuerySet:
    """
    Apply the RecordPanel conditions and returns a filtered queryset

    Args:
        conditions: Conditions dict with the logic used for filtering
        queryset: The queryset to be filtered
        menu (RecordMenu, optional): Limit the results to items related to the menu if not None. Defaults to None.
        default_to_empty (bool, optional): If conditions cannot be applied should we return
        an empty queryset or the input queryset?. Defaults to True.

    Raises:
        serializers.ValidationError: record_panel_conditions_is_limited_to_<model_name>_fields
        serializers.ValidationError: record_panel_conditions_field_requires_a_valid_conditions_object

    Returns:
        result_queryset: Filtered queryset according to the conditions or the configured fallback behaviour
        if the conditions cannot be applied.
        The configured fallback behaviour is either returning an empty queryset or the same received input queryset.
    """

    model_name = queryset.model.__name__

    if conditions and "logic" in conditions:
        query_params = convert_conditions_to_query_params(conditions["logic"])
        try:
            return (
                queryset.filter(query_params, menu=menu)
                if menu
                else queryset.filter(query_params)
            )
        except FieldError as e:
            sentry_sdk.capture_exception(e)
            snake_case_name = to_snake_case(model_name)
            raise serializers.ValidationError(
                f"kartado.error.record_panel.record_panel_conditions_is_limited_to_{snake_case_name}_fields"
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)
            raise serializers.ValidationError(
                "kartado.error.record_panel.record_panel_conditions_field_requires_a_valid_conditions_object"
            )
    elif default_to_empty is False:
        return queryset.filter(menu=menu) if menu else queryset
    else:
        return queryset.none()


def get_color_from_api_name(api_name, custom_options):
    condition_field = get_obj_from_path(
        custom_options, "company__fields__condition__selectoptions__options"
    )
    try:
        condition_option = next(
            a for a in condition_field if get_obj_from_path(a, "apiname") == api_name
        )
    except Exception:
        return ""
    return condition_option["color"]


def get_color_from_display_name(display_name, custom_options):
    condition_field = get_obj_from_path(
        custom_options, "company__fields__condition__selectoptions__options"
    )
    try:
        condition_option = next(
            a for a in condition_field if get_obj_from_path(a, "name") == display_name
        )
    except Exception:
        return ""
    return condition_option["color"]


def get_field_display_name_from_api_name(occ_type, field_name):
    field_display_name = None
    for field in occ_type.form_fields["fields"]:
        if to_snake_case(get_obj_from_path(field, "apiname") or "") == field_name:
            field_display_name = get_obj_from_path(field, "displayname")
            break
    return field_display_name


def handle_reading_notification(
    occ_record: OccurrenceRecord,
    notification_area: str,
):
    """
    Handle common logic for debouce data on reading notifications for signals

    Args:
        occ_record (OccurrenceRecord): The reading instance
        notification_area (str): The notification area (ex: `"auscultacao.novas_leituras_validadas"`)
    """

    DASH_URL_TEMPLATE = (
        settings.FRONTEND_URL
        + "/#/SharedLink/Dashboard/?tab=customDashboard&uuid={}&company={}"
    )
    READING_URL_TEMPLATE = (
        settings.FRONTEND_URL + "/#/SharedLink/OccurrenceRecord/{}/show"
    )

    form_data = occ_record.form_data
    condition = form_data.get("condition", None)
    reading_url = READING_URL_TEMPLATE.format(occ_record.uuid)
    result_api_name = (
        get_obj_from_path(occ_record.occurrence_type.form_fields, "resultapiname")
        or "reading"
    )
    reference_api_names = get_obj_from_path(
        occ_record.occurrence_type.form_fields, "refapinames"
    )
    reference_values = []

    # Find all UserNotification instances related to the area
    usr_notif_instances = UserNotification.objects.filter(
        notification=notification_area,
        companies=occ_record.company,
    ).only("debounce_data")

    reading_data = (
        {
            "value": form_data.get(result_api_name, None),
            "field_name": get_field_display_name_from_api_name(
                occ_record.occurrence_type, result_api_name
            ),
            "url": reading_url,
            "observation": form_data.get("notes", None),
        }
        if result_api_name in form_data
        else None
    )

    for api_name in reference_api_names:
        try:
            reference_field = next(
                a
                for a in occ_record.occurrence_type.form_fields["fields"]
                if get_obj_from_path(a, "apiname") == api_name
            )
        except Exception:
            continue

        reference_values.append(
            {
                "name": reference_field["displayName"],
                "value": form_data.get(to_snake_case(api_name), None),
                "color": get_color_from_api_name(
                    api_name, occ_record.company.custom_options
                ),
            }
        )

    # Default debounce_data item
    data = {
        "condition": condition,
        "condition_color": get_color_from_display_name(
            condition, occ_record.company.custom_options
        ),
        "reading": reading_data,
        "instrument": None,  # Set only if there's an instrument
        "custom_dashboards": None,  # Set only if there are custom dashs for the instrument
        "company_id": str(occ_record.company.pk),
        "reference_values": reference_values,
    }

    # Handle instrument data
    instrument_id = form_data.get("instrument", None)
    instrument = (
        OccurrenceRecord.objects.get(uuid=instrument_id) if instrument_id else None
    )
    if instrument:
        instrument_url = (
            settings.FRONTEND_URL
            + "/#/SharedLink/OccurrenceRecord/{}?company={}".format(
                instrument.uuid, instrument.company.uuid
            )
        )

        # Build instrument display name
        company_name = instrument.company.name if instrument.company else None
        operational_position_value = instrument.form_data.get(
            "operational_position", None
        )
        operational_position_field = next(
            (
                field
                for field in get_obj_from_path(
                    instrument.occurrence_type.form_fields, "fields"
                )
                if field.get("apiName", None) == "operationalPosition"
            ),
            None,
        )
        operational_position = next(
            option["name"]
            for option in get_obj_from_path(
                operational_position_field, "selectoptions__options"
            )
            if option["value"] == operational_position_value
        )
        occ_type_name = (
            instrument.occurrence_type.name if instrument.occurrence_type else None
        )
        code = instrument.form_data.get("code", None)

        instrument_data = (
            {
                "name": " - ".join(
                    filter(
                        None,
                        [
                            company_name,
                            operational_position,
                            occ_type_name,
                            code,
                        ],
                    )
                ),
                "url": instrument_url,
            }
            if "code" in instrument.form_data
            else None
        )

        data["instrument"] = instrument_data

        # Custom dashboards related to instrument
        custom_dashs = CustomDashboard.objects.filter(instrument_records=instrument)

        custom_dashboards_data = (
            [
                {
                    "name": custom_dash.name,
                    "url": DASH_URL_TEMPLATE.format(
                        custom_dash.uuid, custom_dash.company.uuid
                    ),
                }
                for custom_dash in custom_dashs
            ]
            if custom_dashs
            else None
        )

        data["custom_dashboards"] = custom_dashboards_data

    add_debounce_data(usr_notif_instances, data)


def handle_record_panel_show(
    show_model, instance, show_flag, request_user, use_order=False, menu=None
):
    model_name_snake_case = to_snake_case(show_model.__name__)

    if type(show_flag) is bool:
        if menu:
            # It will only enter this for RecordPanelShowList
            user_query = show_model.objects.filter(user=request_user, panel__menu=menu)
        else:
            user_query = show_model.objects.filter(user=request_user)

        next_order = None
        if use_order:
            next_order = max(user_query.values_list("order", flat=True), default=0) + 1

        user_panel_query = user_query.filter(panel=instance)

        if show_flag:
            # If instance doesn't exist already, create it
            if not user_panel_query:
                try:
                    kwargs = {"panel": instance, "user": request_user}

                    if next_order:
                        kwargs["order"] = next_order

                    show_model.objects.create(**kwargs)
                except Exception as e:
                    sentry_sdk.capture_exception(e)
                    raise serializers.ValidationError(
                        f"kartado.error.{model_name_snake_case}.{model_name_snake_case}_could_not_be_created"
                    )
        else:
            # If instance exists already, delete it
            if user_panel_query:
                try:
                    user_panel_query.delete()
                except Exception as e:
                    sentry_sdk.capture_exception(e)
                    raise serializers.ValidationError(
                        f"kartado.error.{model_name_snake_case}.{model_name_snake_case}_could_not_be_deleted"
                    )

        # Rebalance after managing the visibility of a panel
        if show_model == RecordPanelShowList:
            rebalance_visible_panels_orders(
                user_id=str(request_user.uuid),
                company_id=str(instance.company_id),
                menu_id=str(menu.uuid) if menu is not None else None,
            )
    elif show_flag is not None:
        raise serializers.ValidationError(
            "kartado.error.record_panel.show_in_list_attribute_should_be_a_boolean"
        )


def add_occurrence_record_changes_debounce_data(
    instance: OccurrenceRecord, created=False, added_services_ids: Iterable[str] = []
):
    """
    Helper meant to aid in both "informacoes_sobre_registros" notification
    scenarios: OccurrenceRecord creation & update via signal and OccurrenceRecord
    services update via ChangeServiceOrder endpoint.

    Groups results of multiple Company instances.

    Args:
        instance (OccurrenceRecord): The instance being processed
        created (bool, optional): If the OccurrenceRecord was just created. Defaults to False.
        added_services_ids (Iterable[str], optional): List of IDs of the added services. Defaults to [].
    """

    NOTIFICATION_AREA = "registros.informacoes_sobre_registros"

    # NOTE: We'll use custom debounce logic to handle duplicates
    user_notifs = UserNotification.objects.filter(
        notification=NOTIFICATION_AREA,
        companies=instance.company,
    )

    if not user_notifs:
        logging.info(
            "No UserNotification configured to receive OccurrenceRecord updates"
        )
    else:
        # Essential info
        occ_record_id = str(instance.pk)
        number = instance.number
        created_by = instance.created_by.get_full_name() if instance.created_by else ""
        history_user = instance.historicaloccurrencerecord.first().history_user
        edited_by = history_user.get_full_name() if history_user else ""
        occurrence_type = (
            instance.occurrence_type.name if instance.occurrence_type else ""
        )
        url = "{}/#/SharedLink/OccurrenceRecord/{}/show?company={}".format(
            settings.FRONTEND_URL, str(instance.uuid), str(instance.company.pk)
        )

        # Get kind
        try:
            occ_kind = instance.occurrence_type.occurrence_kind
            possible_path = (
                "occurrencetype__fields__occurrencekind__selectoptions__options"
            )
            options = get_obj_from_path(instance.company.custom_options, possible_path)
            kind_translation = {item["value"]: item["name"] for item in options}
            kind = kind_translation[occ_kind]
        except Exception:
            kind = ""

        # Get services
        if created and instance.service_orders.exists():
            services = instance.service_orders.all()
        elif added_services_ids:
            services = instance.service_orders.filter(uuid__in=added_services_ids)
        else:
            services = None

        # Serialize services
        added_services = {}
        if services:
            for service in services:
                # Get GUT
                try:
                    gut = (
                        int(service.priority["seriousness"])
                        * int(service.priority["trend"])
                        * int(service.priority["urgency"])
                    )
                except Exception:
                    gut = ""

                # Get firms
                firms = (
                    [
                        action.firm.name
                        for action in service.actions.all()
                        if action.firm
                    ]
                    if service.actions.exists()
                    else []
                )

                # Create the comma separated string if more than one item
                if firms:
                    firm_list = ", ".join(firms) if len(firms) > 1 else firms.pop()
                else:
                    firm_list = ""

                service_url = "{}/#/SharedLink/ServiceOrder/{}/show?company={}".format(
                    settings.FRONTEND_URL,
                    str(service.uuid),
                    str(service.company.pk),
                )

                service_id = str(service.pk)
                added_services[service_id] = {
                    "number": service.number,
                    "occ_number": number,
                    "description": service.description,
                    "occurrence_record_count": service.so_records.count(),
                    "created_by": service.created_by.get_full_name(),
                    "firms": firm_list,
                    "gut": gut,
                    "url": service_url,
                    "occ_url": url,
                }

        # Dedup and debounce
        # NOTE: Using custom debounce logic because of unusual data structure and requirements
        upd_usr_notifs = []
        for user_notif in user_notifs:
            debounce_data = user_notif.debounce_data

            if not debounce_data:
                debounce_data = {}

            # Get already debounce record with that ID (if exists)
            deb_occ_record = debounce_data.get(occ_record_id, None)

            # If the record is already present
            if deb_occ_record:
                # If present but not set as updated, do that
                if deb_occ_record["created"] and not deb_occ_record["updated"]:
                    deb_occ_record["updated"] = True

                # Updateable fields
                deb_occ_record["kind"] = kind
                deb_occ_record["type"] = occurrence_type
                deb_occ_record["edited_by"] = edited_by

                # Check if new services were added
                if deb_occ_record["services"] and added_services:
                    unique_services = {
                        service_id: service_data
                        for service_id, service_data in added_services.items()
                        if service_id not in deb_occ_record["services"]
                    }
                    deb_occ_record["services"].update(unique_services)
                elif added_services:
                    deb_occ_record["services"] = added_services

                debounce_data[occ_record_id] = deb_occ_record
            # If the record is not present, add to the debounce_data
            else:
                debounce_data_item = {
                    "number": number,
                    "kind": kind,
                    "type": occurrence_type,
                    "created_by": created_by,
                    "edited_by": edited_by,
                    "url": url,
                    "services": added_services,
                    # Determine if it's a create or update debounce item
                    "created": created,
                    "updated": not created,
                }
                debounce_data[occ_record_id] = debounce_data_item

            # Finally, add the updated data to the instance's field and queue the bulk update
            user_notif.debounce_data = debounce_data
            upd_usr_notifs.append(user_notif)

        # Bulk update the debounce_data of all queued instances
        bulk_update(upd_usr_notifs, update_fields=["debounce_data"])
