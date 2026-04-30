from django.contrib import admin
from django.db.models import Prefetch

from apps.companies.models import Company, Firm
from apps.users.models import User

from . import models
from .forms import ApprovalFlowForm


class ApprovalFlowAdmin(admin.ModelAdmin):
    def company_name(self, obj):
        return obj.company.name

    list_display = ("company_name", "target_model", "name")
    autocomplete_fields = ("company",)
    ordering = ("company__name",)
    search_fields = ["company__name", "name"]
    list_filter = ("company__name",)
    form = ApprovalFlowForm

    def get_queryset(self, request):

        qs = super().get_queryset(request)
        return qs.prefetch_related(
            Prefetch("company", queryset=Company.objects.all().only("name", "uuid")),
        )


class ApprovalStepAdmin(admin.ModelAdmin):
    model = models.ApprovalStep

    def target_model(self, obj):
        return obj.approval_flow.target_model

    def company_name(self, obj):
        return obj.approval_flow.company.name

    list_display = ("company_name", "target_model", "name")
    autocomplete_fields = ("approval_flow", "responsible_firms", "responsible_users")
    ordering = ("approval_flow__company__name",)
    search_fields = ["approval_flow__company__name", "name"]
    list_filter = ("approval_flow__company__name",)

    def get_queryset(self, request):
        ApprovalFlow = models.ApprovalFlow

        qs = super().get_queryset(request)
        return qs.prefetch_related(
            Prefetch("responsible_users", queryset=User.objects.all()),
            Prefetch("responsible_firms", queryset=Firm.objects.all()),
            Prefetch("approval_flow", queryset=ApprovalFlow.objects.all()),
            Prefetch(
                "approval_flow__company", queryset=Company.objects.all().only("name")
            ),
        )


class ApprovalTransitionAdmin(admin.ModelAdmin):
    model = models.ApprovalTransition

    def company_name(self, obj):
        return obj.origin.approval_flow.company.name

    def target_model(self, obj):
        return obj.origin.approval_flow.target_model

    list_display = ("company_name", "target_model", "name")
    search_fields = ["origin__approval_flow__company__name", "name"]
    list_filter = ("origin__approval_flow__company__name",)
    autocomplete_fields = (
        "origin",
        "destination",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "origin",
                    "destination",
                    "condition",
                    "callback",
                    "button",
                    "order",
                )
            },
        ),
    )

    def get_queryset(self, request):
        ApprovalStep = models.ApprovalStep
        qs = super().get_queryset(request)
        return qs.prefetch_related(
            Prefetch("origin", queryset=ApprovalStep.objects.all()),
            Prefetch("destination", queryset=ApprovalStep.objects.all()),
            Prefetch(
                "origin__approval_flow__company",
                queryset=Company.objects.all().only("name"),
            ),
        )


admin.site.register(models.ApprovalFlow, ApprovalFlowAdmin)
admin.site.register(models.ApprovalStep, ApprovalStepAdmin)
admin.site.register(models.ApprovalTransition, ApprovalTransitionAdmin)
