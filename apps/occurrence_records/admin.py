from django.contrib import admin
from django.db.models import Case, IntegerField, Prefetch, When

from apps.companies.models import Company

from . import models


class SpecsInline(admin.StackedInline):
    model = models.OccurrenceTypeSpecs
    extra = 0
    autocomplete_fields = ("company",)


def companies_names(obj):
    companies_names = [comp.name for comp in obj.company.all()]
    return companies_names


companies_names.short_description = "Companies"


class OccurrenceTypeAdmin(admin.ModelAdmin):
    search_fields = ["name", "occurrencetype_specs__company__name"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "firms",
                    "occurrence_kind",
                    "form_fields",
                    "goal_formula",
                    "monitoring_plan",
                    "created_by",
                    "deadline",
                    "active",
                    "previous_version",
                    "is_oae",
                    "show_in_web_map",
                    "show_in_app_map",
                    "custom_map_table",
                )
            },
        ),
    )
    autocomplete_fields = ("firms", "previous_version", "monitoring_plan", "created_by")
    inlines = [SpecsInline]
    list_display = ("name", companies_names)
    list_filter = ("company__name",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related(
            Prefetch("company", queryset=Company.objects.all().only("name"))
        )

    def get_search_results(self, request, queryset, search_term):
        """
        Custom search implementation for better performance
        """
        if not search_term:
            return queryset, False

        exact_matches = queryset.none()
        name_contains = queryset.none()
        company_results = queryset.none()

        exact_matches = queryset.filter(name__iexact=search_term)

        if search_term:
            name_contains = queryset.filter(name__icontains=search_term).exclude(
                name__iexact=search_term
            )

        company_specs = (
            models.OccurrenceTypeSpecs.objects.filter(
                company__name__icontains=search_term
            )
            .values_list("occurrence_type__uuid", flat=True)
            .distinct()
        )

        if company_specs:
            excluded_uuids = list(exact_matches.values_list("uuid", flat=True)) + list(
                name_contains.values_list("uuid", flat=True)
            )
            company_results = queryset.filter(uuid__in=company_specs)
            if excluded_uuids:
                company_results = company_results.exclude(uuid__in=excluded_uuids)

        combined_results = (
            list(exact_matches) + list(name_contains) + list(company_results)
        )

        uuids = [obj.uuid for obj in combined_results]
        order = Case(
            *[When(uuid=uuid, then=pos) for pos, uuid in enumerate(uuids)],
            output_field=IntegerField()
        )

        return queryset.filter(uuid__in=uuids).order_by(order), True


class OccurrenceTypeSpecsAdmin(admin.ModelAdmin):
    search_fields = ["company__name", "occurrence_type__name"]
    autocomplete_fields = ("occurrence_type", "company")


class OccurrenceRecordAdmin(admin.ModelAdmin):
    search_fields = [
        "company__name",
        "number",
        "city__name",
        "uf_code",
        "status",
        "created_at",
    ]
    autocomplete_fields = [
        "company",
        "occurrence_type",
        "firm",
        "responsible",
    ]
    raw_id_fields = [
        "city",
        "river",
        "created_by",
        "occurrence_type",
        "status",
        "operational_control",
        "monitoring_plan",
        "parent_action",
        "firm",
        "responsible",
        "approval_step",
        "active_tile_layer",
        "integration_run",
        "active_shape_files",
        "service_orders",
        "search_tags",
    ]
    list_filter = ["company__name", "created_at"]


class DataSeriesAdmin(admin.ModelAdmin):
    autocomplete_fields = [
        "company",
        "instrument_type",
        "instrument_record",
        "sih_monitoring_point",
        "sih_monitoring_parameter",
        "created_by",
    ]
    list_display = ["company", "kind", "name", "field_name"]
    list_filter = ["company__name", "kind"]
    search_fields = ["company__name", "kind", "name", "field_name"]


class CustomDashboardAdmin(admin.ModelAdmin):
    autocomplete_fields = [
        "company",
        "instrument_types",
        "instrument_records",
        "sih_monitoring_points",
        "sih_monitoring_parameters",
    ]
    raw_id_fields = [
        "cities",
        "can_be_viewed_by",
        "can_be_edited_by",
        "sih_monitoring_points",
    ]
    list_display = ["company"]
    list_filter = ["company__name"]
    search_fields = ["company__name"]


class RecordPanelAdmin(admin.ModelAdmin):
    model = models.RecordPanel
    search_fields = ["company__name", "name"]
    list_filter = ("company__name",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related(Prefetch("company", queryset=Company.objects.all()))


admin.site.register(models.OccurrenceType, OccurrenceTypeAdmin)
admin.site.register(models.OccurrenceRecord, OccurrenceRecordAdmin)
admin.site.register(models.OccurrenceTypeSpecs, OccurrenceTypeSpecsAdmin)
admin.site.register(models.OccurrenceRecordWatcher)
admin.site.register(models.RecordPanel, RecordPanelAdmin)
admin.site.register(models.RecordPanelShowList)
admin.site.register(models.RecordPanelShowWebMap)
admin.site.register(models.RecordPanelShowMobileMap)
admin.site.register(models.CustomDashboard, CustomDashboardAdmin)
admin.site.register(models.DataSeries, DataSeriesAdmin)
admin.site.register(models.CustomTable)
admin.site.register(models.TableDataSeries)
