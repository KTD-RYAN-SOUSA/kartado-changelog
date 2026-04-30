from django.contrib import admin

from . import models


class FieldSurveySignatureInline(admin.TabularInline):
    model = models.FieldSurveySignature


class FieldSurveyAdmin(admin.ModelAdmin):
    inlines = [FieldSurveySignatureInline]

    class Meta:
        model = models.FieldSurvey


admin.site.register(models.Resource)
admin.site.register(models.Contract)
admin.site.register(models.ContractService)
admin.site.register(models.ContractItemUnitPrice)
admin.site.register(models.ContractItemAdministration)
admin.site.register(models.ContractItemPerformance)
admin.site.register(models.FieldSurveyRoad)
admin.site.register(models.FieldSurvey, FieldSurveyAdmin)
