from django_filters import FilterSet
from django_filters.filters import BooleanFilter

from helpers.filters import UUIDListFilter

from .models import MLPrediction


class MLPredictionFilter(FilterSet):
    company = UUIDListFilter()
    multiple_daily_report = UUIDListFilter()
    feedback = BooleanFilter()

    class Meta:
        model = MLPrediction
        fields = ["company", "multiple_daily_report", "feedback"]
