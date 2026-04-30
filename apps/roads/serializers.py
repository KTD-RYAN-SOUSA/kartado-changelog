from django.db.models import Prefetch
from rest_framework_json_api import serializers

from apps.companies.models import Company
from helpers.mixins import EagerLoadingMixin

from .models import Road


class RoadSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        Prefetch("company", queryset=Company.objects.all().only("uuid"))
    ]

    class Meta:
        model = Road
        fields = [
            "name",
            "description",
            "direction",
            "uf",
            "company",
            "marks",
            "path",
            "length",
            "metadata",
            "lot_logic",
            "city_logic",
            "lane_type_logic",
            "manual_road",
            "all_marks_have_indexes",
        ]
        read_only_fields = ["path", "length"]


class RoadListSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        Prefetch("company", queryset=Company.objects.all().only("uuid"))
    ]

    class Meta:
        model = Road
        fields = [
            "name",
            "description",
            "direction",
            "uf",
            "company",
            "marks",
            "length",
            "metadata",
            "lot_logic",
            "city_logic",
            "lane_type_logic",
            "manual_road",
            "all_marks_have_indexes",
        ]
        read_only_fields = ["length"]
