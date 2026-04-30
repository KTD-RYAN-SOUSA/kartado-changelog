from django.contrib.contenttypes.models import ContentType
from django.db.models import TextField, Value
from django.db.models.functions import Concat
from django_filters.filters import CharFilter
from django_filters.rest_framework import FilterSet

from helpers.filters import ListFilter, UUIDListFilter

from .models import IntegrationConfig, IntegrationRun


class IntegrationConfigFilter(FilterSet):
    uuid = UUIDListFilter()
    search = CharFilter(label="search", method="get_search")

    class Meta:
        model = IntegrationConfig
        fields = ["uuid", "name", "integration_type"]

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "name", Value(" "), "integration_type", output_field=TextField()
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )


class IntegrationRunFilter(FilterSet):
    uuid = UUIDListFilter()
    integration_config = UUIDListFilter()

    class Meta:
        model = IntegrationRun
        fields = ["uuid"]


class ContentTypeFilter(FilterSet):

    id = ListFilter()
    app_label = ListFilter()
    model = ListFilter()

    class Meta:
        model = ContentType
        fields = ["id", "app_label", "model"]
