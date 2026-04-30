from django.contrib import admin

from . import models

admin.site.register(models.QualitySample)
admin.site.register(models.QualityAssay)
admin.site.register(models.QualityProject)
admin.site.register(models.ConstructionPlant)
admin.site.register(models.QualityControlExport)
