from rest_framework import serializers
from rest_framework_json_api.relations import ResourceRelatedField

from apps.reportings.models import Reporting
from helpers.files import get_url
from helpers.mixins import EagerLoadingMixin
from RoadLabsAPI.storage_backends import PrivateMediaStorage

from .models import BIMModel


class BIMModelSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    """Serializer para o modelo BIMModel."""

    _PREFETCH_RELATED_FIELDS = ["company", "created_by", "inventory"]

    uuid = serializers.UUIDField(read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BIMModel
        fields = [
            "uuid",
            "company",
            "created_by",
            "created_at",
            "updated_at",
            "inventory",
            "name",
            "file",
            "file_size",
            "status",
            "error_message",
            "file_url",
        ]
        read_only_fields = [
            "uuid",
            "created_at",
            "updated_at",
            "status",
            "error_message",
            "file_url",
        ]

    def get_file_url(self, obj):
        """Retorna presigned URL se status=done."""
        if obj.status == BIMModel.STATUS_DONE and obj.file:
            try:
                return obj.file.url
            except Exception:
                return None
        return None


class BIMModelStatusSerializer(serializers.ModelSerializer):
    """Serializer simplificado para endpoint de status."""

    uuid = serializers.UUIDField(read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BIMModel
        fields = [
            "uuid",
            "status",
            "error_message",
            "file_url",
        ]

    def get_file_url(self, obj):
        """Retorna presigned URL se status=done."""
        if obj.status == BIMModel.STATUS_DONE and obj.file:
            try:
                return obj.file.url
            except Exception:
                return None
        return None


class BIMModelCreateSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    """Serializer para criação de BIMModel com presigned URL."""

    _PREFETCH_RELATED_FIELDS = ["company", "created_by", "inventory"]

    uuid = serializers.UUIDField(read_only=True)
    ifc_file = serializers.JSONField(write_only=True, required=True)
    ifc_file_url = serializers.SerializerMethodField()
    inventory = ResourceRelatedField(
        queryset=Reporting.objects.all(),
        required=True,
    )

    class Meta:
        model = BIMModel
        fields = [
            "uuid",
            "name",
            "ifc_file",
            "ifc_file_url",
            "inventory",
            "status",
            "created_at",
        ]
        read_only_fields = ["uuid", "status", "created_at", "ifc_file_url"]

    def get_ifc_file_url(self, obj):
        """Gera presigned URL para upload direto ao S3."""
        if obj.file:
            return get_url(obj, "file")
        return {}

    def create(self, validated_data):
        request = self.context.get("request")

        # Extrair filename do ifc_file
        ifc_file_data = validated_data.pop("ifc_file", {})
        filename = ifc_file_data.get("filename", "modelo.ifc")

        # Gerar path para o arquivo
        storage = PrivateMediaStorage()
        file_path = f"bim/{filename}"
        available_name = storage.get_available_name(file_path)

        # Criar o modelo com file path (arquivo ainda não existe)
        bim_model = BIMModel.objects.create(
            company=validated_data["inventory"].company,
            created_by=request.user,
            inventory=validated_data["inventory"],
            name=filename,
            file=available_name,  # Path onde o arquivo será salvo
            status=BIMModel.STATUS_UPLOADING,
        )

        return bim_model


class BIMModelUploadSerializer(serializers.Serializer):
    """Serializer para upload de arquivos BIM."""

    file = serializers.FileField(required=True)
    inventory_id = serializers.UUIDField(required=True)
