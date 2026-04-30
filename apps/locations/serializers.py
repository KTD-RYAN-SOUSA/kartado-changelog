from rest_framework_json_api import serializers

from helpers.mixins import EagerLoadingMixin

from .models import City, Location, River


class CitySerializer(serializers.ModelSerializer, EagerLoadingMixin):
    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = City
        fields = ["uuid", "uf_code", "name", "coordinates"]


class LocationSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company", "city"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = Location
        fields = ["uuid", "company", "city", "name", "coordinates"]


class LocationSimpleSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = Location
        fields = ["uuid", "name", "coordinates"]


class RiverSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company"]
    _PREFETCH_RELATED_FIELDS = ["locations"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = River
        fields = ["uuid", "company", "name", "locations"]


class RiverSimpleSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = River
        fields = ["uuid", "name"]
