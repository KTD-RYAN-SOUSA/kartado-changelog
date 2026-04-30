from django.contrib import admin
from django.db.models import Prefetch

from apps.companies.models import Company

from . import models


class ShapeFileAdmin(admin.ModelAdmin):
    model = models.ShapeFile
    search_fields = ["companies__name", "name"]
    list_filter = ("companies__name",)
    autocomplete_fields = (
        "companies",
        "parent",
        "created_by",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related(
            Prefetch("companies", queryset=Company.objects.all().only("uuid", "name"))
        )


class TileLayerAdmin(admin.ModelAdmin):
    model = models.TileLayer

    autocomplete_fields = ("companies",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related(
            Prefetch("companies", queryset=Company.objects.all().only("uuid", "name"))
        )


admin.site.register(models.TileLayer, TileLayerAdmin)
admin.site.register(models.ShapeFile, ShapeFileAdmin)
