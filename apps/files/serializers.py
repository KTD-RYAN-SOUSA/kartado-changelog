from django.contrib.contenttypes.models import ContentType
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import ResourceRelatedField

from apps.files.models import File
from helpers.fields import EmptyFileField
from helpers.files import get_url
from helpers.mixins import EagerLoadingMixin, UUIDMixin


class FileSerializer(serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin):
    _PREFETCH_RELATED_FIELDS = ["content_object", "company", "created_by"]

    uuid = serializers.UUIDField(required=False)
    upload = EmptyFileField(required=False)
    upload_url = serializers.SerializerMethodField()
    content_object = ResourceRelatedField(read_only=True)

    class Meta:
        model = File
        fields = [
            "uuid",
            "company",
            "description",
            "kind",
            "upload",
            "upload_url",
            "uploaded_at",
            "datetime",
            "created_by",
            "content_object",
            "object_id",
            "content_type",
            "md5",
            "url",
        ]

    def get_upload_url(self, obj):
        return {}
        # kept this field here to maintain compatibility

    def validate(self, data):

        if "content_object" in self.initial_data:
            content_type = self.initial_data["content_object"]["type"].lower()
            object_id = self.initial_data["content_object"]["id"]
        else:
            raise serializers.ValidationError("Relação genérica não enviada.")

        try:
            obj = ContentType.objects.filter(model=content_type).first()
        except Exception:
            raise serializers.ValidationError("Relação genérica não encontrada.")

        data["object_id"] = object_id
        data["content_type"] = obj

        return data


class FileObjectSerializer(FileSerializer):
    def get_upload_url(self, obj):
        return get_url(obj)
