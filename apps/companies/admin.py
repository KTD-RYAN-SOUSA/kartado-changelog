from django.contrib import admin, messages
from django.db.models import Prefetch
from django.shortcuts import redirect
from django.urls import path, reverse

from apps.companies.create_instances_company_model import create_instances_company_model
from apps.companies.models import Company

from . import models
from .forms import CompanyForm, UserInCompanyForm


class FirmAdmin(admin.ModelAdmin):
    search_fields = ["name", "company__name"]


class CompanyAdmin(admin.ModelAdmin):
    search_fields = ["name", "company_group__name"]
    autocomplete_fields = ("company_group", "owner", "key_users")
    form = CompanyForm


class UserIncompanyAdmin(admin.ModelAdmin):
    def custom_titled_filter(title):
        class Wrapper(admin.FieldListFilter):
            def __new__(cls, *args, **kwargs):
                instance = admin.FieldListFilter.create(*args, **kwargs)
                instance.title = title
                return instance

        return Wrapper

    model = models.UserInCompany

    def company_name(self, obj):
        return obj.company.name

    def user_username(self, obj):
        return obj.user.username

    def permission_name(self, obj):
        return obj.permissions.name if obj.permissions else ""

    list_display = ("company_name", "user_username", "permission_name")
    autocomplete_fields = ("user", "company", "permissions")
    ordering = ("company__name",)
    search_fields = ["company__name", "user__username"]
    list_filter = (
        ("company__name", custom_titled_filter("Company")),
        ("company__company_group__name", custom_titled_filter("Company Group")),
    )
    form = UserInCompanyForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related(
            Prefetch("company", queryset=Company.objects.all().only("uuid", "name"))
        )


class CompanyUsageAdmin(admin.ModelAdmin):
    model = models.CompanyUsage
    change_list_template = "companyusage_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "update-company-usage-and-user-usage/",
                self.admin_site.admin_view(self.update_company_usage_and_user_usage),
                name="update_company_usage_and_user_usage",
            ),
        ]
        return custom_urls + urls

    def update_company_usage_and_user_usage(self, request):
        """
        Update company usage and user usage
        """
        if request.user.is_staff and request.user.is_superuser:
            create_instances_company_model()
            messages.success(
                request,
                "Contagem de usuários e empresas está ocorrendo em background e levará alguns minutos para ser concluída.",
            )
        else:
            messages.error(request, "Error.")

        return redirect(reverse("admin:companies_companyusage_changelist"))


class CompanyGroupAdmin(admin.ModelAdmin):
    search_fields = ("name",)


admin.site.register(models.Company, CompanyAdmin)
admin.site.register(models.SubCompany)
admin.site.register(models.UserInCompany, UserIncompanyAdmin)
admin.site.register(models.Firm, FirmAdmin)
admin.site.register(models.UserInFirm)
admin.site.register(models.InspectorInFirm)
admin.site.register(models.CompanyGroup, CompanyGroupAdmin)
admin.site.register(models.AccessRequest)
admin.site.register(models.Entity)
admin.site.register(models.CompanyUsage, CompanyUsageAdmin)
admin.site.register(models.UserUsage)
