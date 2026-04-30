from django.contrib import admin

from . import models

admin.site.register(models.IntegrationConfig)
admin.site.register(models.IntegrationRun)
