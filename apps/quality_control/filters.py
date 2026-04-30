from django.db.models import Q, TextField, Value
from django.db.models.functions import Concat
from django_filters.filters import CharFilter
from django_filters.rest_framework import FilterSet

from apps.companies.models import Company, Firm
from apps.work_plans.models import Job
from helpers.apps.daily_reports import (
    get_uuids_jobs_user_firms,
    get_uuids_rdos_user_firms,
)
from helpers.filters import DateFromToRangeCustomFilter, KeyFilter, UUIDListFilter

from .models import (
    ConstructionPlant,
    QualityAssay,
    QualityControlExport,
    QualityProject,
    QualitySample,
)


class QualityProjectFilter(FilterSet):
    uuid = UUIDListFilter()
    firm = UUIDListFilter()
    occurrence_type = UUIDListFilter()
    form_data = KeyFilter(allow_null=True)
    search = CharFilter(label="search", method="get_search")

    class Meta:
        model = QualityProject
        fields = [
            "uuid",
            "project_number",
            "firm",
            "created_at",
            "registered_at",
            "expires_at",
            "occurrence_type",
            "form_data",
        ]

    def get_search(self, queryset, name, value):
        queryset = queryset.annotate(
            search=Concat(
                "project_number",
                Value(" "),
                "occurrence_type__name",
                output_field=TextField(),
            )
        )

        return queryset.filter(search__unaccent__icontains=value).distinct()


class ConstructionPlantFilter(FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    created_by = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    search = CharFilter(label="search", method="get_search")

    class Meta:
        model = ConstructionPlant
        fields = ["uuid", "name", "company", "created_at", "created_by"]

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "name",
                Value(" "),
                "construction_plant_quality_samples__occurrence_type__name",
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )


class QualitySampleFilter(FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    created_by = UUIDListFilter()
    responsible = UUIDListFilter()
    quality_project = UUIDListFilter()
    construction_firm = UUIDListFilter()
    construction_plant = UUIDListFilter()
    reportings = UUIDListFilter()
    occurrence_type = UUIDListFilter()
    collected_at = DateFromToRangeCustomFilter()
    created_at = DateFromToRangeCustomFilter()
    received_at = DateFromToRangeCustomFilter()
    form_data = KeyFilter(allow_null=True)
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")
    search = CharFilter(label="search", method="get_search")

    class Meta:
        model = QualitySample
        fields = [
            "uuid",
            "company",
            "collected_at",
            "created_at",
            "created_by",
            "responsible",
            "quality_project",
            "construction_firm",
            "construction_plant",
            "occurrence_type",
            "reportings",
            "form_data",
            "number",
            "received_at",
            "is_proof",
        ]

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        jobs_section, rdos_section = value.split("|")

        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        jobs_uuids = get_uuids_jobs_user_firms(jobs_section, company, self.request.user)
        rdos_uuids = get_uuids_rdos_user_firms(rdos_section, company, self.request.user)

        return queryset.filter(
            Q(reportings__job_id__in=jobs_uuids)
            | Q(reportings__reporting_multiple_daily_reports__in=rdos_uuids)
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
            Q(reportings__job_id__in=jobs_by_count)
            | Q(reportings__job_id__in=jobs_by_ids)
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
            Q(reportings__reporting_multiple_daily_reports__firm__in=firms_by_count)
            | Q(reportings__reporting_multiple_daily_reports__firm__in=firms_by_ids)
        ).distinct()

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "number",
                Value(" "),
                "occurrence_type__name",
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )


class QualityAssayFilter(FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    executed_at = DateFromToRangeCustomFilter()
    created_by = UUIDListFilter()
    responsible = UUIDListFilter()
    quality_project = UUIDListFilter()
    occurence_type = UUIDListFilter()
    quality_sample = UUIDListFilter()
    related_assays = UUIDListFilter()
    reportings = UUIDListFilter()
    form_data = KeyFilter(allow_null=True)
    csv_import = UUIDListFilter()
    search = CharFilter(label="search", method="get_search")

    class Meta:
        model = QualityAssay
        fields = [
            "uuid",
            "number",
            "company",
            "created_at",
            "executed_at",
            "created_by",
            "responsible",
            "quality_project",
            "occurrence_type",
            "related_assays",
            "quality_sample",
            "reportings",
            "form_data",
            "csv_import",
        ]

    def get_search(self, queryset, name, value):
        queryset = queryset.annotate(
            search=Concat(
                "number",
                Value(" "),
                "occurrence_type__name",
                output_field=TextField(),
            )
        )

        return queryset.filter(search__unaccent__icontains=value).distinct()


class QualityControlExportFilter(FilterSet):
    uuid = UUIDListFilter()
    reporting = UUIDListFilter()
    created_by = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()

    class Meta:
        model = QualityControlExport
        fields = ["uuid", "reporting", "created_at", "created_by"]
