from django.contrib import admin

from . import models


class ToDoAdmin(admin.ModelAdmin):
    list_filter = ("is_done",)


class ToDoActionAdmin(admin.ModelAdmin):
    list_filter = ("company_group",)


admin.site.register(models.ToDo, ToDoAdmin)
admin.site.register(models.ToDoAction, ToDoActionAdmin)
admin.site.register(models.ToDoActionStep)
