import datetime
import functools
from functools import reduce
from operator import __or__ as OR

import pytz
from django.db.models import Q, TextField, Value
from django.db.models.functions import Concat
from django_filters import rest_framework as filters
from django_filters.filters import CharFilter, ChoiceFilter, RangeFilter
from django_filters.rest_framework.filters import BooleanFilter
from rest_framework_json_api import serializers

from apps.companies.models import Company, Firm
from apps.occurrence_records.models import OccurrenceType
from apps.work_plans.models import Job
from helpers.apps.daily_reports import (
    get_uuids_jobs_user_firms,
    get_uuids_rdos_user_firms,
)
from helpers.filters import (
    DateFromToRangeCustomFilter,
    ListFilter,
    UUIDListFilter,
    queryset_with_timezone,
)
from helpers.strings import check_image_file, get_obj_from_path

from .const import file_choices, origin_choices, status_types
from .models import (
    AdditionalControl,
    AdministrativeInformation,
    MeasurementBulletin,
    PendingProceduresExport,
    Procedure,
    ProcedureFile,
    ProcedureResource,
    ServiceOrder,
    ServiceOrderAction,
    ServiceOrderActionStatus,
    ServiceOrderActionStatusSpecs,
    ServiceOrderResource,
    ServiceOrderWatcher,
)


class ServiceOrderActionStatusFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="companies")
    only_executed_reporting_status = BooleanFilter(
        method="get_only_executed_reporting_status"
    )
    only_service_order_status = BooleanFilter(
        label="only_service_order_status", method="get_only_service_order_status"
    )

    class Meta:
        model = ServiceOrderActionStatus
        fields = {"kind", "is_final"}

    def get_only_executed_reporting_status(self, queryset, name, value):
        if "company" not in self.data:
            return queryset
        company = Company.objects.get(uuid=self.data["company"])

        executed_status_order = get_obj_from_path(
            company.metadata, "executed_status_order"
        )
        if not isinstance(executed_status_order, int):
            raise serializers.ValidationError(
                "Unidade não possui status de execução configurado"
            )

        filter_base = {"companies": company, "kind": "REPORTING_STATUS"}
        filter_order_true = {"status_specs__order__gte": executed_status_order}
        filter_order_false = {"status_specs__order__lt": executed_status_order}
        if value is True:
            return queryset.filter(**filter_base, **filter_order_true).distinct()
        else:
            return queryset.filter(**filter_base, **filter_order_false).distinct()

    def get_only_service_order_status(self, queryset, name, value):
        """
        This filter returns only items related to service orders.
        """
        if value is True:
            return queryset.filter(
                kind__in=[
                    status_types.ENVIRONMENTAL_SERVICE_CONCLUSION,
                    status_types.ENVIRONMENTAL_SERVICE_PROGRESS,
                    status_types.LAND_SERVICE_CONCLUSION,
                    status_types.LAND_SERVICE_PROGRESS,
                ]
            )


class ServiceOrderActionStatusSpecsFilter(filters.FilterSet):
    uuid = UUIDListFilter()

    class Meta:
        model = ServiceOrderActionStatusSpecs
        fields = {"company": ["exact"], "status": ["exact"]}


class ServiceOrderFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    opened_at = DateFromToRangeCustomFilter()
    updated_at = DateFromToRangeCustomFilter()
    closed_at = DateFromToRangeCustomFilter()
    is_not_approved = BooleanFilter(field_name="opened_at", lookup_expr="isnull")
    is_closed = BooleanFilter()
    occurrence_kind = ListFilter(
        field_name="so_records__occurrence_type__occurrence_kind", distinct=True
    )
    occurrence_type = ListFilter(method="get_occurrence_type")
    description = CharFilter(lookup_expr="icontains")
    contracts = UUIDListFilter()
    human_resources = UUIDListFilter(field_name="contracts")
    operational_controls = ListFilter(method="get_operational_controls")
    monitoring_cycles = UUIDListFilter()
    entity = UUIDListFilter()
    kind = ListFilter()
    process_type = ListFilter()
    shape_file_property = ListFilter()
    search = CharFilter(label="search", method="get_search")
    status = UUIDListFilter()

    firm = ListFilter(label="firm", method="filter_firm")

    class Meta:
        model = ServiceOrder
        fields = {"company": ["exact"], "number": ["exact"]}

    def get_operational_controls(self, queryset, name, value):
        values = value.split(",")
        return queryset.filter(so_records__operational_control__in=values).distinct()

    def filter_firm(self, queryset, name, value):
        firms = value.split(",")
        return queryset.filter(
            Q(actions__procedures__firm__in=firms) | Q(contracts__firm__in=firms)
        ).distinct()

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "number",
                Value(" "),
                "description",
                Value(" "),
                "other_reference",
                Value(" "),
                "closed_description",
                Value(" "),
                "location__name",
                Value(" "),
                "river__name",
                Value(" "),
                "entity__name",
                Value(" "),
                "city__name",
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )

    def get_occurrence_type(self, queryset, name, value):
        ids = value.split(",")
        occ_types = OccurrenceType.objects.filter(
            type_records__service_order__in=queryset
        ).values_list("uuid", "previous_version_id")
        list_ids = []

        def get_previous_id(obj_id, occ_types):
            for obj, pre_obj in occ_types:
                if str(obj) == obj_id and pre_obj:
                    return str(pre_obj)
            return None

        for obj_id in ids:
            while obj_id:
                list_ids.append(obj_id)
                obj_id = get_previous_id(obj_id, occ_types)

        return queryset.filter(so_records__occurrence_type_id__in=list_ids).distinct()


class ServiceOrderWatcherFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="service_order__company")
    user = UUIDListFilter()
    firm = UUIDListFilter()
    service_order = UUIDListFilter()
    is_user = BooleanFilter(field_name="user", lookup_expr="isnull", exclude=True)
    is_firm = BooleanFilter(field_name="firm", lookup_expr="isnull", exclude=True)

    class Meta:
        model = ServiceOrderWatcher
        fields = ["uuid", "user", "firm"]


class ServiceOrderActionFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter(field_name="service_order__company")
    service_order = UUIDListFilter()
    is_closed = BooleanFilter(field_name="service_order__is_closed")
    responsible = UUIDListFilter()
    created_by = UUIDListFilter()
    service_order_action_status = UUIDListFilter()
    opened_at = DateFromToRangeCustomFilter()
    deadline = DateFromToRangeCustomFilter(
        method="filter_deadline", label="filter_deadline"
    )
    allow_forwarding = BooleanFilter()
    contains_files = BooleanFilter(
        method="procedures_have_files", label="procedures_have_files"
    )
    contains_images = BooleanFilter(
        method="procedures_have_images", label="procedures_have_images"
    )
    contract = CharFilter(method="contract_filter", label="contract")
    search = CharFilter(label="search", method="get_search")

    class Meta:
        model = ServiceOrderAction
        fields = {"uuid": ["exact"]}

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "name",
                Value(" "),
                "service_order__number",
                Value(" "),
                "service_order__description",
                Value(" "),
                "service_order_action_status__name",
                Value(" "),
                "firm__name",
                Value(" "),
                "responsible__first_name",
                Value(" "),
                "created_by__first_name",
                Value(" "),
                "parent_record__number",
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )

    def filter_deadline(self, queryset, name, value):
        if not value:
            return queryset

        qs = Procedure.objects.filter(action__in=queryset, procedure_next__isnull=True)
        qs_annotated = queryset_with_timezone(qs, "deadline", "new_deadline")
        if value.start and value.stop:
            procedure_queryset = qs_annotated.filter(
                new_deadline__gte=value.start.replace(tzinfo=pytz.UTC),
                new_deadline__lte=value.stop.replace(tzinfo=pytz.UTC),
            )
        elif value.start:
            procedure_queryset = qs_annotated.filter(
                new_deadline__gte=value.start.replace(tzinfo=pytz.UTC)
            )
        elif value.stop:
            procedure_queryset = qs_annotated.filter(
                new_deadline__lte=value.stop.replace(tzinfo=pytz.UTC)
            )

        return queryset.filter(procedures__in=procedure_queryset)

    def procedures_have_files(self, queryset, name, value):
        procedures = {a.uuid: list(a.procedures.all()) for a in queryset}

        procedure_files = {
            key: reduce(
                lambda x, y: x + y,
                [list(a.procedure_files.all()) for a in value],
                [],
            )
            for key, value in procedures.items()
        }

        action_ids = [
            key
            for key, value in procedure_files.items()
            if len([item for item in value if not check_image_file(item.upload.name)])
        ]

        return queryset.filter(uuid__in=action_ids)

    def procedures_have_images(self, queryset, name, value):
        procedures = {a.uuid: list(a.procedures.all()) for a in queryset}

        procedure_files = {
            key: reduce(
                lambda x, y: x + y,
                [list(a.procedure_files.all()) for a in value],
                [],
            )
            for key, value in procedures.items()
        }

        action_ids = [
            key
            for key, value in procedure_files.items()
            if len([item for item in value if check_image_file(item.upload.name)])
        ]

        return queryset.filter(uuid__in=action_ids)

    def contract_filter(self, queryset, name, value):
        if not value:
            return queryset

        return queryset.filter(
            procedures__procedure_resources__service_order_resource__contract=value
        ).distinct()


class ProcedureFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    responsible = UUIDListFilter()
    action = UUIDListFilter()
    company = CharFilter(field_name="action__service_order__company__uuid")
    service_order = UUIDListFilter(field_name="action__service_order")
    procedure_next_is_null = BooleanFilter(
        field_name="procedure_next", lookup_expr="isnull"
    )
    is_closed = BooleanFilter(field_name="action__service_order__is_closed")
    firm = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    deadline = DateFromToRangeCustomFilter()
    done_at = DateFromToRangeCustomFilter()
    occurrence_kind = ListFilter(
        field_name="action__service_order__so_records__occurrence_type__occurrence_kind"
    )
    occurrence_type = ListFilter(
        field_name="action__service_order__so_records__occurrence_type"
    )
    created_by = UUIDListFilter()
    service_order_action_status = UUIDListFilter()
    is_done = BooleanFilter(label="is_done", method="is_done_filter")
    service_order_kind = ListFilter(field_name="action__service_order__kind")
    service_order_river = UUIDListFilter(field_name="action__service_order__river")
    service_order_city = UUIDListFilter(field_name="action__service_order__city")
    service_order_location = UUIDListFilter(
        field_name="action__service_order__location"
    )
    service_order_uf_code = ListFilter(method="get_uf_code")
    service_order_place_on_dam = ListFilter(method="get_place_on_dam")

    forward_to_judiciary = BooleanFilter()

    search = CharFilter(label="search", method="get_search")

    class Meta:
        model = Procedure
        fields = [
            "service_order_river",
            "service_order_city",
            "service_order_location",
        ]

    def is_done_filter(self, queryset, name, value):
        if value is True:
            return queryset.filter(
                Q(procedure_next__isnull=False)
                | Q(service_order_action_status__is_final=True)
                | Q(action__service_order__is_closed=True)
            ).distinct()
        elif value is False:
            return queryset.exclude(
                Q(procedure_next__isnull=False)
                | Q(service_order_action_status__is_final=True)
                | Q(action__service_order__is_closed=True)
            ).distinct()
        else:
            return queryset

    def get_uf_code(self, queryset, name, value):
        values = value.split(",")
        return queryset.filter(
            action__service_order__uf_code__overlap=values
        ).distinct()

    def get_place_on_dam(self, queryset, name, value):
        values = value.split(",")
        return queryset.filter(
            action__service_order__place_on_dam__overlap=values
        ).distinct()

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "action__name",
                Value(" "),
                "to_do",
                Value(" "),
                "action__service_order__description",
                Value(" "),
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )


class ProcedureFileFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="procedures__action__service_order__company__uuid")
    procedure = UUIDListFilter(field_name="procedures", distinct=True)
    procedures = ListFilter(distinct=True)
    exclude_procedures = ListFilter(
        field_name="procedures", distinct=True, exclude=True
    )
    procedure__action = ListFilter(field_name="procedures__action", distinct=True)
    procedures__action = ListFilter(distinct=True)
    procedure__action__service_order = ListFilter(
        field_name="procedures__action__service_order", distinct=True
    )
    procedures__action__service_order = ListFilter(distinct=True)
    procedure__action__service_order__occurrence_record = ListFilter(
        field_name="procedures__action__service_order__so_records",
        distinct=True,
    )
    procedures__action__service_order__occurrence_record = ListFilter(
        field_name="procedures__action__service_order__so_records",
        distinct=True,
    )
    occurrence_record = CharFilter(
        method="occurrence_record_filter", label="occurrence_record_id"
    )
    file_type = ChoiceFilter(
        choices=file_choices.FILE_CHOICES,
        method="check_image",
        label="file_type",
    )

    class Meta:
        model = ProcedureFile
        fields = [
            "company",
            "procedures",
            "procedures__action",
            "procedures__action__service_order",
            "procedures__action__service_order__occurrence_record",
            "occurrence_record",
        ]

    def occurrence_record_filter(self, queryset, name, value):
        queryset = (
            ProcedureFile.objects.filter(
                procedures__action__service_order__so_records=value
            )
            .distinct()
            .prefetch_related("procedures")
        )
        return queryset

    def check_image(self, queryset, name, value):
        ids_and_file_names = queryset.values_list("uuid", "upload")
        if value == "image":
            list_get = [
                item[0] for item in ids_and_file_names if check_image_file(item[1])
            ]
        elif value == "file":
            list_get = [
                item[0] for item in ids_and_file_names if not check_image_file(item[1])
            ]

        return queryset.filter(pk__in=list_get)


class ProcedureResourceFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = ListFilter(method="get_company_filter")
    procedure = UUIDListFilter()
    procedure__action = UUIDListFilter()
    service_order = UUIDListFilter()
    service_order__occurrence_record = ListFilter(
        field_name="service_order__so_records", distinct=True
    )
    reporting__approval_step = UUIDListFilter()
    measurement_bulletin = ListFilter(allow_null=True)
    resource = UUIDListFilter()
    reporting = UUIDListFilter()
    reporting__executed_at = DateFromToRangeCustomFilter()
    reporting__reporting_multiple_daily_reports = UUIDListFilter()
    approval_status = CharFilter()
    creation_date = DateFromToRangeCustomFilter()
    approval_date = DateFromToRangeCustomFilter()
    total_price = RangeFilter()
    administrative_information = ListFilter(
        method="administrative_information_filter",
        label="administrative_information",
    )
    contract = UUIDListFilter(field_name="service_order_resource__contract")
    has_measurement_bulletin = BooleanFilter(
        field_name="measurement_bulletin", lookup_expr="isnull", exclude=True
    )
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")
    contract_service = ListFilter(method="get_contract_service")
    service_order_resource = UUIDListFilter()
    has_reporting = CharFilter(method="get_with_reporting")
    origin_of_creation = ChoiceFilter(
        choices=origin_choices.ORIGIN_CHOICES,
        method="filter_origin_of_creation",
        label="origin_of_creation",
    )
    number_list = ListFilter(method="get_number_list")
    firm = UUIDListFilter(field_name="reporting__firm")
    lot = ListFilter(field_name="reporting__lot")
    active = ListFilter(method="get_active")

    class Meta:
        model = ProcedureResource
        fields = [
            "company",
            "procedure",
            "procedure__action",
            "service_order",
            "service_order__occurrence_record",
        ]

    def get_with_reporting(self, queryset, name, value):
        if value == "false":
            condition = True
        elif value == "true":
            condition = False
        else:
            raise serializers.ValidationError()

        return queryset.filter(reporting__isnull=condition).distinct()

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        jobs_section, rdos_section = value.split("|")

        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        jobs_uuids = get_uuids_jobs_user_firms(jobs_section, company, self.request.user)
        rdos_uuids = get_uuids_rdos_user_firms(rdos_section, company, self.request.user)

        return queryset.filter(
            Q(reporting__job_id__in=jobs_uuids)
            | Q(reporting__reporting_multiple_daily_reports__in=rdos_uuids)
        ).distinct()

    def get_num_jobs_only_user_firms(self, queryset, name, value):
        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        jobs_values = value.split(",")
        num_jobs = jobs_values.pop(0)
        user_firms = self.request.user.user_firms.all()
        if "num_jobs" in company.metadata:
            num_jobs = int(company.metadata["num_jobs"])

        max_reportings_by_job = int(company.metadata.get("max_reportings_by_job", 250))

        jobs_by_count = (
            Job.objects.filter(
                firm__in=user_firms,
                archived=False,
                reporting_count__lte=max_reportings_by_job,
            )
            .order_by("-start_date")[0 : int(num_jobs)]
            .values_list("uuid", flat=True)
        )
        jobs_by_ids = Job.objects.filter(
            uuid__in=jobs_values,
            archived=False,
            reporting_count__lte=max_reportings_by_job,
        ).values_list("uuid", flat=True)

        return queryset.filter(
            Q(reporting__job_id__in=jobs_by_count)
            | Q(reporting__job_id__in=jobs_by_ids)
        ).distinct()

    def get_num_user_firms(self, queryset, name, value):
        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        firms_values = value.split(",")
        num_firms = firms_values.pop(0)
        if "num_firms" in company.metadata:
            num_firms = int(company.metadata["num_firms"])

        firms_by_count = (
            Firm.objects.filter(company=company, users__in=[self.request.user])
            .order_by("name")[: int(num_firms)]
            .values_list("uuid", flat=True)
        )

        firms_by_ids = Firm.objects.filter(
            uuid__in=firms_values, company=company
        ).values_list("uuid", flat=True)

        return queryset.filter(
            Q(reporting__reporting_multiple_daily_reports__firm__in=firms_by_count)
            | Q(reporting__reporting_multiple_daily_reports__firm__in=firms_by_ids)
        ).distinct()

    def administrative_information_filter(self, queryset, name, value):
        administrative_informations = AdministrativeInformation.objects.filter(
            uuid__in=value.split(",")
        ).select_related("contract", "service_order")

        conditions = [
            Q(service_order_resource__contract=a.contract.uuid)
            & Q(procedure__action__service_order=a.service_order.uuid)
            for a in administrative_informations
        ]

        return queryset.filter(reduce(OR, conditions))

    def get_company_filter(self, queryset, name, value):
        uuid_list = value.split(",")

        return queryset.filter(
            Q(firm__company__uuid__in=uuid_list)
            | Q(service_order_resource__resource__company__uuid__in=uuid_list)
        ).distinct()

    def get_contract_service(self, queryset, name, value):
        contract_service_ids = value.split(",")
        return queryset.filter(
            Q(
                service_order_resource__resource_contract_unit_price_items__contract_item_unit_price_services__in=contract_service_ids
            )
            | Q(
                service_order_resource__resource_contract_administration_items__contract_item_administration_services__in=contract_service_ids
            )
        ).distinct()

    def filter_origin_of_creation(self, queryset, name, value):
        if value == "MANUAL":
            return queryset.filter(
                reporting__isnull=True,
                resource__resource_daily_report_resources__isnull=True,
            ).distinct()
        elif value == "REPORTING":
            return queryset.filter(
                reporting__isnull=False,
            ).distinct()
        elif value == "RDO":
            return queryset.filter(
                resource__resource_daily_report_resources__isnull=False,
            ).distinct()

    def get_number_list(self, queryset, name, value):
        number_list = [item for item in value.replace(" ", "").split(",") if item]

        return queryset.filter(
            functools.reduce(
                lambda acc, x: acc | Q(reporting__number__icontains=x), number_list, Q()
            )
        ).distinct()

    def get_active(self, queryset, name, value):
        values = value.split(",")

        return queryset.filter(reporting__form_data__active__in=values).distinct()


class ServiceOrderResourceFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = ListFilter(method="get_company_filter")
    administrative_information = ListFilter(
        method="administrative_information_filter",
        label="administrative_information",
    )

    contract = ListFilter(distinct=True)
    human_resource = UUIDListFilter(field_name="contract", distinct=True)
    service_order = ListFilter(field_name="contract__service_orders", distinct=True)
    action = ListFilter(field_name="contract__service_orders__actions", distinct=True)
    firm = ListFilter(method="get_firm")
    responsible = ListFilter(field_name="contract__responsibles_hirer", distinct=True)
    responsibles_hirer = ListFilter(
        field_name="contract__responsibles_hirer", distinct=True
    )
    responsibles_hired = ListFilter(
        field_name="contract__responsibles_hired", distinct=True
    )
    entity = UUIDListFilter()
    contract_item_type = ListFilter(method="get_contract_item_type")
    search = CharFilter(label="search", method="get_search")
    contract_in_force = BooleanFilter(method="filter_contract_in_force")

    class Meta:
        model = ServiceOrderResource
        fields = ["resource", "resource_kind"]

    def get_company_filter(self, queryset, name, value):
        uuid_list = value.split(",")

        return queryset.filter(
            Q(contract__firm__company__uuid__in=uuid_list)
            | Q(contract__subcompany__company__uuid__in=uuid_list)
        ).distinct()

    def get_contract_item_type(self, queryset, name, value):
        item_type_list = value.split(",")

        conditions = []

        if "unit_price" in item_type_list:
            conditions.append(Q(resource_contract_unit_price_items__isnull=False))
        if "administration" in item_type_list:
            conditions.append(Q(resource_contract_administration_items__isnull=False))
        if "performance" in item_type_list:
            conditions.append(Q(resource_contract_performance_items__isnull=False))

        return queryset.filter(reduce(OR, conditions))

    def administrative_information_filter(self, queryset, name, value):
        administrative_informations = AdministrativeInformation.objects.filter(
            uuid__in=value.split(",")
        ).select_related("contract", "service_order")

        conditions = [
            Q(contract=a.contract.uuid)
            & Q(contract__service_orders=a.service_order.uuid)
            for a in administrative_informations
        ]

        return queryset.filter(reduce(OR, conditions))

    def get_firm(self, queryset, name, value):
        firm_ids = value.split(",")

        return queryset.filter(
            Q(contract__firm__in=firm_ids)
            | Q(contract__unit_price_services__firms__in=firm_ids)
            | Q(contract__administration_services__firms__in=firm_ids)
            | Q(contract__performance_services__firms__in=firm_ids)
        )

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "resource__name",
                Value(" "),
                "resource__unit",
                Value(" "),
                "additional_control_model__name",
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )

    def filter_contract_in_force(self, queryset, name, value):
        today = datetime.datetime.now()
        if value:
            return queryset.filter(
                contract__contract_start__lte=today,
                contract__contract_end__gte=today,
            ).distinct()
        else:
            return queryset.exclude(
                contract__contract_start__lte=today,
                contract__contract_end__gte=today,
            ).distinct()


class MeasurementBulletinFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    # company = CharFilter(field_name="firm__company__uuid")
    measurement_date = DateFromToRangeCustomFilter()
    total_price = RangeFilter()
    administrative_information = ListFilter(
        method="administrative_information_filter",
        label="administrative_information",
    )
    contract = UUIDListFilter()
    editable = BooleanFilter()
    is_processing = BooleanFilter()
    related_firms = UUIDListFilter()

    class Meta:
        model = MeasurementBulletin
        fields = ["firm", "created_by"]

    def administrative_information_filter(self, queryset, name, value):
        administrative_informations = AdministrativeInformation.objects.filter(
            uuid__in=value.split(",")
        ).select_related("contract", "service_order")

        conditions = [
            Q(contract=a.contract.uuid)
            & Q(contract__service_orders=a.service_order.uuid)
            for a in administrative_informations
        ]

        return queryset.filter(reduce(OR, conditions))


class AdministrativeInformationFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="service_order__company__uuid")
    human_resource = UUIDListFilter(field_name="contract")
    is_human_resource = BooleanFilter(method="get_is_human_resource")

    class Meta:
        model = AdministrativeInformation
        fields = ["contract", "service_order", "created_by"]

    def get_is_human_resource(self, queryset, name, value):
        subcompany_type = "HIRING" if value else "HIRED"

        return queryset.filter(
            Q(contract__firm__is_company_team=value)
            | Q(contract__subcompany__subcompany_type=subcompany_type)
        )


class AdditionalControlFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    created_by = UUIDListFilter()
    is_active = BooleanFilter()

    class Meta:
        model = AdditionalControl
        fields = {"company": ["exact"]}


class PendingProcedureExportFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    created_by = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()

    class Meta:
        model = PendingProceduresExport
        fields = ["uuid", "created_at", "created_by", "done", "error"]
