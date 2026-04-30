from django.contrib import admin

from . import models


class RecordMenuRelationInline(admin.TabularInline):
    model = models.RecordMenuRelation


class RecordMenuAdmin(admin.ModelAdmin):
    inlines = [RecordMenuRelationInline]

    class Meta:
        model = models.RecordMenu


class ReportingRelationAdmin(admin.ModelAdmin):
    model = models.ReportingRelation

    def company_name(self, obj):
        return obj.company.name

    list_display = ("name", "outward", "inward", "company_name")
    search_fields = ["company__name", "name"]
    list_filter = ("company__name",)


class ReportingAdmin(admin.ModelAdmin):
    search_fields = [
        "company__name",
        "number",
        "status",
        "created_at",
    ]
    autocomplete_fields = [
        "company",
        "occurrence_type",
        "firm",
    ]
    raw_id_fields = [
        "created_by",
        "occurrence_type",
        "status",
        "firm",
        "approval_step",
        "active_tile_layer",
        "active_shape_files",
        "job",
        "services",
        "parent",
        "active_inspection",
        "construction",
        "pdf_import",
        "self_relations",
    ]
    list_filter = ["company__name", "created_at"]


admin.site.register(models.Reporting, ReportingAdmin)
admin.site.register(models.ReportingFile)
admin.site.register(models.ReportingMessage)
admin.site.register(models.ReportingMessageReadReceipt)
admin.site.register(models.RecordMenu, RecordMenuAdmin)
admin.site.register(models.ReportingRelation, ReportingRelationAdmin)
admin.site.register(models.ReportingInReporting)
admin.site.register(models.ReportingInReportingAsyncBatch)
