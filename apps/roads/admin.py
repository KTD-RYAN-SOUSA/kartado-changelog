from django.contrib import admin
from django.db.models import Prefetch

from apps.companies.models import Company

from . import models


class IsDefaultSegmentFilter(admin.SimpleListFilter):
    title = "Segmento Padrão"
    parameter_name = "is_default_segment"

    def lookups(self, request, model_admin):
        return (
            ("1", "Sim"),
            ("0", "Não"),
        )

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(is_default_segment=True)
        if self.value() == "0":
            return queryset.filter(is_default_segment=False)
        if self.value() == "both":
            return queryset
        return queryset


class RoadAdmin(admin.ModelAdmin):
    model = models.Road

    list_display = ("name", "direction", "uf", "companies_names", "is_default_segment")

    def companies_names(self, obj):
        return "\n".join([comp.name for comp in obj.company.all()])

    search_fields = ["name", "company__name"]
    list_filter = (IsDefaultSegmentFilter, "company__name")
    autocomplete_fields = ("company",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related(
            Prefetch("company", queryset=Company.objects.all().only("uuid", "name"))
        )


admin.site.register(models.Road, RoadAdmin)
