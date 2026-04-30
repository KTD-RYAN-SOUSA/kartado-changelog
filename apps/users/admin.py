from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from . import models


class EnhancedUserAdmin(UserAdmin):
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Informações pessoais",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "email",
                    "cpf",
                    "birth_date",
                    "phone",
                    "avatar",
                )
            },
        ),
        (
            "Permissões",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Datas importantes", {"fields": ("last_login", "date_joined")}),
        (
            "Autenticacao Integrada",
            {"fields": ("saml_idp", "saml_nameid", "auth_error")},
        ),
        (
            "Extra",
            {
                "fields": (
                    "metadata",
                    "configuration",
                    "company_group",
                    "is_supervisor",
                    "is_internal",
                    "supervisor",
                    "responsible",
                    "firm_name",
                    "has_accepted_tos",
                )
            },
        ),
    )

    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
    )


admin.site.register(models.User, EnhancedUserAdmin)
admin.site.register(models.UserNotification)
