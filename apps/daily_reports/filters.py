import functools

from django.db.models import Exists, OuterRef, Q
from django_filters.filters import (
    BooleanFilter,
    CharFilter,
    ChoiceFilter,
    DateFilter,
    DateFromToRangeFilter,
)
from django_filters.rest_framework import FilterSet

from apps.companies.models import Company
from apps.resources.models import ContractItemAdministration, ContractService
from apps.service_orders.const import file_choices
from helpers.apps.daily_reports import (
    filter_board_item_contract_services,
    filter_jobs_rdos_user_firms,
    filter_num_jobs_only_user_firms,
    filter_num_user_firms,
    get_uuids_rdos_user_firms,
)
from helpers.filters import DateFromToRangeCustomFilter, ListFilter, UUIDListFilter
from helpers.strings import check_image_file

from .const import export_formats, origin_choices, weather_forecast, work_conditions
from .models import (
    DailyReport,
    DailyReportContractUsage,
    DailyReportEquipment,
    DailyReportExport,
    DailyReportExternalTeam,
    DailyReportOccurrence,
    DailyReportRelation,
    DailyReportResource,
    DailyReportSignaling,
    DailyReportVehicle,
    DailyReportWorker,
    MultipleDailyReport,
    MultipleDailyReportFile,
    MultipleDailyReportSignature,
    ProductionGoal,
)


class BaseDailyReportFilter(FilterSet):
    uuid = UUIDListFilter()
    date = DateFilter()
    date_range = DateFromToRangeFilter(field_name="date")
    created_by = UUIDListFilter()
    responsible = UUIDListFilter()
    inspector = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    approval_step = UUIDListFilter()
    contract = UUIDListFilter()

    # Weather
    morning_weather = ChoiceFilter(choices=weather_forecast.WEATHER_FORECAST_CHOICES)
    afternoon_weather = ChoiceFilter(choices=weather_forecast.WEATHER_FORECAST_CHOICES)
    night_weather = ChoiceFilter(choices=weather_forecast.WEATHER_FORECAST_CHOICES)

    # Conditions
    morning_conditions = ChoiceFilter(choices=work_conditions.WORK_CONDITION_CHOICES)
    afternoon_conditions = ChoiceFilter(choices=work_conditions.WORK_CONDITION_CHOICES)
    night_conditions = ChoiceFilter(choices=work_conditions.WORK_CONDITION_CHOICES)

    number_list = ListFilter(method="get_number_list")

    class Meta:
        fields = [
            "uuid",
            "company",
            "date",
            "day_without_work",
            "created_by",
            "responsible",
            "created_at",
            "notes",
            "number",
            "use_reporting_resources",
            "editable",
            "approval_step",
            # Weather
            "morning_weather",
            "afternoon_weather",
            "night_weather",
            # Conditions
            "morning_conditions",
            "afternoon_conditions",
            "night_conditions",
            # Duration
            "morning_start",
            "morning_end",
            "afternoon_start",
            "afternoon_end",
            "night_start",
            "night_end",
            # M2M
            "reporting_files",
        ]

    def get_number_list(self, queryset, name, value):
        number_list = [item for item in value.replace(" ", "").split(",") if item]

        return queryset.filter(
            functools.reduce(
                lambda acc, x: acc | Q(number__icontains=x), number_list, Q()
            )
        ).distinct()


class DailyReportFilter(BaseDailyReportFilter):
    class Meta(BaseDailyReportFilter.Meta):
        model = DailyReport


class MultipleDailyReportFilter(BaseDailyReportFilter):
    firm = UUIDListFilter()
    reportings = UUIDListFilter()
    has_reportings = BooleanFilter(method="get_has_reportings")
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    firm__subcompany = UUIDListFilter()
    compensation = BooleanFilter()
    has_signatures = BooleanFilter(method="get_has_signatures")

    class Meta(BaseDailyReportFilter.Meta):
        model = MultipleDailyReport
        fields = BaseDailyReportFilter.Meta.fields + [
            "firm",
            "reportings",
            "legacy_number",
            "compensation",
        ]

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        _jobs_section, rdos_section = value.split("|")

        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        rdos_uuids = get_uuids_rdos_user_firms(rdos_section, company, self.request.user)

        return queryset.filter(uuid__in=rdos_uuids)

    def get_has_reportings(self, queryset, _, value):
        return queryset.exclude(reportings__isnull=value)

    def get_has_signatures(self, queryset, name, value):
        if value is True:
            return queryset.filter(
                multiple_daily_report_signatures__isnull=False
            ).distinct()
        elif value is False:
            return queryset.filter(
                multiple_daily_report_signatures__isnull=True
            ).distinct()
        else:
            return queryset


class DailyReportWorkerFilter(FilterSet):
    uuid = UUIDListFilter()
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")
    creation_date = DateFromToRangeCustomFilter()
    contract_item_administration = UUIDListFilter()
    firm = UUIDListFilter()
    approved_by = UUIDListFilter()
    contract_service = ListFilter(method="get_contract_service")
    measurement_bulletin = UUIDListFilter()
    service_order_resource = UUIDListFilter(
        field_name="contract_item_administration__resource"
    )
    reportings = UUIDListFilter(field_name="multiple_daily_reports__reportings")

    class Meta:
        model = DailyReportWorker
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "firm",
            "members",
            "amount",
            "role",
            "creation_date",
            "total_price",
            "contract_item_administration",
            "approval_status",
            "approval_date",
            "approved_by",
        ]

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        return filter_jobs_rdos_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_jobs_only_user_firms(self, queryset, name, value):
        return filter_num_jobs_only_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_user_firms(self, queryset, name, value):
        return filter_num_user_firms(value, queryset, self.request.user, self.data)

    def get_contract_service(self, queryset, name, value):
        contract_service_ids = value.split(",")
        return filter_board_item_contract_services(queryset, contract_service_ids)


class DailyReportExternalTeamFilter(FilterSet):
    uuid = UUIDListFilter()
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")
    reportings = UUIDListFilter(field_name="multiple_daily_reports__reportings")

    class Meta:
        model = DailyReportExternalTeam
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "company",
            "contract_number",
            "contractor_name",
            "amount",
            "contract_description",
        ]

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        return filter_jobs_rdos_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_jobs_only_user_firms(self, queryset, name, value):
        return filter_num_jobs_only_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_user_firms(self, queryset, name, value):
        return filter_num_user_firms(value, queryset, self.request.user, self.data)


class DailyReportEquipmentFilter(FilterSet):
    uuid = UUIDListFilter()
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")
    creation_date = DateFromToRangeCustomFilter()
    contract_item_administration = UUIDListFilter()
    approved_by = UUIDListFilter()
    contract_service = UUIDListFilter(method="get_contract_service")
    measurement_bulletin = UUIDListFilter()
    service_order_resource = UUIDListFilter(
        field_name="contract_item_administration__resource"
    )
    reportings = UUIDListFilter(field_name="multiple_daily_reports__reportings")

    class Meta:
        model = DailyReportEquipment
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "company",
            "kind",
            "description",
            "amount",
            "creation_date",
            "total_price",
            "contract_item_administration",
            "approval_status",
            "approval_date",
            "approved_by",
        ]

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        return filter_jobs_rdos_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_jobs_only_user_firms(self, queryset, name, value):
        return filter_num_jobs_only_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_user_firms(self, queryset, name, value):
        return filter_num_user_firms(value, queryset, self.request.user, self.data)

    def get_contract_service(self, queryset, name, value):
        contract_service_ids = value.split(",")
        return filter_board_item_contract_services(queryset, contract_service_ids)


class DailyReportVehicleFilter(FilterSet):
    uuid = UUIDListFilter()
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")
    creation_date = DateFromToRangeCustomFilter()
    contract_item_administration = UUIDListFilter()
    approved_by = UUIDListFilter()
    contract_service = ListFilter(method="get_contract_service")
    measurement_bulletin = UUIDListFilter()
    service_order_resource = UUIDListFilter(
        field_name="contract_item_administration__resource"
    )
    reportings = UUIDListFilter(field_name="multiple_daily_reports__reportings")

    class Meta:
        model = DailyReportVehicle
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "company",
            "kind",
            "description",
            "amount",
            "creation_date",
            "total_price",
            "contract_item_administration",
            "approval_status",
            "approval_date",
            "approved_by",
        ]

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        return filter_jobs_rdos_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_jobs_only_user_firms(self, queryset, name, value):
        return filter_num_jobs_only_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_user_firms(self, queryset, name, value):
        return filter_num_user_firms(value, queryset, self.request.user, self.data)

    def get_contract_service(self, queryset, name, value):
        contract_service_ids = value.split(",")
        return filter_board_item_contract_services(queryset, contract_service_ids)


class DailyReportSignalingFilter(FilterSet):
    uuid = UUIDListFilter()
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")
    reportings = UUIDListFilter(field_name="multiple_daily_reports__reportings")

    class Meta:
        model = DailyReportSignaling
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "company",
            "kind",
        ]

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        return filter_jobs_rdos_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_jobs_only_user_firms(self, queryset, name, value):
        return filter_num_jobs_only_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_user_firms(self, queryset, name, value):
        return filter_num_user_firms(value, queryset, self.request.user, self.data)


class DailyReportResourceFilter(FilterSet):
    uuid = UUIDListFilter()
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")
    reportings = UUIDListFilter(field_name="multiple_daily_reports__reportings")

    class Meta:
        model = DailyReportResource
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "kind",
            "amount",
            "resource",
        ]

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        return filter_jobs_rdos_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_jobs_only_user_firms(self, queryset, name, value):
        return filter_num_jobs_only_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_user_firms(self, queryset, name, value):
        return filter_num_user_firms(value, queryset, self.request.user, self.data)


class DailyReportOccurrenceFilter(FilterSet):
    uuid = UUIDListFilter()
    daily_reports = UUIDListFilter()
    multiple_daily_reports = UUIDListFilter()
    firm = UUIDListFilter()
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")
    reportings = UUIDListFilter(field_name="multiple_daily_reports__reportings")

    class Meta:
        model = DailyReportOccurrence
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "firm",
            "starts_at",
            "ends_at",
            "impact_duration",
            "description",
            "extra_info",
        ]

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        return filter_jobs_rdos_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_jobs_only_user_firms(self, queryset, name, value):
        return filter_num_jobs_only_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_user_firms(self, queryset, name, value):
        return filter_num_user_firms(value, queryset, self.request.user, self.data)


class ProductionGoalFilter(FilterSet):
    uuid = UUIDListFilter()
    starts_at = DateFromToRangeFilter()
    ends_at = DateFromToRangeFilter()
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")
    reportings = UUIDListFilter(field_name="multiple_daily_reports__reportings")

    class Meta:
        model = ProductionGoal
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "service",
            "starts_at",
            "ends_at",
            "days_of_work",
            "amount",
        ]

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        return filter_jobs_rdos_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_jobs_only_user_firms(self, queryset, name, value):
        return filter_num_jobs_only_user_firms(
            value, queryset, self.request.user, self.data
        )

    def get_num_user_firms(self, queryset, name, value):
        return filter_num_user_firms(value, queryset, self.request.user, self.data)


class DailyReportRelationFilter(FilterSet):
    uuid = UUIDListFilter()
    contract_service = ListFilter(method="get_contract_service")

    class Meta:
        model = DailyReportRelation
        fields = [
            "uuid",
            "active",
            "daily_report",
            "multiple_daily_report",
            "worker",
            "external_team",
            "equipment",
            "vehicle",
            "signaling",
            "occurrence",
            "resource",
            "production_goal",
            "contract_service",
        ]

    def get_contract_service(self, queryset, name, value):
        contract_service_ids = value.split(",")
        return queryset.filter(
            Q(
                worker__contract_item_administration__contract_item_administration_services__uuid__in=contract_service_ids
            )
            | Q(
                equipment__contract_item_administration__contract_item_administration_services__uuid__in=contract_service_ids
            )
            | Q(
                vehicle__contract_item_administration__contract_item_administration_services__uuid__in=contract_service_ids
            )
        )


class DailyReportExportFilter(FilterSet):
    uuid = UUIDListFilter()
    daily_reports = UUIDListFilter()
    multiple_daily_reports = UUIDListFilter()
    created_by = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    format = ChoiceFilter(choices=export_formats.EXPORT_FORMAT_CHOICES)

    class Meta:
        model = DailyReportExport
        fields = [
            "uuid",
            "created_at",
            "created_by",
            "daily_reports",
            "multiple_daily_reports",
            "done",
            "error",
            "format",
            "export_photos",
        ]


class DailyReportContractUsageFilter(FilterSet):
    uuid = UUIDListFilter()
    worker = UUIDListFilter()
    equipment = UUIDListFilter()
    vehicle = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    contract_service = ListFilter(method="get_contract_service")
    contract = ListFilter(method="get_contract")
    measurement_bulletin = ListFilter(method="get_measurement_bulletin")
    approval_status = CharFilter(method="get_approval_status")
    approval_step = ListFilter(method="get_approval_step")
    multiple_daily_report__executed_at_after = DateFilter(
        method="get_executed_at_after"
    )
    multiple_daily_report__executed_at_before = DateFilter(
        method="get_executed_at_before"
    )
    has_daily_report_item = BooleanFilter(method="get_with_daily_report_item")

    origin_of_creation = ChoiceFilter(
        choices=origin_choices.ORIGIN_CHOICES,
        method="filter_origin_of_creation",
        label="origin_of_creation",
    )
    creation_date_before = DateFilter(method="get_executed_at_before")
    creation_date_after = DateFilter(method="get_executed_at_after")
    number_list = ListFilter(method="get_number_list")
    firm = UUIDListFilter(method="get_firm")

    class Meta:
        model = DailyReportContractUsage
        fields = [
            "uuid",
            "worker",
            "equipment",
            "vehicle",
            "created_at",
            "contract_service",
        ]

    def get_with_daily_report_item(self, queryset, name, value):
        # OPTIMIZED: Usar campo M2M multiple_daily_reports denormalizado
        return queryset.filter(multiple_daily_reports__isnull=value).distinct()

    def get_executed_at_after(self, queryset, name, value):
        # OPTIMIZED: Usar campo M2M multiple_daily_reports denormalizado
        return queryset.filter(multiple_daily_reports__date__gte=value).distinct()

    def get_executed_at_before(self, queryset, name, value):
        # OPTIMIZED: Usar campo M2M multiple_daily_reports denormalizado
        return queryset.filter(multiple_daily_reports__date__lte=value).distinct()

    def get_approval_step(self, queryset, name, value):
        ids = value.split(",")
        # OPTIMIZED: Usar campo M2M multiple_daily_reports denormalizado
        return queryset.filter(
            multiple_daily_reports__approval_step__uuid__in=ids
        ).distinct()

    def get_contract(self, queryset, name, value):
        # OPTIMIZED: Usar campo contract_item_administration denormalizado
        contract_ids = value.split(",")

        contract_exists = Exists(
            ContractItemAdministration.objects.filter(
                pk=OuterRef("contract_item_administration_id"),
                resource__contract__uuid__in=contract_ids,
            )
        )

        annotated = queryset.annotate(
            has_contract=contract_exists,
        )

        return annotated.filter(has_contract=True).distinct()

    def get_contract_service(self, queryset, name, value):
        # OPTIMIZED: Usar campo contract_item_administration denormalizado
        contract_service_ids = value.split(",")

        contract_service_exists = Exists(
            ContractService.objects.filter(
                contract_item_administration__pk=OuterRef(
                    "contract_item_administration_id"
                ),
                uuid__in=contract_service_ids,
            )
        )

        annotated = queryset.annotate(
            has_contract_service=contract_service_exists,
        )

        return annotated.filter(has_contract_service=True).distinct()

    def get_approval_status(self, queryset, name, value):
        return queryset.filter(
            Q(worker__approval_status=value)
            | Q(equipment__approval_status=value)
            | Q(vehicle__approval_status=value)
        )

    def get_measurement_bulletin(self, queryset, name, value):
        # OPTIMIZED: Usar campo measurement_bulletin denormalizado
        values = value.split(",")
        check_null = "null" in values

        if check_null:
            values.remove("null")

        filters = Q()

        if check_null:
            filters |= Q(measurement_bulletin__isnull=True)

        if values:
            filters |= Q(measurement_bulletin__in=values)

        return queryset.filter(filters).distinct()

    def filter_origin_of_creation(self, queryset, name, value):
        if value == "MANUAL":
            return queryset.filter(
                Q(worker__multiple_daily_reports__isnull=True)
                & Q(vehicle__multiple_daily_reports__isnull=True)
                & Q(equipment__multiple_daily_reports__isnull=True)
            ).distinct()
        elif value == "RDO":
            return queryset.filter(
                Q(worker__multiple_daily_reports__isnull=False)
                | Q(vehicle__multiple_daily_reports__isnull=False)
                | Q(equipment__multiple_daily_reports__isnull=False)
            ).distinct()

    def get_number_list(self, queryset, name, value):
        number_list = [item for item in value.replace(" ", "").split(",") if item]
        # OPTIMIZED: Use denormalized M2M field multiple_daily_reports instead of 3 separate paths
        return queryset.filter(
            functools.reduce(
                lambda acc, x: acc | Q(multiple_daily_reports__number__icontains=x),
                number_list,
                Q(),
            )
        ).distinct()

    def get_firm(self, queryset, name, value):
        ids = value.split(",")
        # OPTIMIZED: Use denormalized M2M field multiple_daily_reports instead of 3 separate paths
        return queryset.filter(multiple_daily_reports__firm__uuid__in=ids).distinct()


class MultipleDailyReportFileFilter(FilterSet):
    company = CharFilter(field_name="multiple_daily_report__company__uuid")
    multiple_daily_report = ListFilter()
    uuid = ListFilter()
    datetime = DateFromToRangeCustomFilter()
    rdos_user_firms = CharFilter(method="filter_rdos_user_firms")
    file_type = ChoiceFilter(
        choices=file_choices.FILE_CHOICES,
        method="check_image",
        label="file_type",
    )

    class Meta:
        model = MultipleDailyReportFile
        fields = ["company", "multiple_daily_report", "legacy_uuid"]

    def filter_rdos_user_firms(self, queryset, name, value):
        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        rdos_uuids = get_uuids_rdos_user_firms(value, company, self.request.user)
        return queryset.filter(multiple_daily_report_id__in=rdos_uuids).distinct()

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


class MultipleDailyReportSignatureFilter(FilterSet):
    company = UUIDListFilter(field_name="multiple_daily_report__company__uuid")
    multiple_daily_report = UUIDListFilter()
    uuid = UUIDListFilter()
    signature_date = DateFromToRangeCustomFilter()
    uploaded_at = DateFromToRangeCustomFilter()
    created_by = UUIDListFilter()
    signature_name = CharFilter(lookup_expr="icontains")
    rdos_user_firms = CharFilter(method="filter_rdos_user_firms")

    class Meta:
        model = MultipleDailyReportSignature
        fields = ["multiple_daily_report", "created_by"]

    def filter_rdos_user_firms(self, queryset, name, value):
        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        rdos_uuids = get_uuids_rdos_user_firms(value, company, self.request.user)
        return queryset.filter(multiple_daily_report_id__in=rdos_uuids).distinct()
