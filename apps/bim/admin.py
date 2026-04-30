from django.contrib import admin

from .models import BIMModel


@admin.register(BIMModel)
class BIMModelAdmin(admin.ModelAdmin):
    list_display = ["uuid", "name", "inventory", "status", "created_at", "created_by"]
    list_filter = ["status", "created_at"]
    search_fields = ["name", "uuid"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
    raw_id_fields = ["inventory", "company", "created_by"]
