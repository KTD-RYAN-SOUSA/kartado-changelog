from django.db.models import Q, TextField, Value
from django.db.models.functions import Concat
from django_filters import rest_framework as filters
from rest_framework_json_api import serializers

from apps.resources.const import type_survey_filter
from apps.resources.helpers.filters.abstract_filters import (
    ContractFilterBase,
    ContractItemFilter,
    ContractItemFilterBasic,
    ContractServiceFilterBase,
)
from apps.resources.models import (
    Contract,
    ContractAdditive,
    ContractItemAdministration,
    ContractItemPerformance,
    ContractItemUnitPrice,
    ContractPeriod,
    ContractService,
    FieldSurvey,
    FieldSurveyExport,
    FieldSurveyRoad,
    FieldSurveySignature,
    MeasurementBulletinExport,
    Resource,
)
from apps.service_orders.const import resource_approval_status
from helpers.filters import (
    DateFromToRangeCustomFilter,
    FilterSetWithInitialValues,
    ListFilter,
    UUIDListFilter,
)


class ContractServiceFilter(ContractServiceFilterBase):
    uuid = UUIDListFilter()
    firms = UUIDListFilter()
    company = UUIDListFilter(field_name="firms__company")
    contract_item_unit_prices = UUIDListFilter()
    contract_item_administration = UUIDListFilter()
    has_resources_for_approval = filters.BooleanFilter(
        method="get_has_resources_for_approval"
    )
    measurement_bulletin = ListFilter(method="get_measurement_bulletin_filter")

    entity = UUIDListFilter(method="get_entity")
    additional_control = ListFilter(method="get_additional_control")
    creation_date_before = filters.DateFilter(method="get_creation_date_before")
    creation_date_after = filters.DateFilter(method="get_creation_date_after")
    unit = filters.CharFilter(method="get_unit")
    sort_string = filters.CharFilter(method="get_sort_string")
    content_type = filters.CharFilter(method="get_content_type")
    balance_from = filters.NumberFilter(method="get_balance_from")
    balance_to = filters.NumberFilter(method="get_balance_to")
    unit_price_service_contracts = UUIDListFilter(
        field_name="unit_price_service_contracts"
    )
    administration_service_contracts = UUIDListFilter(
        field_name="administration_service_contracts"
    )
    performance_service_contracts = UUIDListFilter(
        field_name="performance_service_contracts"
    )

    class Meta:
        model = ContractService
        fields = [
            "uuid",
            "description",
            "firms",
            "contract_item_unit_prices",
            "contract_item_administration",
            "entity",
            "additional_control",
            "creation_date_before",
            "creation_date_after",
            "content_type",
            "sort_string",
            "balance_from",
            "balance_to",
        ]


class ContractItemUnitPriceFilter(ContractItemFilter):
    contract_item_unit_price_services = ListFilter()
    services_firms = ListFilter(field_name="contract_item_unit_price_services__firms")
    search = filters.CharFilter(label="search", method="get_search")

    class Meta:
        model = ContractItemUnitPrice
        fields = [
            "uuid",
            "sort_string",
            "entity",
            "resource",
            "contract_item_unit_price_services",
        ]

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "sort_string",
                Value(" "),
                "resource__resource__name",
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )


class ContractItemAdministrationFilter(ContractItemFilter):
    content_type__model = filters.CharFilter()
    contract_item_performance_services = UUIDListFilter()
    contract_item_unit_price_services = UUIDListFilter()
    contract_item_administration_services = UUIDListFilter()
    contract_item_administration_services__firms = UUIDListFilter(
        field_name="contract_item_administration_services__firms"
    )
    content_type = filters.CharFilter(method="get_content_type")
    search = filters.CharFilter(label="search", method="get_search")

    class Meta:
        model = ContractItemAdministration
        fields = [
            "uuid",
            "sort_string",
            "entity",
            "resource",
            "content_type__model",
            "contract_item_performance_services",
            "contract_item_unit_price_services",
            "contract_item_administration_services",
            "contract_item_administration_services__firms",
        ]

    def get_content_type(self, queryset, name, value: str):
        list_value = [x.strip() for x in value.split(",")]
        return queryset.filter(Q(content_type__model__in=list_value)).distinct()

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "sort_string",
                Value(" "),
                "resource__resource__name",
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )


class ContractItemPerformanceFilter(ContractItemFilterBasic):
    contract_item_performance_services = UUIDListFilter()

    class Meta:
        model = ContractItemPerformance
        fields = [
            "uuid",
            "sort_string",
            "entity",
            "resource",
            "contract_item_performance_services",
        ]


class FieldSurveyRoadFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    entity = UUIDListFilter()
    contract = UUIDListFilter()
    start_km = ListFilter()
    end_km = ListFilter()
    road = UUIDListFilter()

    class Meta:
        model = FieldSurveyRoad
        fields = ["uuid", "entity", "contract", "end_km", "start_km", "road"]


class FieldSurveySignatureFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    contract = ListFilter(method="get_contract_signatures")
    user = ListFilter(method="get_responsibles")
    responsibles_hirer = UUIDListFilter()
    responsibles_hired = UUIDListFilter()
    field_survey = UUIDListFilter()

    class Meta:
        model = FieldSurveySignature
        fields = []

    def get_contract_signatures(self, queryset, name, value):
        uuid_list = value.split(",")

        return queryset.filter(field_survey__contract__uuid__in=uuid_list).distinct()

    def get_responsibles(self, queryset, name, value):
        uuid_list = value.split(",")
        return queryset.filter(
            Q(hired__uuid__in=uuid_list) | Q(hirer__uuid__in=uuid_list)
        ).distinct()


class FieldSurveyFilterBase(filters.FilterSet):
    class Meta:
        abstract = True

    def get_signatures(self, queryset, name, value):
        if value == "signed_hirer":
            return queryset.filter(
                signatures__signed_at__isnull=False,
                signatures__hirer__isnull=False,
            )
        elif value == "signed_hired":
            return queryset.filter(
                signatures__signed_at__isnull=False,
                signatures__hired__isnull=False,
            )
        elif value == "pending_hirer":
            return queryset.filter(
                signatures__hirer__isnull=False,
                signatures__signed_at__isnull=True,
            )
        elif value == "pending_hired":
            return queryset.filter(
                signatures__hired__isnull=False,
                signatures__signed_at__isnull=True,
            )
        else:
            raise serializers.ValidationError()

    def filter_executed_at_before(self, queryset, name, value):
        return queryset.filter(executed_at__lte=value)

    def filter_executed_at_after(self, queryset, name, value):
        return queryset.filter(executed_at__gte=value)

    def filter_status(self, queryset, name, value):
        status = value.split(",")
        return queryset.filter(status__in=status)

    def get_type_survey(self, queryset, name, value):
        if value == type_survey_filter.DETAILED_TYPE_SURVEY:
            return queryset.filter(manual=False)
        elif value == type_survey_filter.MANUAL_TYPE_SURVEY:
            return queryset.filter(manual=True)
        elif value == type_survey_filter.ALL_TYPE_SURVEY:
            return queryset
        else:
            raise serializers.ValidationError(
                "kartado.error.field_survey.type_survey_filter.invalid_choice"
            )


class FieldSurveyFilter(FilterSetWithInitialValues):
    uuid = UUIDListFilter()
    contract = UUIDListFilter()
    responsibles_hirer = UUIDListFilter()
    responsibles_hired = UUIDListFilter()
    measurement_bulletin = UUIDListFilter(allow_null=True)
    signature = filters.ChoiceFilter(
        method="get_signatures",
        choices=(
            ("signed_hirer", "signed_hirer"),
            ("signed_hired", "signed_hired"),
            ("pending_hirer", "pending_hirer"),
            ("pending_hired", "pending_hired"),
        ),
    )
    approval_status = filters.ChoiceFilter(
        choices=resource_approval_status.APPROVAL_STATUS_CHOICES
    )
    executed_at_after = filters.DateFilter(method="filter_executed_at_after")
    executed_at_before = filters.DateFilter(method="filter_executed_at_before")
    status = ListFilter(method="filter_status")
    type_survey = filters.CharFilter(
        method="get_type_survey",
        initial=type_survey_filter.DETAILED_TYPE_SURVEY,
    )

    class Meta:
        model = FieldSurvey
        fields = [
            "contract",
            "status",
            "approval_status",
            "approval_date",
            "approved_by",
            "approval_status",
            "executed_at",
        ]

    def get_signatures(self, queryset, name, value):
        if value == "signed_hirer":
            return queryset.filter(
                signatures__signed_at__isnull=False,
                signatures__hirer__isnull=False,
            )
        elif value == "signed_hired":
            return queryset.filter(
                signatures__signed_at__isnull=False,
                signatures__hired__isnull=False,
            )
        elif value == "pending_hirer":
            return queryset.filter(
                signatures__hirer__isnull=False,
                signatures__signed_at__isnull=True,
            )
        elif value == "pending_hired":
            return queryset.filter(
                signatures__hired__isnull=False,
                signatures__signed_at__isnull=True,
            )
        else:
            raise serializers.ValidationError()

    def filter_executed_at_before(self, queryset, name, value):
        return queryset.filter(executed_at__lte=value)

    def filter_executed_at_after(self, queryset, name, value):
        return queryset.filter(executed_at__gte=value)

    def filter_status(self, queryset, name, value):
        status = value.split(",")
        return queryset.filter(status__in=status).distinct()

    def get_type_survey(self, queryset, name, value):
        if value == type_survey_filter.DETAILED_TYPE_SURVEY:
            return queryset.filter(manual=False)
        elif value == type_survey_filter.MANUAL_TYPE_SURVEY:
            return queryset.filter(manual=True)
        elif value == type_survey_filter.ALL_TYPE_SURVEY:
            return queryset
        else:
            raise serializers.ValidationError(
                "kartado.error.field_survey.type_survey_filter.invalid_choice"
            )


class FieldSurveyExportFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    field_survey = UUIDListFilter()
    created_by = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()

    class Meta:
        model = FieldSurveyExport
        fields = [
            "uuid",
            "created_at",
            "created_by",
            "field_survey",
            "done",
            "error",
        ]


class MeasurementBulletinExportFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    measurement_bulletin = UUIDListFilter()
    created_by = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()

    class Meta:
        model = MeasurementBulletinExport
        fields = [
            "uuid",
            "created_at",
            "created_by",
            "measurement_bulletin",
            "done",
            "error",
        ]


class ResourceFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    is_extra = filters.BooleanFilter(field_name="is_extra")
    firm = UUIDListFilter(field_name="resource_service_orders__contract__firm")
    search = filters.CharFilter(label="search", method="get_search")
    only_unit_price_contracts = filters.BooleanFilter(
        method="filter_only_unit_price_contracts"
    )
    contract = ListFilter(method="filter_contract")
    created_by = UUIDListFilter()
    only_unit_price_contracts = filters.BooleanFilter(
        method="filter_only_unit_price_contracts"
    )
    contract = ListFilter(method="filter_contract")

    class Meta:
        model = Resource
        fields = ["company"]

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "name",
                Value(" "),
                "total_amount",
                Value(" "),
                "unit",
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )

    def filter_only_unit_price_contracts(self, queryset, name, value):
        if value is False:
            return queryset
        return queryset.filter(
            resource_service_orders__resource_contract_unit_price_items__isnull=False,
            resource_service_orders__resource_contract_administration_items__isnull=True,
            resource_service_orders__resource_contract_performance_items__isnull=True,
        ).distinct()

    def filter_contract(self, queryset, name, value):
        contract_ids = value.split(",")
        return queryset.filter(
            resource_service_orders__contract__uuid__in=contract_ids
        ).distinct()


class ContractFilter(ContractFilterBase):
    uuid = UUIDListFilter()
    company = ListFilter(method="get_company_filter")
    subcompany = UUIDListFilter()
    firm = ListFilter(method="get_firm")
    date = filters.DateFilter(method="get_date")
    is_internal = filters.BooleanFilter(method="get_is_internal")
    responsible = UUIDListFilter(field_name="responsibles_hirer")
    responsibles_hirer = UUIDListFilter()
    responsibles_hired = UUIDListFilter()
    service_orders = UUIDListFilter()
    search = filters.CharFilter(label="search", method="get_search")
    status = UUIDListFilter()
    number = filters.CharFilter(field_name="extra_info__r_c_number")
    contract_start_after = filters.DateFilter(
        field_name="contract_start", lookup_expr="gte"
    )
    contract_start_before = filters.DateFilter(
        field_name="contract_start", lookup_expr="lte"
    )
    contract_end_after = filters.DateFilter(
        field_name="contract_end", lookup_expr="gte"
    )
    contract_end_before = filters.DateFilter(
        field_name="contract_end", lookup_expr="lte"
    )

    contract_type = ListFilter(method="get_contract_type")

    spent_price_from = filters.NumberFilter(field_name="spent_price", lookup_expr="gte")
    spent_price_to = filters.NumberFilter(field_name="spent_price", lookup_expr="lte")
    performance_months_from = filters.NumberFilter(
        field_name="performance_months", lookup_expr="gte"
    )
    performance_months_to = filters.NumberFilter(
        field_name="performance_months", lookup_expr="lte"
    )
    remaining_price_from = filters.NumberFilter(
        field_name="remaining_price", lookup_expr="gte"
    )
    remaining_price_to = filters.NumberFilter(
        field_name="remaining_price", lookup_expr="lte"
    )
    accounting_classification = filters.CharFilter(
        method="get_accounting_classification"
    )
    has_unit_price_or_administration_service = filters.BooleanFilter(
        method="get_unit_price_or_administration_service"
    )

    class Meta:
        model = Contract
        fields = ["company", "subcompany"]


class ContractAdditiveFilter(filters.FilterSet):

    uuid = UUIDListFilter()
    company = UUIDListFilter()
    contract = UUIDListFilter()
    created_by = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    number = filters.CharFilter(lookup_expr="icontains")
    description = filters.CharFilter(lookup_expr="icontains")
    notes = filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = ContractAdditive
        fields = [
            "additional_percentage",
            "old_price",
            "new_price",
            "done",
            "error",
        ]


class ContractPeriodFilter(filters.FilterSet):

    uuid = UUIDListFilter()
    company = UUIDListFilter()
    contract = UUIDListFilter()
    firms = UUIDListFilter()
    created_by = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()

    class Meta:
        model = ContractPeriod
        fields = [
            "hours",
        ]
