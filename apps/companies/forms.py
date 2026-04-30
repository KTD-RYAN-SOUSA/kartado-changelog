from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect, AutocompleteSelectMultiple

from .models import Company, UserInCompany


class UserInCompanyForm(forms.ModelForm):
    class Meta:
        fields = (
            "user",
            "company",
            "expiration_date",
            "level",
            "permissions",
            "added_permissions",
            "is_active",
        )
        widgets = {
            "user": AutocompleteSelect(
                UserInCompany.user.field,
                admin.site,
                attrs={"style": "width: 600px", "data-dropdown-auto-width": "true"},
            ),
            "company": AutocompleteSelect(
                UserInCompany.company.field,
                admin.site,
                attrs={"style": "width: 600px", "data-dropdown-auto-width": "true"},
            ),
            "permissions": AutocompleteSelect(
                UserInCompany.permissions.field,
                admin.site,
                attrs={"style": "width: 600px", "data-dropdown-auto-width": "true"},
            ),
        }


class CompanyForm(forms.ModelForm):
    class Meta:
        fields = (
            "name",
            "active",
            "owner",
            "cnpj",
            "logo",
            "provider_logo",
            "company_group",
            "street_address",
            "custom_options",
            "metadata",
            "shape",
            "key_users",
            "mobile_app_override",
        )
        widgets = {
            "owner": AutocompleteSelect(
                Company.owner.field,
                admin.site,
                attrs={"style": "width: 600px", "data-dropdown-auto-width": "true"},
            ),
            "company_group": AutocompleteSelect(
                Company.company_group.field,
                admin.site,
                attrs={"style": "width: 600px", "data-dropdown-auto-width": "true"},
            ),
            "key_users": AutocompleteSelectMultiple(
                Company.key_users.field,
                admin.site,
                attrs={"style": "width: 600px", "data-dropdown-auto-width": "true"},
            ),
        }
