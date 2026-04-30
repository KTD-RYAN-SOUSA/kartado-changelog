from django.contrib import admin

from . import models


class MonitoringPlanAdmin(admin.ModelAdmin):
    search_fields = ["number", "company__name", "specificity", "description"]


admin.site.register(models.MonitoringPlan, MonitoringPlanAdmin)
admin.site.register(models.MonitoringPoint)
admin.site.register(models.MonitoringCycle)
admin.site.register(models.MonitoringFrequency)
admin.site.register(models.MonitoringCampaign)
admin.site.register(models.MonitoringRecord)
admin.site.register(models.MonitoringCollect)
admin.site.register(models.OperationalControl)
admin.site.register(models.OperationalCycle)
admin.site.register(models.MaterialItem)
admin.site.register(models.MaterialUsage)
