from django_filters import rest_framework as filters

from helpers.filters import UUIDListFilter

from .models import BIMModel


class BIMModelFilter(filters.FilterSet):
    """Filtros para o modelo BIMModel."""

    uuid = UUIDListFilter()
    company = UUIDListFilter()
    inventory = UUIDListFilter()
    status = filters.ChoiceFilter(choices=BIMModel.STATUS_CHOICES)
    created_at = filters.DateTimeFromToRangeFilter()

    class Meta:
        model = BIMModel
        fields = ["uuid", "company", "inventory", "status", "created_at"]
