from django.contrib.contenttypes.models import ContentType
from rest_framework_json_api import serializers

from helpers.mixins import EagerLoadingMixin

from .models import IntegrationConfig, IntegrationRun


class IntegrationConfigSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "company",
        "instrument_occurrence_type",
        "reading_occurrence_type",
        "reading_operational_control",
        "reading_created_by",
        "default_status",
        "default_approval_step",
    ]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = IntegrationConfig
        fields = [
            "uuid",
            "name",
            "active",
            "company",
            "created_at",
            "last_run_at",
            "integration_type",
            "instrument_occurrence_type",
            "instrument_operational_position",
            "instrument_code_field",
            "instrument_code_prefix",
            "reading_occurrence_type",
            "field_map",
            "fields_to_copy",
            "frequency_type",
            "historiador_path",
            "reading_operational_control",
            "reading_created_by",
            "default_status",
            "default_approval_step",
        ]
        read_only_fields = ["created_at", "last_run_at"]


class IntegrationRunSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["integration_config"]

    uuid = serializers.UUIDField(required=False)
    created_count = serializers.SerializerMethodField(read_only=True)
    success = serializers.SerializerMethodField(read_only=True)

    def get_created_count(self, obj):
        return obj.records.count()

    def get_success(self, obj):
        return not obj.error

    class Meta:
        model = IntegrationRun
        fields = [
            "uuid",
            "integration_config",
            "started_at",
            "finished_at",
            "log",
            "error",
            "success",
            "created_count",
        ]
        read_only_fields = ["started_at", "finished_at", "log"]


class ContentTypeSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    """
    Serializer for Django's ContentType model.
    Provides app_label, model, and id fields.
    """

    class Meta:
        model = ContentType
        fields = ["id", "app_label", "model"]
        read_only_fields = fields
