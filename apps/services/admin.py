from django.contrib import admin

from . import models

admin.site.register(models.Service)
admin.site.register(models.ServiceSpecs)
admin.site.register(models.ServiceUsage)
admin.site.register(models.Measurement)
admin.site.register(models.MeasurementService)
admin.site.register(models.Goal)
admin.site.register(models.GoalAggregate)
