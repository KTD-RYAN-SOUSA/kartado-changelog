from django.db.models import Prefetch
from rest_framework_json_api import serializers

from apps.companies.models import Company
from helpers.fields import FeatureCollectionField
from helpers.mixins import EagerLoadingMixin

from .models import ShapeFile, TileLayer


class TileLayerSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        Prefetch("companies", queryset=Company.objects.all().only("uuid"))
    ]

    uuid = serializers.UUIDField(required=False)
    companies = serializers.ResourceRelatedField(queryset=Company.objects, many=True)

    class Meta:
        model = TileLayer
        fields = [
            "uuid",
            "type",
            "name",
            "description",
            "companies",
            "provider_info",
        ]


class ShapeFileSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    uuid = serializers.UUIDField(required=False)
    children = serializers.ResourceRelatedField(many=True, read_only=True)

    _SELECT_RELATED_FIELDS = ["created_by", "parent"]
    _PREFETCH_RELATED_FIELDS = [
        Prefetch("companies", queryset=Company.objects.all().only("uuid", "name")),
        "children",
    ]

    class Meta:
        model = ShapeFile
        fields = [
            "uuid",
            "created_by",
            "created_at",
            "updated_at",
            "synced_at",
            "name",
            "description",
            "companies",
            "private",
            "parent",
            "children",
            "metadata",
            "enable_default",
        ]


class ShapeFileObjectSerializer(ShapeFileSerializer):
    feature_collection = FeatureCollectionField(
        required=False,
        allow_null=True,
        geometry_field="geometry",
        properties_field="properties",
    )

    class Meta(ShapeFileSerializer.Meta):
        model = ShapeFileSerializer.Meta.model
        fields = ShapeFileSerializer.Meta.fields + ["feature_collection"]
