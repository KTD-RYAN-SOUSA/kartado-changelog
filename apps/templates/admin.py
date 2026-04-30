from django.contrib import admin
from django.db.models import Prefetch

from apps.companies.models import Company
from apps.occurrence_records.models import OccurrenceType

from . import models


class SearchTagOccurrenceTypeAdmin(admin.ModelAdmin):
    model = models.SearchTagOccurrenceType
    search_fields = ["company__name", "search_tags__name"]
    list_filter = ("company__name",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related(
            Prefetch("company", queryset=Company.objects.all()),
            Prefetch("search_tags", queryset=models.SearchTag.objects.all()),
            Prefetch("occurrence_type", queryset=OccurrenceType.objects.all()),
        )


admin.site.register(models.Template)
admin.site.register(models.Log)
admin.site.register(models.CanvasList)
admin.site.register(models.CanvasCard)
admin.site.register(models.AppVersion)
admin.site.register(models.ExportRequest)
admin.site.register(models.MobileSync)
admin.site.register(models.ActionLog)
admin.site.register(models.SearchTag)
admin.site.register(models.SearchTagOccurrenceType, SearchTagOccurrenceTypeAdmin)
admin.site.register(models.ExcelImport)
admin.site.register(models.ExcelReporting)
admin.site.register(models.PDFImport)
admin.site.register(models.CSVImport)
admin.site.register(models.ReportingExport)
