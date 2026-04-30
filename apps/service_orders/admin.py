from django.contrib import admin

from . import models

admin.site.register(models.ServiceOrderActionStatus)
admin.site.register(models.ServiceOrderActionStatusSpecs)
admin.site.register(models.ServiceOrder)
admin.site.register(models.ServiceOrderAction)
admin.site.register(models.Procedure)
admin.site.register(models.ProcedureFile)
admin.site.register(models.ProcedureResource)
admin.site.register(models.ServiceOrderResource)
admin.site.register(models.MeasurementBulletin)
admin.site.register(models.AdministrativeInformation)
admin.site.register(models.ServiceOrderWatcher)
admin.site.register(models.AdditionalControl)
admin.site.register(models.PendingProceduresExport)
