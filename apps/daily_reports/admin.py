from django.contrib import admin

from . import models

admin.site.register(models.DailyReport)
admin.site.register(models.MultipleDailyReport)
admin.site.register(models.DailyReportWorker)
admin.site.register(models.DailyReportRelation)
admin.site.register(models.DailyReportExternalTeam)
admin.site.register(models.DailyReportEquipment)
admin.site.register(models.DailyReportVehicle)
admin.site.register(models.DailyReportSignaling)
admin.site.register(models.DailyReportOccurrence)
admin.site.register(models.DailyReportResource)
admin.site.register(models.ProductionGoal)
admin.site.register(models.DailyReportExport)
admin.site.register(models.DailyReportContractUsage)
admin.site.register(models.MultipleDailyReportFile)
admin.site.register(models.MultipleDailyReportSignature)
