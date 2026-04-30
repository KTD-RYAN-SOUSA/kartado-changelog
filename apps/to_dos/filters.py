from django_filters import rest_framework as filters
from django_filters.filters import CharFilter, DateFilter

from apps.to_dos.models import ToDo, ToDoAction
from helpers.filters import DateFromToRangeCustomFilter, UUIDListFilter


class ToDoFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    only_company = UUIDListFilter(field_name="company")
    created_by = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    due_at = DateFilter(field_name="due_at__date")
    action = UUIDListFilter()
    description = CharFilter(lookup_expr="icontains")
    resource = UUIDListFilter(field_name="resource_obj_id")
    resource_type = UUIDListFilter()
    responsibles = UUIDListFilter()
    is_read = filters.BooleanFilter(method="get_is_read")

    def get_is_read(self, queryset, name, value):
        return queryset.filter(read_at__isnull=not value)

    class Meta:
        model = ToDo
        fields = [
            "uuid",
            "only_company",
            "created_by",
            "created_at",
            "due_at",
            "action",
            "description",
            "resource",
            "resource_type",
            "is_done",
            "responsibles",
        ]


class ToDoActionFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company_group = UUIDListFilter()

    class Meta:
        model = ToDoAction
        fields = ["uuid", "company_group"]
