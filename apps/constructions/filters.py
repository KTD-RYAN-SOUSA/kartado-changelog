from django.contrib.postgres.aggregates import StringAgg
from django.db.models import TextField, Value
from django.db.models.functions import Concat
from django_filters.filters import BooleanFilter, CharFilter
from django_filters.rest_framework import FilterSet

from helpers.filters import (
    DateFromToRangeCustomFilter,
    KeyFilter,
    ListFilter,
    ListRangeFilter,
    UUIDListFilter,
)

from .models import Construction, ConstructionProgress


class ConstructionFilter(FilterSet):
    uuid = UUIDListFilter()
    created_by = UUIDListFilter()
    km = ListRangeFilter()
    end_km = ListRangeFilter()
    company = UUIDListFilter()
    construction_item = CharFilter(lookup_expr="icontains")
    intervention_type = ListFilter()
    search = CharFilter(
        label="search",
        method="get_search",
        distinct=True,
        lookup_expr="icontains",
    )

    # JSON Fields
    phases = KeyFilter(allow_null=True)
    spend_schedule = KeyFilter(allow_null=True)

    # Dates
    created_at = DateFromToRangeCustomFilter()
    scheduling_start_date = DateFromToRangeCustomFilter()
    scheduling_end_date = DateFromToRangeCustomFilter()
    analysis_start_date = DateFromToRangeCustomFilter()
    analysis_end_date = DateFromToRangeCustomFilter()
    execution_start_date = DateFromToRangeCustomFilter()
    execution_end_date = DateFromToRangeCustomFilter()
    spend_schedule_start_date = DateFromToRangeCustomFilter()
    spend_schedule_end_date = DateFromToRangeCustomFilter()

    class Meta:
        model = Construction
        fields = [
            "uuid",
            "company",
            "name",
            "description",
            "location",
            "km",
            "end_km",
            "construction_item",
            "intervention_type",
            "created_by",
            "created_at",
            "scheduling_start_date",
            "scheduling_end_date",
            "analysis_start_date",
            "analysis_end_date",
            "execution_start_date",
            "execution_end_date",
            "spend_schedule_start_date",
            "spend_schedule_end_date",
            "origin",
        ]

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "name",
                Value(" "),
                "description",
                Value(" "),
                "location",
                Value(" "),
                "km",
                Value(" "),
                "end_km",
                Value(" "),
                StringAgg("construction_progresses__name", delimiter="", distinct=True),
                output_field=TextField(),
            )
        )
        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )


class ConstructionProgressFilter(FilterSet):
    uuid = UUIDListFilter()
    construction = UUIDListFilter(allow_null=True)
    reportings = UUIDListFilter()
    created_by = UUIDListFilter()
    progress_details = KeyFilter(allow_null=True)

    created_at = DateFromToRangeCustomFilter()
    executed_at = DateFromToRangeCustomFilter()
    only_last_progress = BooleanFilter(method="filter_only_last_progress")
    exclude_last_progress = BooleanFilter(method="filter_exclude_last_progress")

    class Meta:
        model = ConstructionProgress
        fields = [
            "uuid",
            "name",
            "created_at",
            "executed_at",
            "created_by",
            "construction",
            "progress_details",
            "reportings",
        ]

    def filter_only_last_progress(self, queryset, name, value):
        if value is True:
            most_recent = queryset.order_by("-created_at").first()
            if most_recent:
                return queryset.exclude(created_at__lt=most_recent.created_at)
            else:
                return queryset.none()
        else:
            return queryset

    def filter_exclude_last_progress(self, queryset, name, value):
        if value is True:
            most_recent = queryset.order_by("-created_at").first()
            if most_recent:
                return queryset.exclude(uuid=most_recent.uuid)
            else:
                return queryset.none()
        else:
            return queryset
