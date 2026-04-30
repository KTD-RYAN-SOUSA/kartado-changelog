import calendar
import uuid
from collections import Counter
from curses.ascii import isdigit
from datetime import datetime, timedelta

import pytz
from arrow import Arrow
from dateutil import parser, relativedelta
from django.contrib.postgres.aggregates.general import ArrayAgg
from django.db.models import Case, Count, DurationField, ExpressionWrapper, F, Q, When
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from apps.companies.models import Company, Firm
from apps.locations.models import City, Location
from apps.occurrence_records.models import OccurrenceType, OccurrenceTypeSpecs
from apps.occurrence_records.views import get_occurrence_record_queryset
from apps.reportings.views import ReportingFilter, get_reporting_queryset
from apps.resources.serializers import ContractSerializer
from apps.resources.views import get_contract_queryset
from apps.service_orders.const import resource_approval_status, status_types
from apps.service_orders.models import (
    Procedure,
    ProcedureResource,
    ServiceOrderActionStatus,
    ServiceOrderActionStatusSpecs,
    ServiceOrderResource,
)
from apps.service_orders.views import (
    get_measurement_bulletin_queryset,
    get_procedure_queryset,
    get_procedure_resource_queryset,
    get_service_order_action_queryset,
    get_service_order_queryset,
    get_service_order_resource_queryset,
)
from helpers.apps.dashboard_reporting import (
    RainData,
    ReportingCount,
    ReportingCountRoad,
)
from helpers.as_of import first_histories
from helpers.dates import date_tz, get_dates_by_frequency
from helpers.error_messages import error_message
from helpers.filters import KeyFilter
from helpers.permissions import PermissionManager
from helpers.strings import get_obj_from_path, get_random_color, is_valid_uuid


def list_range_filter(name):
    def apply_filter(qs, value):
        if not value:
            return qs

        values = value.split(",")

        if len(values) % 2 != 0:
            raise Exception("O Filtro deve ter um tamanho total par")

        min_name = name + "__gte"
        max_name = name + "__lte"

        for i in range(0, len(values), 2):
            new_filter = {min_name: values[i], max_name: values[i + 1]}
            if i == 0:
                queryset = qs.filter(**new_filter)
            else:
                queryset = queryset | qs.filter(**new_filter)

        return queryset.distinct()

    return apply_filter


def execute_filters(filter_params, model, queryset):
    filter_dict = {
        "OccurrenceRecord": {
            "date_after": "created_at__gte",
            "date_before": "created_at__lte",
            "occurrence_type": "occurrence_type",
            "occurrence_kind": "occurrence_type__occurrence_kind",
            "status": "status",
            "firm_filter": "firm__uuid",
            "firm_is_internal": "firm__is_company_team",
            "city": "city",
            "location": "location",
            "place_on_dam": "place_on_dam",
            "uf_code": "uf_code",
        },
        "Procedure": {
            "date_after": "created_at__gte",
            "date_before": "created_at__lte",
            "firm_filter": "firm__uuid",
            "firm_is_internal": "firm__is_company_team",
            "occurrence_type": "action__service_order__so_records__occurrence_type__uuid",
            "contract": "procedure_resources__service_order_resource__contract",
        },
        "ProcedureResource": {
            "date_after": "approval_date__gte",
            "date_before": "approval_date__lte",
            "additional_control": "service_order_resource__additional_control",
            "additional_control_model": "service_order_resource__additional_control_model",
            "firm_filter": "service_order_resource__contract__firm",
            "contract": "service_order_resource__contract",
            # "subcompany": "firm__subcompany__uuid",
            "subcompany": "service_order_resource__contract__subcompany__uuid",
        },
        "ServiceOrderAction": {
            "date_after": "opened_at__gte",
            "date_before": "opened_at__lte",
            "firm_filter": "procedures__firm",
            "contract": "procedures__procedure_resources__service_order_resource__contract",
        },
        "ServiceOrder": {
            "date_after": "opened_at__gte",
            "date_before": "opened_at__lte",
            "contract": "contracts",
            "subcompany": "contracts__subcompany__uuid",
        },
        "ServiceOrderResource": {
            "date_after": "creation_date__gte",
            "date_before": "creation_date__lte",
            "additional_control": "additional_control",
            "additional_control_model": "additional_control_model",
            "firm_filter": "contract__firm",
            "contract": "contract",
            "subcompany": "contract__subcompany__uuid",
        },
        "Reporting": {
            # Dates
            "date_after": "created_at__gte",
            "date_before": "created_at__lte",
            "created_at_after": "created_at__gte",
            "created_at_before": "created_at__lte",
            "found_at_after": "found_at__gte",
            "found_at_before": "found_at__lte",
            "updated_at_after": "updated_at__gte",
            "updated_at_before": "updated_at__lte",
            "executed_at_after": "executed_at__gte",
            "executed_at_before": "executed_at__lte",
            "due_at_after": "due_at__gte",
            "due_at_before": "due_at__lte",
            # Model fields
            "range_multi__km": list_range_filter("km"),
            "direction": "direction",
            "lane": "lane",
            # Relationships
            "uf_code": "road__uf",
            "occurrence_type": "occurrence_type__uuid",
            "occurrence_kind": "occurrence_type__occurrence_kind",
            "firm": "firm__uuid",
            "status": "status__uuid",
            "job": "job__uuid",
            "created_by": "created_by__uuid",
            "road": "road__uuid",
            "road_name": "road_name",
            "lot": "lot",
            "subcompany": "firm__subcompany__uuid",
        },
        "MeasurementBulletin": {
            "date_after": "measurement_date__gte",
            "date_before": "measurement_date__lte",
            "firm_filter": "contract__firm__uuid",
            "additional_control": "bulletin_resources__service_order_resource__additional_control",
            "additional_control_model": "bulletin_resources__service_order_resource__additional_control_model",
            "contract": "contract",
            "subcompany": "contract__subcompany",
        },
        "Firm": {
            "company": "company",
            "firm_filter": "uuid",
            "firm_is_internal": "is_company_team",
            "additional_control": "is_company_team",
        },
    }

    filters = {}
    for item in filter_dict[model]:
        try:
            if filter_params[item]:
                if isinstance(filter_dict[model][item], str):
                    if len(filter_params[item].split(",")) > 1:
                        filters[filter_dict[model][item] + "__in"] = filter_params[
                            item
                        ].split(",")
                    elif filter_params[item] == "true":
                        filters[filter_dict[model][item]] = True
                    elif filter_params[item] == "false":
                        filters[filter_dict[model][item]] = False
                    else:
                        filters[filter_dict[model][item]] = filter_params[item]
                elif callable(filter_dict[model][item]):
                    queryset = filter_dict[model][item](queryset, filter_params[item])
        except Exception:
            pass

    valid_date_fields = [
        "approval_date__gte",
        "approval_date__lte",
        "created_at__gte",
        "created_at__lte",
        "opened_at__gte",
        "opened_at__lte",
        "creation_date__gte",
        "creation_date__lte",
        "found_at__gte",
        "found_at__lte",
        "updated_at__gte",
        "updated_at__lte",
        "executed_at__gte",
        "executed_at__lte",
        "measurement_date__gte",
        "measurement_date__lte",
        "due_at__gte",
        "due_at__lte",
    ]

    # Fiz timezone in date filters
    for key, value in filters.items():
        if key not in valid_date_fields:
            continue
        try:
            date = date_tz(value, end_of_the_day=("__lte" in key))
        except Exception:
            continue
        filters[key] = date

    return queryset.filter(**filters).distinct()


def filter_by_date(list_of_objects, attribute_name, date, current_year, greater_zero):
    if greater_zero:
        return [
            item
            for item in list_of_objects
            if (
                (getattr(item, attribute_name))
                and (int(getattr(item, attribute_name).strftime("%m")) == (date))
                and (
                    int(getattr(item, attribute_name).strftime("%Y")) == (current_year)
                )
            )
        ]
    else:
        return [
            item
            for item in list_of_objects
            if (
                (getattr(item, attribute_name))
                and (int(getattr(item, attribute_name).strftime("%m")) == (date + 12))
                and (
                    int(getattr(item, attribute_name).strftime("%Y"))
                    == (current_year - 1)
                )
            )
        ]


def safe_increment(transformer_dict, first_key, second_key):
    if first_key in transformer_dict.keys():
        if second_key in transformer_dict[first_key].keys():
            transformer_dict[first_key][second_key] += 1
        else:
            transformer_dict[first_key][second_key] = 1
    else:
        transformer_dict[first_key] = {second_key: 1}

    return transformer_dict


def get_contracts_dates(contracts, request, date_format="date"):
    try:
        contract_ids = request.query_params["contract"]
        if not contract_ids:
            raise Exception
        contracts = contracts.filter(uuid__in=contract_ids.split(","))
        contracts_dates_sets = list(
            contracts.values_list("contract_start", "contract_end").distinct()
        )
        contracts_dates = [item for t in contracts_dates_sets for item in t]
        first_date = min(contracts_dates)
        last_date = max(contracts_dates)
    except Exception:
        if "date_after" in request.query_params:
            try:
                first_date = parser.parse(request.query_params["date_after"]).replace(
                    tzinfo=pytz.UTC
                )
            except Exception:
                raise ValidationError("Data inválida")
        else:
            first_date = (
                datetime.now() - relativedelta.relativedelta(months=11)
            ).replace(tzinfo=pytz.UTC)

        if "date_before" in request.query_params:
            try:
                last_date = parser.parse(request.query_params["date_before"]).replace(
                    tzinfo=pytz.UTC
                )
            except Exception:
                raise ValidationError("Data inválida")
        else:
            last_date = datetime.now().replace(tzinfo=pytz.UTC)

        contracts = contracts.filter(
            contract_end__gte=first_date, contract_start__lte=last_date
        )
    if date_format == "datetime":
        return (
            contracts,
            datetime(first_date.year, first_date.month, first_date.day),
            datetime(last_date.year, last_date.month, last_date.day),
        )
    return contracts, first_date, last_date


class ResourceHistoryView(APIView):
    """
    View to show resources cost balance from the last 12 months.

    Parameters:
    resources (list): list of Resource ids - required
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        # Get parameters
        fields = ["resources", "company"]

        if not set(fields).issubset(self.request.query_params.keys()):
            return Response({"type": "ResourceHistory", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        # Make a list of resources ids
        try:
            resources_ids = [
                uuid.UUID(resource_id)
                for resource_id in request.query_params.get("resources").split(",")
            ]
        except ValueError:
            return Response({"type": "ResourceHistory", "attributes": []})

        # Get suitable procedure resources from past 12 months
        procedure_resources = ProcedureResource.objects.filter(
            resource_id__in=resources_ids,
            resource__company_id=company_id,
            procedure__created_at__gte=datetime.now() - timedelta(days=365),
        ).prefetch_related("resource", "procedure", "resource__company")

        # Execute filters
        model = "ProcedureResource"

        procedure_resources = execute_filters(
            request.query_params, model, procedure_resources
        )

        date_filter = {}
        resource_history = []

        last_date = datetime.now()
        first_date = datetime.now() - timedelta(days=365)

        date_list = [
            item.date() for item in Arrow.range("month", first_date, last_date)
        ]

        for date in date_list:
            key = str(date.month) + "/" + str(date.year)
            # get procedure resources by month
            date_filter[key] = [
                item
                for item in procedure_resources
                if (
                    (int(item.procedure.created_at.strftime("%m")) == (date.month))
                    and (int(item.procedure.created_at.strftime("%Y")) == (date.year))
                )
            ]

            resource_history.append(
                {"month": key.split("/")[0], "year": key.split("/")[1]}
            )
            for resource in resources_ids:
                if date_filter[key]:
                    resource_by_month = [
                        item
                        for item in date_filter[key]
                        if item.resource.uuid == resource
                    ]
                    values = [item.total_price for item in resource_by_month]
                    amount = [item.amount for item in resource_by_month]
                    if sum(amount) != 0:
                        cost = sum(values) / sum(amount)
                    else:
                        cost = 0
                    if resource_by_month:
                        name = (
                            resource_by_month[0].resource.name
                            + " ("
                            + resource_by_month[0].resource.unit
                            + ")"
                        )
                        resource_history[-1][name] = cost

        return Response({"type": "ResourceHistory", "attributes": resource_history})


class RecordStatusView(APIView):
    """
    View to show count of status in records by firm.
    The status need kind="OCCURRENCE_RECORD_STATUS"
    The firm comes from first record_history entry

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        if "company" not in request.query_params:
            return Response({"type": "RecordStatus", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="OccurrenceRecord"
        )

        records = get_occurrence_record_queryset(
            "list", request, permissions
        ).prefetch_related("created_by", "status", "firm")

        model = "OccurrenceRecord"
        records = execute_filters(request.query_params, model, records)

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="Dashboard"
        )

        allowed_queryset = permissions.get_allowed_queryset()
        if ("all" not in allowed_queryset) and ("self" not in allowed_queryset):
            return Response({"type": "RecordStatus", "attributes": []})

        if "self" in allowed_queryset:
            records = records.filter(firm__users=request.user).distinct()

        firms = Firm.objects.filter(
            users__records_created__in=records, company__uuid=company_id
        ).distinct()
        firms = execute_filters(request.query_params, "Firm", firms).order_by("name")

        company_status = ServiceOrderActionStatus.objects.filter(
            companies=company_id, kind="OCCURRENCE_RECORD_STATUS"
        )
        status_specs = (
            ServiceOrderActionStatusSpecs.objects.filter(
                company__uuid=company_id, status__in=company_status
            )
            .prefetch_related("status")
            .values("status_id", "status__name", "color")
        )

        colors = {item["status__name"]: item["color"] for item in status_specs}

        records_annotated = records.prefetch_related("created_by__user_firms").annotate(
            user_firms=ArrayAgg("created_by__user_firms", distinct=True)
        )

        records_list = [
            {
                "user_firms": item.user_firms,
                "status_id": item.status_id,
                "reviews": item.reviews,
            }
            for item in records_annotated
        ]

        data = []
        for firm in firms:
            item_dict = {"firm": firm.name}
            records_by_firm = list(
                filter(lambda item: firm.uuid in item["user_firms"], records_list)
            )

            item_dict["Rev"] = sum([item["reviews"] for item in records_by_firm])

            counts = dict(Counter([item["status_id"] for item in records_by_firm]))

            total = 0
            for item in status_specs:
                count = counts.get(item["status_id"], 0)
                item_dict[item["status__name"]] = count
                total += count

            item_dict["Total"] = total
            data.append(item_dict)

        attributes = {"data": data, "colors": colors}

        return Response({"type": "RecordStatus", "attributes": attributes})


class ProcedureStatusView(APIView):
    """
    View to show count of procedures by firm.
    The procedures are separated in on_time, done_late, running and late
    depending on the procedure deadline.

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)
    firm (uuid)
    occurrence_type (uuid)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        if "company" not in self.request.query_params:
            return Response({"type": "ProcedureStatus", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        firms = Firm.objects.filter(company__uuid=company_id).order_by("name")
        procedures = Procedure.objects.filter(firm__in=firms).prefetch_related("firm")

        model = "Procedure"
        procedures = execute_filters(request.query_params, model, procedures)

        attributes = []
        transformer_dict = {}
        for procedure in procedures:
            if procedure.done_at:
                if procedure.done_at <= procedure.deadline:
                    transformer_dict = safe_increment(
                        transformer_dict, procedure.firm.name, "on_time"
                    )
                else:
                    transformer_dict = safe_increment(
                        transformer_dict, procedure.firm.name, "done_late"
                    )
            else:
                if procedure.deadline.replace(tzinfo=pytz.UTC) > datetime.now().replace(
                    tzinfo=pytz.UTC
                ):
                    transformer_dict = safe_increment(
                        transformer_dict, procedure.firm.name, "running"
                    )
                else:
                    transformer_dict = safe_increment(
                        transformer_dict, procedure.firm.name, "late"
                    )

        for firm in transformer_dict.keys():
            attributes.append({"firm": firm})
            total = 0
            for status in ["on_time", "done_late", "late", "running"]:
                if status in transformer_dict[firm].keys():
                    attributes[-1][status] = transformer_dict[firm][status]
                    total += transformer_dict[firm][status]
                else:
                    attributes[-1][status] = 0
            attributes[-1]["Total"] = total

        return Response({"type": "ProcedureStatus", "attributes": attributes})


class Top5RecordLocalView(APIView):
    """
    View to show count of records by Location or City.
    Show just the top 5 counting.

    Parameters:
    company (uuid) - required
    local_type ("cities" or "locations") - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        fields = ["local_type", "company"]

        if not set(fields).issubset(self.request.query_params.keys()):
            return Response({"type": "Top5RecordLocal", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))
        local_type = request.query_params.get("local_type")

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="OccurrenceRecord"
        )

        records = get_occurrence_record_queryset(
            "list", request, permissions
        ).prefetch_related("location", "city")

        model = "OccurrenceRecord"
        records = execute_filters(request.query_params, model, records)

        if local_type == "cities":
            places = (
                City.objects.filter(occurrencerecord__in=records)
                .annotate(num_records=Count("occurrencerecord"))
                .order_by("-num_records")[:5]
            )

        elif local_type == "locations":
            places = (
                Location.objects.filter(occurrencerecord__in=records)
                .annotate(num_records=Count("occurrencerecord"))
                .order_by("-num_records")[:5]
            )

        attributes = []
        for place in places:
            attributes.append({"name": place.name, "value": place.num_records})

        return Response({"type": "Top5RecordLocal", "attributes": attributes})


class RecordNatureView(APIView):
    """
    View to show count of records by kind from the past 12 months.
    The kinds come from customOptions of Company

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        if "company" not in self.request.query_params:
            return Response({"type": "RecordNature", "attributes": []})
        company_id = uuid.UUID(request.query_params.get("company"))

        fields = ["date_after", "date_before"]

        date_list = []
        if not set(fields).issubset(self.request.query_params.keys()):
            # default dates
            first_date = datetime.now() - relativedelta.relativedelta(months=11)
            last_date = datetime.now()
        else:
            try:
                first_date = parser.parse(self.request.query_params["date_after"])
                last_date = parser.parse(self.request.query_params["date_before"])
            except Exception:
                raise ValidationError("As datas especificadas são inválidas")

        if not isinstance(first_date, datetime):
            first_date = datetime(first_date.year, first_date.month, first_date.day)
        if not isinstance(last_date, datetime):
            last_date = datetime(last_date.year, last_date.month, last_date.day)

        for month in Arrow.range("month", first_date, last_date):
            date_list.append(month.datetime)

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="OccurrenceRecord"
        )

        records = (
            get_occurrence_record_queryset("list", request, permissions)
            .filter(created_at__gte=first_date)
            .prefetch_related("occurrence_type", "company")
        )

        model = "OccurrenceRecord"
        records = execute_filters(request.query_params, model, records)

        try:
            company = Company.objects.get(pk=company_id)
            possible_path = (
                "occurrencerecord__fields__occurrencekind__selectoptions__options"
            )
            options = get_obj_from_path(company.custom_options, possible_path)
            types = {item["name"]: item["value"] for item in options}
        except Exception:
            types = {"Ocorrências": 1, "Requisições": 2, "Comunicações": 3}

        date_filter = {}
        attributes = []

        for date in date_list:
            key = str(date.month) + "/" + str(date.year)
            date_filter[key] = [
                item
                for item in records
                if (
                    (item.datetime)
                    and (int(item.datetime.strftime("%m")) == (date.month))
                    and (int(item.datetime.strftime("%Y")) == (date.year))
                )
            ]

            attributes.append({"month": key.split("/")[0], "year": key.split("/")[1]})

            for kind, order in types.items():
                kind_by_month = len(
                    [
                        item
                        for item in date_filter[key]
                        if item.occurrence_type
                        and int(item.occurrence_type.occurrence_kind) == int(order)
                    ]
                )
                attributes[-1][kind] = kind_by_month

        return Response({"type": "RecordNature", "attributes": attributes})


class RecordTypesView(APIView):
    """
    View to show count of records by types

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        if "company" not in self.request.query_params:
            return Response({"type": "RecordTypes", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="OccurrenceRecord"
        )

        records = get_occurrence_record_queryset(
            "list", request, permissions
        ).prefetch_related("occurrence_type")

        model = "OccurrenceRecord"
        records = execute_filters(request.query_params, model, records)

        records_types = (
            OccurrenceType.objects.filter(type_records__in=records)
            .annotate(num_records=Count("type_records"))
            .order_by("-num_records")
        )

        attributes = [
            {"name": item.name, "value": item.num_records} for item in records_types
        ]

        return Response({"type": "RecordTypes", "attributes": attributes})


class ActionStatusView(APIView):
    """
    View to show count of status in all actions

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        if "company" not in self.request.query_params:
            return Response({"type": "ActionStatus", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        permissions = PermissionManager(
            user=request.user,
            company_ids=company_id,
            model="ServiceOrderAction",
        )

        actions = get_service_order_action_queryset(
            "list", request, permissions
        ).prefetch_related("service_order_action_status")

        model = "ServiceOrderAction"
        actions = execute_filters(request.query_params, model, actions)

        action_status = (
            ServiceOrderActionStatus.objects.filter(
                action_status__in=actions, companies__in=[company_id]
            )
            .annotate(num_actions=Count("action_status"))
            .order_by("-num_actions")
        )

        attributes = [
            {"name": item.name, "value": item.num_actions} for item in action_status
        ]

        return Response({"type": "ActionStatus", "attributes": attributes})


class ServiceOrderCostView(APIView):
    """
    View to show count of service_orders from the last 12 months.
    Show by closed, opened or running.
    Also, show cost by month using total_price of approved procedure_resources.

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        if "company" not in request.query_params:
            return Response({"type": "ServiceOrderCost", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="Contract"
        )

        contracts = get_contract_queryset("list", request, permissions)

        contracts, first_date, last_date = get_contracts_dates(
            contracts, request, date_format="datetime"
        )

        date_list = []
        for month in Arrow.range("month", first_date, last_date):
            date_list.append(month.datetime)

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="ServiceOrder"
        )

        service_orders = get_service_order_queryset(
            "list", request, permissions
        ).filter(updated_at__gte=first_date)

        model = "ServiceOrder"
        service_orders = execute_filters(request.query_params, model, service_orders)

        filters_without_date = request.query_params.copy()
        try:
            filters_without_date.pop("date_after")
        except KeyError:
            pass
        try:
            filters_without_date.pop("date_before")
        except KeyError:
            pass

        permissions = PermissionManager(
            user=request.user,
            company_ids=company_id,
            model="ServiceOrderResource",
        )

        service_order_resources = (
            get_service_order_resource_queryset("list", request, permissions)
            .filter(contract__in=contracts)
            .prefetch_related("contract")
        )

        model = "ServiceOrderResource"
        service_order_resources = execute_filters(
            filters_without_date, model, service_order_resources
        )

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="ProcedureResource"
        )

        procedure_resources = (
            get_procedure_resource_queryset("list", request, permissions)
            .filter(
                service_order_resource__in=service_order_resources,
                approval_status=resource_approval_status.APPROVED_APPROVAL,
                approval_date__isnull=False,
            )
            .prefetch_related("procedure")
        )

        attributes = []
        accumulated = sum(
            [
                item.total_price
                for item in procedure_resources
                if item.approval_status == resource_approval_status.APPROVED_APPROVAL
                and item.approval_date
                < first_date.replace(tzinfo=item.approval_date.tzinfo)
            ]
        )

        for date in date_list:
            key = str(date.month) + "/" + str(date.year)
            closed_list = filter_by_date(
                service_orders, "closed_at", date.month, date.year, True
            )
            opened_list = filter_by_date(
                service_orders, "opened_at", date.month, date.year, True
            )
            running_list = filter_by_date(
                service_orders, "updated_at", date.month, date.year, True
            )
            not_created_in_this_month = [
                item
                for item in service_orders
                if (
                    (getattr(item, "opened_at"))
                    and (int(getattr(item, "opened_at").strftime("%m")) != (date.month))
                    and (int(getattr(item, "opened_at").strftime("%Y")) == (date.year))
                    and (getattr(item, "closed_at") is None)
                )
            ]

            closed = len(closed_list)
            opened = len(opened_list)
            running = len(running_list)

            created_and_not_closed = len(
                [item for item in opened_list if item not in closed_list]
            )
            not_created_and_updated = len(
                [item for item in not_created_in_this_month if item in running_list]
            )
            not_created_and_not_updated = len(
                [item for item in not_created_in_this_month if item not in running_list]
            )
            month_procedures = [
                item
                for item in procedure_resources
                if (
                    (int(item.approval_date.strftime("%m")) == (date.month))
                    and (int(item.approval_date.strftime("%Y")) == (date.year))
                )
            ]
            month_service_order_resources = [
                item
                for item in service_order_resources
                if item.contract and item.contract.contract_start <= date.date()
            ]

            cost = sum(
                [
                    item.total_price
                    for item in month_procedures
                    if item.approval_status
                    == resource_approval_status.APPROVED_APPROVAL
                ]
            )
            total_price = 0
            for resource in month_service_order_resources:
                try:
                    resource_total_price = resource.unit_price * resource.amount
                    if not isinstance(resource_total_price, (int, float)):
                        raise Exception()
                    total_price += resource_total_price
                except Exception:
                    continue

            accumulated += cost
            remaining = total_price - accumulated

            attributes.append(
                {
                    "month": key.split("/")[0],
                    "year": key.split("/")[1],
                    "not_closed": created_and_not_closed,
                    "updated": not_created_and_updated,
                    "not_updated": not_created_and_not_updated,
                    "closed": closed,
                    "opened": opened,
                    "running": running,
                    "cost": cost,
                    "accumulated": accumulated,
                    "remaining": remaining,
                }
            )

        return Response({"type": "ServiceOrderCost", "attributes": attributes})


class FirmPerformanceView(APIView):
    """
    Using status of procedures, show stats about procedures by firm.

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        if "company" not in request.query_params:
            return Response({"type": "FirmPerformance", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="OccurrenceRecord"
        )

        occ_records = get_occurrence_record_queryset(
            "list", request, permissions
        ).prefetch_related("created_by", "status")

        model = "OccurrenceRecord"
        occ_records = execute_filters(request.query_params, model, occ_records)

        first_history = first_histories(
            "occurrence_records", model, occ_records
        ).prefetch_related("firm")
        firms_old = Firm.objects.filter(
            uuid__in=first_history.values_list("firm_id").distinct(),
            company__uuid=company_id,
        )
        firms_old = execute_filters(request.query_params, "Firm", firms_old)

        metadata = Company.objects.get(uuid=company_id).metadata
        approve = metadata["extra_actions"]["approve"]["dest_status"]
        reject = metadata["extra_actions"]["reject"]["dest_status"]
        request_review_record = metadata["extra_actions"]["requestReview"][
            "dest_status"
        ]
        request_review_action = metadata["extra_actions"]["requestReviewAction"][
            "dest_status"
        ]

        firms = (
            Firm.objects.filter(company__uuid=company_id)
            .annotate(num_procedures=Count("procedure_firm"))
            .prefetch_related("users")
        )
        firms = execute_filters(request.query_params, "Firm", firms).order_by("name")

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="Procedure"
        )

        procedures = get_procedure_queryset(
            "list", request, permissions
        ).prefetch_related("firm")

        intime_procedures = procedures.filter(deadline__gte=F("done_at"))

        procedures_toreview = procedures.filter(
            service_order_action_status__in=[
                request_review_action,
                request_review_record,
            ]
        )

        model = "Procedure"

        intime_procedures = execute_filters(
            request.query_params, model, intime_procedures
        )

        procedures_toreview = execute_filters(
            request.query_params, model, procedures_toreview
        )

        attributes = []
        records = {}

        for firm in firms_old:
            records_by_firm = occ_records.filter(firm_id=firm.uuid).prefetch_related(
                "status"
            )

            # Get firm names
            firm_name = firm.name

            for record in records_by_firm:
                status_id = record.status.uuid

                # Increment values with a safe method
                records = safe_increment(records, firm_name, status_id)

        # Translate records to response format
        for firm in firms:
            attributes.append({"firm": firm.name})
            if firm.name in records.keys():
                ratified_records = []

                try:
                    ratified_records.append(records[firm.name][uuid.UUID(approve)])
                except KeyError:
                    ratified_records.append(0)

                try:
                    ratified_records.append(records[firm.name][uuid.UUID(reject)])
                except KeyError:
                    ratified_records.append(0)

                try:
                    confidence = ratified_records[0] / sum(ratified_records)
                except ZeroDivisionError:
                    confidence = 0

                try:
                    record_emission = (
                        sum(list(records[firm.name].values())) / firm.users.count()
                    )
                except ZeroDivisionError:
                    record_emission = 0

            else:
                confidence = 0
                record_emission = 0

            try:
                procedures_emission = firm.num_procedures / firm.users.count()
            except ZeroDivisionError:
                procedures_emission = 0

            try:
                quality = (
                    1
                    - len(
                        [
                            procedure
                            for procedure in procedures_toreview
                            if firm.uuid == procedure.firm.uuid
                        ]
                    )
                    / firm.num_procedures
                )
            except ZeroDivisionError:
                quality = 0

            try:
                punctuality = (
                    len(
                        [
                            procedure
                            for procedure in intime_procedures
                            if firm.uuid == procedure.firm.uuid
                        ]
                    )
                    / firm.num_procedures
                )
            except ZeroDivisionError:
                punctuality = 0

            attributes[-1]["confidence"] = confidence
            attributes[-1]["record_emission"] = record_emission
            attributes[-1]["procedures_emission"] = procedures_emission
            attributes[-1]["punctuality"] = punctuality
            attributes[-1]["quality"] = quality

        return Response({"type": "FirmPerformance", "attributes": attributes})


class ResourcesView(APIView):
    """
    View to show cumulative of created service_orders_resources and
    approved procedure_resources in the current year.

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        if "company" not in self.request.query_params:
            return Response({"type": "Resources", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        fields = ["date_after", "date_before"]

        date_list = []
        if not set(fields).issubset(self.request.query_params.keys()):
            # default dates
            first_date = datetime.now().replace(month=1, day=1)
            last_date = datetime.now().replace(month=12, day=31)
        else:
            try:
                first_date = parser.parse(self.request.query_params["date_after"])
                last_date = parser.parse(self.request.query_params["date_before"])
            except Exception:
                raise ValidationError("As datas especificadas são inválidas")

        for month in Arrow.range("month", first_date, last_date):
            date_list.append(month.datetime)

        action_resources = ServiceOrderResource.objects.filter(
            resource__company__uuid=company_id, creation_date__gte=first_date
        ).prefetch_related("serviceorderresource_procedures")

        model = "ServiceOrderResource"
        action_resources = execute_filters(
            request.query_params, model, action_resources
        )

        procedure_resources = ProcedureResource.objects.filter(
            resource__company__uuid=company_id, approval_date__gte=first_date
        )

        model = "ProcedureResource"
        procedure_resources = execute_filters(
            request.query_params, model, procedure_resources
        )

        attributes = []
        for date in date_list:
            key = str(date.month) + "/" + str(date.year)

            month_actions = [
                action_resource
                for action_resource in action_resources
                if (
                    (action_resource.creation_date)
                    and (action_resource.creation_date.month == (date.month))
                    and (action_resource.creation_date.year == (date.year))
                )
            ]

            month_procedures = [
                procedure_resource
                for procedure_resource in procedure_resources
                if (
                    (procedure_resource.approval_date)
                    and (procedure_resource.approval_date.month == (date.month))
                    and (procedure_resource.approval_date.year == (date.year))
                )
            ]

            actions_cost = sum(
                [
                    action_resource.serviceorderresource_procedures.order_by(
                        "approval_date"
                    )[0].unit_price
                    * action_resource.amount
                    if action_resource.serviceorderresource_procedures.order_by(
                        "approval_date"
                    ).exists()
                    else action_resource.unit_price * action_resource.amount
                    for action_resource in month_actions
                ]
            )
            procedures_cost = sum(
                [
                    procedure_resource.total_price
                    for procedure_resource in month_procedures
                    if procedure_resource.approval_status
                    == resource_approval_status.APPROVED_APPROVAL
                ]
            )

            attributes.append(
                {
                    "month": key.split("/")[0],
                    "year": key.split("/")[1],
                    "expected": actions_cost,
                    "executed": procedures_cost,
                }
            )

        return Response({"type": "Resources", "attributes": attributes})


class ContractSpendScheduleView(APIView):
    """
    View to show cumulative of created service_orders_resources and
    approved procedure_resources in the current year.

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        required_fields = ["company"]
        if not set(required_fields).issubset(request.query_params.keys()):
            return Response({"type": "Contract Spend Schedule", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="Contract"
        )

        contracts = get_contract_queryset("list", request, permissions)

        contracts, first_date, last_date = get_contracts_dates(
            contracts, request, date_format="datetime"
        )

        date_list = []
        for month in Arrow.range("month", first_date, last_date):
            date_list.append(month.datetime)

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="ProcedureResource"
        )

        procedure_resources = get_procedure_resource_queryset(
            "list", request, permissions
        ).filter(approval_date__gte=first_date)

        model = "ProcedureResource"
        procedure_resources = execute_filters(
            request.query_params, model, procedure_resources
        )

        attributes = []
        for date in date_list:
            key = str(date.month) + "/" + str(date.year)

            month_procedures = [
                procedure_resource
                for procedure_resource in procedure_resources
                if (
                    (procedure_resource.approval_date)
                    and (procedure_resource.approval_date.month == (date.month))
                    and (procedure_resource.approval_date.year == (date.year))
                )
            ]

            executed_month = sum(
                [
                    procedure_resource.total_price
                    for procedure_resource in month_procedures
                    if procedure_resource.approval_status
                    == resource_approval_status.APPROVED_APPROVAL
                ]
            )

            expected_month = 0
            for item in contracts:
                if item.spend_schedule and key in item.spend_schedule:
                    spend_schedule = item.spend_schedule[key]
                    if isinstance(spend_schedule, str) and isdigit(spend_schedule):
                        spend_schedule = float(spend_schedule)

                    if spend_schedule and not isinstance(spend_schedule, str):
                        expected_month += spend_schedule

            expected = (
                sum([item["expected_month"] for item in attributes]) + expected_month
            )

            executed = (
                sum([item["executed_month"] for item in attributes]) + executed_month
            )

            attributes.append(
                {
                    "date": date.strftime("%-m/%Y"),
                    "expected": expected,
                    "executed": executed,
                    "expected_month": expected_month,
                    "executed_month": executed_month,
                }
            )

        return Response({"type": "Contract Spend Schedule", "attributes": attributes})


class MeasurementBulletinsView(APIView):
    """
    View to show approved_value, pending_value and denied_value
    of approved and not approved procedure_resources from the past 12 months.
    Also, show the count of measurement_bulletins.

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        if "company" not in request.query_params:
            return Response({"type": "Measurement Bulletins", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="Contract"
        )

        contracts = get_contract_queryset("list", request, permissions)

        contracts, first_date, last_date = get_contracts_dates(
            contracts, request, date_format="datetime"
        )
        date_list = []
        for month in Arrow.range("month", first_date, last_date):
            date_list.append(month.datetime)

        filters_without_date = request.query_params.copy()
        try:
            filters_without_date.pop("date_after")
        except KeyError:
            pass
        try:
            filters_without_date.pop("date_before")
        except KeyError:
            pass

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="ProcedureResource"
        )

        procedure_resources = (
            get_procedure_resource_queryset("list", request, permissions)
            .filter(service_order_resource__contract__in=contracts)
            .prefetch_related("reporting")
        )

        model = "ProcedureResource"
        procedure_resources = execute_filters(
            filters_without_date, model, procedure_resources
        )

        permissions = PermissionManager(
            user=request.user,
            company_ids=company_id,
            model="MeasurementBulletin",
        )

        measurement_bulletins = (
            get_measurement_bulletin_queryset("list", request, permissions)
            .filter(contract__in=contracts)
            .annotate(num_bulletins=Count("uuid"))
        )

        model = "MeasurementBulletin"
        measurement_bulletins = execute_filters(
            filters_without_date, model, measurement_bulletins
        )

        # Since we should use the reporting found_at as reference for
        # everything, we create two dates to keep using the old structure that
        # default to the procedure_resource's dates, but use the reporting's
        # found_at date when it's available.
        procedure_resources = procedure_resources.annotate(
            ref_creation_date=Case(
                When(reporting__uuid__isnull=False, then=F("reporting__found_at")),
                default=F("creation_date"),
            ),
            ref_approval_date=Case(
                When(reporting__uuid__isnull=False, then=F("reporting__found_at")),
                default=F("approval_date"),
            ),
        )

        procedure_resources_list = [
            {
                "ref_creation_date": item.ref_creation_date,
                "ref_approval_date": item.ref_approval_date,
                "service_order_resource_id": item.service_order_resource_id,
                "total_price": item.total_price,
                "approval_status": item.approval_status,
            }
            for item in procedure_resources.distinct()
        ]

        measurement_bulletins_list = [
            {
                "num_bulletins": item.num_bulletins,
                "measurement_date": item.measurement_date,
            }
            for item in measurement_bulletins.distinct()
        ]

        attributes = []

        for date in date_list:
            key = str(date.month) + "/" + str(date.year)

            # Approved and denied
            month_approved = list(
                filter(
                    lambda item: item["ref_approval_date"]
                    and item["ref_approval_date"].month == date.month
                    and item["ref_approval_date"].year == date.year,
                    procedure_resources_list,
                )
            )

            approved_value = sum(
                [
                    procedure_resource["total_price"]
                    for procedure_resource in month_approved
                    if procedure_resource["approval_status"]
                    == resource_approval_status.APPROVED_APPROVAL
                ]
            )
            denied_value = sum(
                [
                    procedure_resource["total_price"]
                    for procedure_resource in month_approved
                    if procedure_resource["approval_status"]
                    == resource_approval_status.DENIED_APPROVAL
                ]
            )

            # Not approved
            month_not_approved = list(
                filter(
                    lambda item: item["ref_creation_date"]
                    and item["ref_creation_date"].month == date.month
                    and item["ref_creation_date"].year == date.year,
                    procedure_resources_list,
                )
            )
            pending_value = sum(
                [
                    procedure_resource["total_price"]
                    for procedure_resource in month_not_approved
                    if procedure_resource["approval_status"]
                    == resource_approval_status.WAITING_APPROVAL
                ]
            )

            # Unique resources
            unique_so_resources = len(
                list(
                    set(
                        [
                            item["service_order_resource_id"]
                            for item in month_approved
                            if item["service_order_resource_id"]
                        ]
                    )
                )
            )

            # Month bulletins
            measurement_bulletins_filtered = list(
                filter(
                    lambda item: item["measurement_date"]
                    and item["measurement_date"].month == date.month
                    and item["measurement_date"].year == date.year,
                    measurement_bulletins_list,
                )
            )
            month_bulletins = [
                item["num_bulletins"]
                for item in measurement_bulletins_filtered
                if item["num_bulletins"]
            ]
            if month_bulletins:
                num_bulletins = month_bulletins[0]
            else:
                num_bulletins = 0

            attributes.append(
                {
                    "month": key.split("/")[0],
                    "year": key.split("/")[1],
                    "approved_value": approved_value,
                    "pending_value": pending_value,
                    "denied_value": denied_value,
                    "num_bulletins": num_bulletins,
                    "num_resources": unique_so_resources,
                }
            )

        return Response({"type": "Measurement Bulletin", "attributes": attributes})


class UniqueMeasurementBulletinsView(APIView):
    """
    View to show values and dates of MeasurementBulletins

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        required_fields = ["company"]
        if not set(required_fields).issubset(request.query_params.keys()):
            return Response({"type": "Unique Measurement Bulletins", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="Contract"
        )

        contracts = get_contract_queryset("list", request, permissions)

        contracts, first_date, last_date = get_contracts_dates(
            contracts, request, date_format="datetime"
        )

        date_list = []
        for month in Arrow.range("month", first_date, last_date):
            date_list.append(month.datetime)

        permissions = PermissionManager(
            user=request.user,
            company_ids=company_id,
            model="MeasurementBulletin",
        )

        measurement_bulletins = get_measurement_bulletin_queryset(
            "list", request, permissions
        ).filter(contract__in=contracts, creation_date__gte=first_date)

        model = "MeasurementBulletin"
        measurement_bulletins = execute_filters(
            request.query_params, model, measurement_bulletins
        )

        attributes = []

        date_format = "%d-%m-%Y"

        for date in date_list:
            month_bulletins = [
                {
                    "date": bulletin.measurement_date.strftime(date_format),
                    "bulletin_number": bulletin.number,
                    "value": bulletin.total_price,
                }
                for bulletin in measurement_bulletins
                if (
                    (bulletin.measurement_date)
                    and (bulletin.measurement_date.month == (date.month))
                    and (bulletin.measurement_date.year == (date.year))
                )
            ]

            if not month_bulletins:
                last_day_of_month = calendar.monthrange(date.year, date.month)[1]
                last_day_str = date.replace(day=last_day_of_month).strftime(date_format)
                month_bulletins = [
                    {"date": last_day_str, "bulletin_number": "-", "value": 0}
                ]

            attributes += month_bulletins

        return Response(
            {"type": "Unique Measurement Bulletin", "attributes": attributes}
        )


class ReportingStatsView(APIView):
    """
    View to show count of type or status in all reportings.

    Parameters:
    company (uuid) - required
    data ("types", "status" or "kind") - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        fields = ["data", "company"]

        if not set(fields).issubset(request.query_params.keys()):
            return Response({"type": "ReportingStats", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))
        data = request.query_params.get("data")

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="Reporting"
        )

        reportings = ReportingFilter(
            request.GET,
            queryset=get_reporting_queryset("list", request, permissions),
            request=request,
        ).qs

        attributes = {}

        if data == "types":
            occurrence_type_specs = OccurrenceTypeSpecs.objects.filter(
                company__uuid=company_id
            ).prefetch_related("occurrence_type")

            reportings_occurrence_type = (
                reportings.values("occurrence_type__uuid", "occurrence_type__name")
                .annotate(num_occurence_type=Count("occurrence_type"))
                .order_by("-num_occurence_type")
            )

            def next_func_types(item):
                try:
                    color = next(
                        b
                        for b in occurrence_type_specs
                        if b.occurrence_type.uuid == item["occurrence_type__uuid"]
                    ).color
                except Exception:
                    color = ""
                return color

            types = [
                {
                    "id": a["occurrence_type__uuid"],
                    "name": a["occurrence_type__name"],
                    "color": next_func_types(a),
                    "value": a["num_occurence_type"],
                }
                for a in reportings_occurrence_type
                if a["occurrence_type__uuid"]
            ]

            attributes["types"] = types

        elif data == "status":
            status_specs = ServiceOrderActionStatusSpecs.objects.filter(
                company__uuid=company_id
            ).prefetch_related("status")

            reportings_occurrence_status = (
                reportings.values("status__uuid", "status__name")
                .annotate(num_status=Count("status"))
                .order_by("-num_status")
            )

            def next_func_status(item):
                try:
                    color = next(
                        b for b in status_specs if b.status.uuid == item["status__uuid"]
                    ).color
                except Exception:
                    color = ""
                return color

            status = [
                {
                    "id": a["status__uuid"],
                    "name": a["status__name"],
                    "color": next_func_status(a),
                    "value": a["num_status"],
                }
                for a in reportings_occurrence_status
                if a["status__uuid"]
            ]

            attributes["status"] = status

        elif data == "kind":
            try:
                company = Company.objects.get(pk=company_id)
                possible_path = (
                    "occurrencetype__fields__occurrencekind__selectoptions__options"
                )
                kinds = get_obj_from_path(company.custom_options, possible_path)
                kind_translation = {item["value"]: item["name"] for item in kinds}
            except Exception:
                pass
            else:
                reportings_occurrence_kind = (
                    reportings.values("occurrence_type__occurrence_kind")
                    .annotate(num_kind=Count("occurrence_type__occurrence_kind"))
                    .order_by("-num_kind")
                )

                kind = [
                    {
                        "id": a["occurrence_type__occurrence_kind"],
                        "name": kind_translation.get(
                            a["occurrence_type__occurrence_kind"], ""
                        ),
                        "color": get_random_color(),
                        "value": a["num_kind"],
                    }
                    for a in reportings_occurrence_kind
                    if a["occurrence_type__occurrence_kind"]
                ]

                attributes["kind"] = kind

        return Response({"type": "ReportingStats", "attributes": attributes})


class ReportingSLAView(APIView):
    """
    View to show how many Reporting objects were executed within their deadline

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        fields = ["company"]

        if not set(fields).issubset(request.query_params.keys()):
            return Response({"type": "ReportingSLA", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="Reporting"
        )

        try:
            company = Company.objects.get(pk=company_id)
            possible_path = "reporting__filters__csp__selectoptions__options"
            options = get_obj_from_path(company.custom_options, possible_path)
            csp_list = [item["value"] for item in options]
        except Exception:
            return Response({"type": "ReportingSLA", "attributes": []})

        reportings = ReportingFilter(
            request.GET,
            queryset=get_reporting_queryset("list", request, permissions).filter(
                due_at__isnull=False, executed_at__isnull=False
            ),
        ).qs

        attributes = {}
        for item in csp_list:
            reportings_filtered = reportings.filter(
                Q(
                    occurrence_type__form_fields__fields__contains=[
                        {"apiName": "csp"},
                        {"logic": item},
                    ]
                )
                | Q(
                    occurrence_type__form_fields__fields__contains=[
                        {"api_name": "csp"},
                        {"logic": item},
                    ]
                )
                | Q(form_data__csp=item)
            )

            inside_limit = reportings_filtered.filter(
                executed_at__date__lte=F("due_at__date")
            ).count()
            outside_limit = reportings_filtered.filter(
                executed_at__date__gt=F("due_at__date")
            ).count()

            try:
                sla = inside_limit / (inside_limit + outside_limit)
            except Exception:
                sla = 1

            attributes[item] = {
                "Atendimentos dentro do prazo": inside_limit,
                "Atendimentos fora do prazo": outside_limit,
                "sla": sla,
            }

        return Response({"type": "ReportingSLA", "attributes": attributes})


def build_type_reporting_dict(
    reportings, specs, date__lte=None, date__gte=None, isnull=False
):
    reportings_query = reportings
    if not isnull:
        if date__lte:
            reportings_query = reportings_query.filter(diff__lte=date__lte)
        if date__gte:
            reportings_query = reportings_query.filter(diff__gte=date__gte)
    else:
        reportings_query = reportings_query.filter(executed_at__isnull=True)

    reportings_result = reportings_query.values(
        "occurrence_type__uuid", "occurrence_type__name"
    ).annotate(amount=Count("occurrence_type"))

    def next_func(item):
        try:
            color = next(
                b
                for b in specs
                if b.occurrence_type.uuid == item["occurrence_type__uuid"]
            ).color
        except Exception:
            color = ""
        return color

    return [
        {
            "uuid": a["occurrence_type__uuid"],
            "name": a["occurrence_type__name"],
            "color": next_func(a),
            "amount": a["amount"],
        }
        for a in reportings_result
    ]


class ReportingRecentlyExecutedView(APIView):
    """
    View to show how many Reporting objects were executed in the last week,
    by OccurrenceType, in periods of: the last 24h; the last 48h; the last 72h;
    the last week; not executed; For this one we're only considering the executed_at date.

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        fields = ["company"]

        if not set(fields).issubset(request.query_params.keys()):
            return Response({"type": "ReportingRecentlyExecuted", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="Reporting"
        )

        reportings = ReportingFilter(
            request.GET,
            queryset=get_reporting_queryset("list", request, permissions),
            request=request,
        ).qs

        reportings = reportings.annotate(
            diff=ExpressionWrapper(
                F("executed_at") - F("found_at"), output_field=DurationField()
            )
        )

        date_24 = timedelta(days=1)
        date_48 = timedelta(days=2)
        date_72 = timedelta(days=3)
        date_week = timedelta(days=7)

        specs = OccurrenceTypeSpecs.objects.filter(
            company__uuid=company_id
        ).prefetch_related("occurrence_type")

        attributes = {
            "recentlyExecuted": [
                {
                    "name": "24h",
                    "types": build_type_reporting_dict(reportings, specs, date_24),
                },
                {
                    "name": "48h",
                    "types": build_type_reporting_dict(
                        reportings, specs, date_48, date_24
                    ),
                },
                {
                    "name": "72h",
                    "types": build_type_reporting_dict(
                        reportings, specs, date_72, date_48
                    ),
                },
                {
                    "name": "1 semana",
                    "types": build_type_reporting_dict(
                        reportings, specs, date_week, date_72
                    ),
                },
                {
                    "name": "Não atendidos",
                    "types": build_type_reporting_dict(reportings, specs, isnull=True),
                },
            ]
        }

        return Response({"type": "ReportingRecentlyExecuted", "attributes": attributes})


class ContractCostView(APIView):
    """
    View to show amount of approved ProceduresResources, amount
    of waiting for approval ProceduresResources and the
    total remaining of ServiceOrderResources of each Contract

    Parameters:
    company (uuid) - required
    contract (uuid list)
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        if "company" not in request.query_params:
            return Response({"type": "ContractCost", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="Contract"
        )

        contracts = get_contract_queryset("list", request, permissions).order_by("name")

        try:
            contract_ids = request.query_params["contract"]
            if not contract_ids:
                raise Exception
            contracts = contracts.filter(
                Q(uuid__in=contract_ids.split(","))
                & (
                    Q(firm__is_company_team=False)
                    | Q(subcompany__subcompany_type="HIRED")
                )
            )
        except Exception:
            contracts = contracts.filter(
                Q(firm__is_company_team=False) | Q(subcompany__subcompany_type="HIRED")
            )

        try:
            subcompany_uuid = uuid.UUID(request.query_params.get("subcompany"))

            contracts = contracts.filter(subcompany=subcompany_uuid)

        except Exception:
            pass

        contracts = ContractSerializer().setup_eager_loading(contracts)

        attributes = []
        for contract in contracts:
            total_price = contract.total_price
            spent_price = contract.spent_price

            waiting_price = 0
            for resource in contract.resources.all():
                for (
                    procedure_resource
                ) in resource.serviceorderresource_procedures.all():
                    try:
                        resource_spent_price = (
                            (procedure_resource.unit_price * procedure_resource.amount)
                            if procedure_resource.approval_status
                            == resource_approval_status.WAITING_APPROVAL
                            else 0
                        )
                        if not isinstance(resource_spent_price, (int, float)):
                            raise Exception()
                        waiting_price += resource_spent_price
                    except Exception:
                        continue

            remaining = total_price - waiting_price - spent_price

            attributes.append(
                {
                    "name": contract.name,
                    "approved": spent_price,
                    "waiting_approval": waiting_price,
                    "remaining": remaining,
                }
            )

        return Response({"type": "ContractCost", "attributes": attributes})


class ActionCountView(APIView):
    """
    View to show count of ServiceOrderActions by firm.

    Parameters:
    company (uuid) - required
    date_after (date)
    date_before (date)

    Returns:
    JSON

    * Requires token authentication.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        if "company" not in request.query_params:
            return Response({"type": "ActionCount", "attributes": []})

        company_id = uuid.UUID(request.query_params.get("company"))

        firms = Firm.objects.filter(company_id=company_id)
        model = "Firm"
        firms = execute_filters(request.query_params, model, firms).order_by("name")

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="Procedure"
        )

        procedures = (
            get_procedure_queryset("list", request, permissions)
            .filter(firm__in=firms)
            .prefetch_related("firm", "action", "action__service_order_action_status")
        )

        model = "Procedure"
        procedures = execute_filters(request.query_params, model, procedures)

        try:
            first_status = (
                ServiceOrderActionStatusSpecs.objects.filter(
                    company_id=company_id,
                    status__kind=status_types.ACTION_STATUS,
                )
                .order_by("order")
                .first()
                .status
            )
        except Exception:
            return Response({"type": "ActionCount", "attributes": []})

        final_status = ServiceOrderActionStatus.objects.filter(
            companies__uuid=company_id,
            kind=status_types.ACTION_STATUS,
            is_final=True,
        )

        doing_status = (
            ServiceOrderActionStatus.objects.filter(
                companies__uuid=company_id, kind=status_types.ACTION_STATUS
            )
            .exclude(pk__in=final_status)
            .exclude(pk=first_status.pk)
        )

        attributes = []
        action_already_counted = []
        transformer_dict = {}
        for procedure in procedures:
            status = procedure.action.service_order_action_status
            if (procedure.action, procedure.firm) not in action_already_counted:
                action_already_counted.append((procedure.action, procedure.firm))
                if status == first_status:
                    transformer_dict = safe_increment(
                        transformer_dict, procedure.firm.name, "to_do"
                    )
                elif status in doing_status:
                    transformer_dict = safe_increment(
                        transformer_dict, procedure.firm.name, "doing"
                    )
                elif status in final_status:
                    transformer_dict = safe_increment(
                        transformer_dict, procedure.firm.name, "done"
                    )

        transformer_dict_final = {
            firm.name: transformer_dict[firm.name]
            if firm.name in transformer_dict
            else {"done": 0, "to_do": 0, "doing": 0}
            for firm in firms
        }

        for firm in transformer_dict_final.keys():
            attributes.append({"name": firm})
            for status in ["to_do", "doing", "done"]:
                if status in transformer_dict_final[firm].keys():
                    attributes[-1][status] = transformer_dict_final[firm][status]
                else:
                    attributes[-1][status] = 0

        return Response({"type": "ActionCount", "attributes": attributes})


class ReportingCountView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        fields = ["from_year", "company", "occurrence_type"]

        if not set(fields).issubset(request.query_params.keys()):
            return error_message(
                400,
                "Não é possível realizar esta operação sem atributos company, from_year ou occurrence_type.",
            )

        user_company = uuid.UUID(request.query_params["company"])

        permissions = PermissionManager(
            user=request.user, company_ids=user_company, model="Reporting"
        )

        reportings_base = ReportingFilter(
            request.GET,
            queryset=get_reporting_queryset("list", request, permissions),
            request=request,
        ).qs

        if "period" not in request.query_params:
            period = "day"
        else:
            period = request.query_params["period"]

        if "reference_date" not in request.query_params:
            reference_date = "found_at"
        else:
            reference_date = request.query_params["reference_date"]
            if reference_date not in ["found_at", "executed_at"]:
                return error_message(400, "Invalid reference_date.")

        from_year = request.query_params["from_year"]
        if not from_year.isdigit():
            return error_message(400, "Invalid from_year.")

        start_date = parser.parse(from_year + "/01/01")
        end_date = datetime.now()
        mid_steps = get_dates_by_frequency(period, start_date, end_date)
        steps = [item[0] for item in mid_steps]

        occ_types_ids = request.query_params["occurrence_type"].split(",")
        for item in occ_types_ids:
            if not is_valid_uuid(item):
                return error_message(400, "Invalid occurrence_type.")

        occ_types = OccurrenceType.objects.filter(pk__in=occ_types_ids).distinct()

        try:
            company = Company.objects.get(pk=uuid.UUID(request.query_params["company"]))
        except Exception:
            return error_message(400, "Company não encontrada")

        if reference_date == "found_at":
            reportings = reportings_base.filter(
                occurrence_type_id__in=occ_types,
                found_at__gte=start_date,
                found_at__lte=end_date,
            )
        else:
            reportings = reportings_base.filter(
                occurrence_type_id__in=occ_types,
                executed_at__gte=start_date,
                executed_at__lte=end_date,
            )

        try:
            daily_kind = company.metadata["daily_occurrence_kind"]
        except Exception:
            daily_kind = "5"

        try:
            occ_type = OccurrenceType.objects.filter(
                company=company, occurrence_kind=daily_kind
            ).first()
        except Exception:
            return Response({"type": "RainData", "attributes": []})

        mid_steps_rain = get_dates_by_frequency("day", start_date, end_date)
        steps_rain = [item[0] for item in mid_steps_rain]

        reportings_rain = reportings_base.filter(occurrence_type=occ_type)

        # form_data filter
        if "form_data" in request.query_params.keys():
            key_filter = KeyFilter(field_name="form_data", distinct=True)
            reportings = key_filter.filter(
                reportings, request.query_params["form_data"]
            )
            reportings_rain = key_filter.filter(
                reportings_rain, request.query_params["form_data"]
            )

        # artesp filter
        if "has_artesp_code" in request.query_params.keys():
            if request.query_params["has_artesp_code"].lower() == "true":
                reportings = reportings.filter(
                    form_data__artesp_code__isnull=False
                ).exclude(form_data__artesp_code__exact="")
                reportings_rain = reportings_rain.filter(
                    form_data__artesp_code__isnull=False
                ).exclude(form_data__artesp_code__exact="")

            if request.query_params["has_artesp_code"].lower() == "false":
                reportings = reportings.filter(form_data__artesp_code__isnull=True)
                reportings_rain = reportings_rain.filter(
                    form_data__artesp_code__isnull=True
                )

        reportings_count = ReportingCount(
            period,
            steps,
            reportings,
            occ_types,
            reference_date,
            steps_rain,
            reportings_rain,
        )

        return reportings_count.get_response()


class ReportingCountRoadView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        fields = [
            "start_date",
            "end_date",
            "company",
            "occurrence_type",
            "km_step",
            "road_name",
        ]

        if not set(fields).issubset(request.query_params.keys()):
            return error_message(
                400,
                "Falta algum atributo: company, start_date, end_date, occurrence_type, km_step ou road_name.",
            )

        user_company = uuid.UUID(request.query_params["company"])

        permissions = PermissionManager(
            user=request.user, company_ids=user_company, model="Reporting"
        )

        reportings = ReportingFilter(
            request.GET,
            queryset=get_reporting_queryset("list", request, permissions),
            request=request,
        ).qs

        try:
            start_date = parser.parse(request.query_params["start_date"])
            end_date = parser.parse(request.query_params["end_date"])
        except Exception:
            return error_message(400, "start_date ou end_date inválido")

        km_step = request.query_params["km_step"]
        if not km_step.isdigit():
            return error_message(400, "km_step inválido.")

        road_name = request.query_params["road_name"]

        occ_types_ids = request.query_params["occurrence_type"].split(",")
        for item in occ_types_ids:
            if not is_valid_uuid(item):
                return error_message(400, "occurrence_type inválido.")

        occ_types = OccurrenceType.objects.filter(pk__in=occ_types_ids).distinct()

        reportings = reportings.filter(
            occurrence_type_id__in=occ_types,
            found_at__gte=start_date,
            found_at__lte=end_date,
        )

        # form_data filter
        if "form_data" in request.query_params.keys():
            key_filter = KeyFilter(field_name="form_data", distinct=True)
            reportings = key_filter.filter(
                reportings, request.query_params["form_data"]
            )

        if "lane" in request.query_params.keys() and request.query_params["lane"]:
            lanes = request.query_params["lane"].split(",")
            reportings = reportings.filter(lane__in=lanes)

        if (
            "direction" in request.query_params.keys()
            and request.query_params["direction"]
        ):
            directions = request.query_params["direction"].split(",")
            reportings = reportings.filter(direction__in=directions)

        # artesp filter
        if "has_artesp_code" in request.query_params.keys():
            if request.query_params["has_artesp_code"].lower() == "true":
                reportings = reportings.filter(
                    form_data__artesp_code__isnull=False
                ).exclude(form_data__artesp_code__exact="")

            if request.query_params["has_artesp_code"].lower() == "false":
                reportings = reportings.filter(form_data__artesp_code__isnull=True)

        reportings_count = ReportingCountRoad(
            int(km_step), road_name, reportings, occ_types, user_company
        )

        return reportings_count.get_response()


class RainDataView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        fields = ["start_date", "end_date", "company"]

        if not set(fields).issubset(request.query_params.keys()):
            return error_message(
                400,
                "Não é possível realizar esta operação sem atributos company, start_date ou end_date.",
            )

        company_id = uuid.UUID(request.query_params.get("company"))

        permissions = PermissionManager(
            user=request.user, company_ids=company_id, model="Reporting"
        )

        reportings = ReportingFilter(
            request.GET,
            queryset=get_reporting_queryset("list", request, permissions),
            request=request,
        ).qs

        try:
            start_date = parser.parse(request.query_params["start_date"])
            end_date = parser.parse(request.query_params["end_date"])
        except Exception:
            return error_message(400, "Formato de data inválido")

        try:
            company = Company.objects.get(pk=company_id)
        except Exception:
            return error_message(400, "Company não encontrada")

        try:
            daily_kind = company.metadata["daily_occurrence_kind"]
        except Exception:
            daily_kind = "5"

        try:
            occ_type = OccurrenceType.objects.filter(
                company=company, occurrence_kind=daily_kind
            ).first()
        except Exception:
            return Response({"type": "RainData", "attributes": []})

        steps = list(Arrow.range("day", start_date, end_date))

        reportings = reportings.filter(occurrence_type=occ_type)

        reportings_count = RainData(steps, reportings)

        return reportings_count.get_response()
