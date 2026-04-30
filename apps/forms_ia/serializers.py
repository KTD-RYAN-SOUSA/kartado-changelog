from rest_framework_json_api import serializers

from apps.occurrence_records.models import OccurrenceType
from helpers.mixins import EagerLoadingMixin

from .models import FormsIARequest


class FormsIARequestCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a Forms IA request
    """

    class Meta:
        model = FormsIARequest
        fields = ["company", "occurrence_kind", "name", "input_text", "uuid"]

    def create(self, validated_data):
        name = validated_data["name"]
        company = validated_data["company"]

        if OccurrenceType.objects.filter(name=name, company=company).exists():
            raise serializers.ValidationError(
                "Tipo de Classe com esse Nome e Unidade já existe"
            )

        request_obj = FormsIARequest.objects.create(**validated_data)
        return request_obj


class FormsIARequestSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    """
    Serializer for retrieving Forms IA request status
    """

    _PREFETCH_RELATED_FIELDS = ["company", "created_by"]

    class Meta:
        model = FormsIARequest
        fields = [
            "uuid",
            "company",
            "occurrence_kind",
            "name",
            "input_text",
            "request_id",
            "output_json",
            "done",
            "error",
            "error_message",
            "created_at",
            "created_by",
        ]
        read_only_fields = [
            "uuid",
            "request_id",
            "output_json",
            "done",
            "error",
            "error_message",
            "created_at",
            "created_by",
        ]
