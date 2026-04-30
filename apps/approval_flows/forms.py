from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect

from .models import ApprovalFlow


class ApprovalFlowForm(forms.ModelForm):
    class Meta:
        fields = (
            "name",
            "target_model",
            "company",
        )
        widgets = {
            "company": AutocompleteSelect(
                ApprovalFlow.company.field,
                admin.site,
                attrs={"style": "width: 600px", "data-dropdown-auto-width": "true"},
            ),
        }
