from django.contrib import admin
from django.db.models import Prefetch

from apps.companies.models import Company

from . import models


class PermissionOccurrenceKindRestrictionInline(admin.TabularInline):
    model = models.PermissionOccurrenceKindRestriction
    extra = 0
    autocomplete_fields = ("company",)
    verbose_name = "Restrição de Natureza"
    verbose_name_plural = "Restrições de Natureza (Occurrence Kind)"


class UserPermissionAdmin(admin.ModelAdmin):
    model = models.UserPermission

    list_display = ("name", "companies_names", "is_inactive")

    def companies_names(self, obj):
        return "\n".join([comp.name for comp in obj.companies.all()])

    search_fields = ["name", "companies__name"]
    list_filter = ("companies__name",)
    autocomplete_fields = ("companies",)
    inlines = [PermissionOccurrenceKindRestrictionInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related(
            Prefetch("companies", queryset=Company.objects.all().only("uuid", "name")),
            Prefetch(
                "occurrence_kind_restrictions",
                queryset=models.PermissionOccurrenceKindRestriction.objects.select_related(
                    "company"
                ),
            ),
        )


admin.site.register(models.UserPermission, UserPermissionAdmin)
