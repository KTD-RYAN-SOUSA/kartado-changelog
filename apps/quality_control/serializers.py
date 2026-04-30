from rest_framework_json_api import serializers
from rest_framework_json_api.relations import ResourceRelatedField

from apps.reportings.models import Reporting
from helpers.apps.quality_control import generate_exported_file
from helpers.mixins import EagerLoadingMixin, UUIDMixin

from .models import (
    ConstructionPlant,
    QualityAssay,
    QualityControlExport,
    QualityProject,
    QualitySample,
)


class QualityProjectSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["firm", "occurrence_type"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = QualityProject
        fields = [
            "uuid",
            "project_number",
            "firm",
            "created_at",
            "registered_at",
            "expires_at",
            "occurrence_type",
            "form_data",
        ]
        read_only_fields = ["created_at"]


class ConstructionPlantSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company", "created_by"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = ConstructionPlant
        fields = ["uuid", "name", "company", "created_at", "created_by"]
        read_only_fields = ["created_at", "created_by"]


class QualitySampleSerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _SELECT_RELATED_FIELDS = [
        "company",
        "created_by",
        "occurrence_type",
        "quality_project",
        "responsible",
        "construction_firm",
        "construction_plant",
    ]
    _PREFETCH_RELATED_FIELDS = ["reportings"]

    uuid = serializers.UUIDField(required=False)
    reportings = ResourceRelatedField(
        queryset=Reporting.objects, required=False, many=True
    )
    history = serializers.SerializerMethodField()

    class Meta:
        model = QualitySample
        fields = [
            "uuid",
            "company",
            "collected_at",
            "created_at",
            "created_by",
            "responsible",
            "quality_project",
            "construction_firm",
            "construction_plant",
            "occurrence_type",
            "reportings",
            "form_data",
            "number",
            "received_at",
            "is_proof",
            "history",
        ]
        read_only_fields = ["number", "created_at", "created_by"]
        extra_kwargs = {
            "quality_project": {"required": True},
            "construction_firm": {"required": True},
        }

    def get_history(self, obj):
        history_list = []
        for history in obj.history.all():
            history_dict = history.__dict__
            del history_dict["_state"]
            history_list.append(history_dict)
        return history_list


class QualityAssaySerializer(serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin):
    _SELECT_RELATED_FIELDS = [
        "company",
        "created_by",
        "responsible",
        "occurrence_type",
        "quality_sample",
        "quality_project",
        "csv_import",
    ]
    _PREFETCH_RELATED_FIELDS = ["related_assays", "reportings"]

    uuid = serializers.UUIDField(required=False)
    related_assays = ResourceRelatedField(
        queryset=QualityAssay.objects, required=False, many=True
    )
    reportings = ResourceRelatedField(
        queryset=Reporting.objects, required=False, many=True
    )

    class Meta:
        model = QualityAssay
        fields = [
            "uuid",
            "number",
            "company",
            "created_at",
            "executed_at",
            "created_by",
            "responsible",
            "quality_project",
            "occurrence_type",
            "related_assays",
            "quality_sample",
            "reportings",
            "form_data",
            "notes",
            "csv_import",
        ]
        read_only_fields = ["number", "created_at"]
        extra_kwargs = {"quality_project": {"required": True}}


class QualityControlExportSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["reporting", "created_by"]
    _PREFETCH_RELATED_FIELDS = [
        "reporting__reporting_quality_assays",
        "reporting__reporting_quality_assays__quality_sample",
    ]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = QualityControlExport
        fields = [
            "uuid",
            "reporting",
            "exported_file",
            "created_at",
            "created_by",
        ]
        read_only_fields = ["exported_file"]

    def create(self, validated_data):
        instance = super().create(validated_data)

        generate_exported_file(instance)

        return instance
