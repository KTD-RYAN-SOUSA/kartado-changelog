from rest_framework_json_api import serializers

from helpers.mixins import EagerLoadingMixin

from .models import MLPrediction


class MLPredictionSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["company", "multiple_daily_report"]

    class Meta:
        model = MLPrediction
        fields = [
            "uuid",
            "company",
            "created_at",
            "multiple_daily_report",
            "output_data",
            "feedback",
            "feedback_notes",
        ]
        read_only_fields = [
            "uuid",
            "company",
            "created_at",
            "multiple_daily_report",
            "output_data",
        ]
