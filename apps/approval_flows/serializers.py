from rest_framework_json_api import serializers
from rest_framework_json_api.relations import (
    ResourceRelatedField,
    SerializerMethodResourceRelatedField,
)

from apps.approval_flows.models import ApprovalFlow, ApprovalStep, ApprovalTransition
from apps.companies.models import Company, Firm
from apps.users.models import User
from helpers.mixins import EagerLoadingMixin


class ApprovalFlowSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["approval_flow_steps", "company"]

    uuid = serializers.UUIDField(required=False)

    approval_flow_steps = ResourceRelatedField(read_only=True, many=True)

    class Meta:
        model = ApprovalFlow
        fields = [
            "uuid",
            "name",
            "target_model",
            "company",
            "approval_flow_steps",
        ]


class ApprovalStepSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "next_steps",
        "responsible_firms",
        "responsible_users",
        "approval_flow",
        "approval_flow__company",
    ]

    uuid = serializers.UUIDField(required=False)
    field_options = serializers.JSONField(required=False)
    responsible_firms = ResourceRelatedField(
        queryset=Firm.objects, read_only=False, many=True
    )
    responsible_users = ResourceRelatedField(
        queryset=User.objects, read_only=False, many=True
    )
    responsible_json_logic = serializers.JSONField(required=False)
    target_model = serializers.SerializerMethodField()
    company = SerializerMethodResourceRelatedField(
        model=Company, method_name="get_company", read_only=True
    )

    class Meta:
        model = ApprovalStep
        fields = [
            "uuid",
            "name",
            "approval_flow",
            "next_steps",
            "field_options",
            "responsible_firms",
            "responsible_users",
            "responsible_created_by",
            "responsible_supervisor",
            "responsible_firm_entity",
            "responsible_firm_manager",
            "auto_execute_transition",
            "responsible_json_logic",
            "color",
            "target_model",
            "company",
        ]

    def get_target_model(self, obj):
        return obj.approval_flow.target_model

    def get_company(self, obj):
        return obj.approval_flow.company


class ApprovalTransitionSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["origin", "destination"]

    uuid = serializers.UUIDField(required=False)
    condition = serializers.JSONField(required=False)
    callback = serializers.JSONField(required=False)

    class Meta:
        model = ApprovalTransition
        fields = [
            "uuid",
            "name",
            "origin",
            "destination",
            "condition",
            "callback",
            "button",
            "order",
        ]
