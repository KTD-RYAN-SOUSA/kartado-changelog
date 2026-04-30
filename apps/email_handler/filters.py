from django_filters import rest_framework as filters

from apps.email_handler.models import QueuedEmail
from helpers.filters import DateFromToRangeCustomFilter, ListFilter, UUIDListFilter


class QueuedJudiciaryEmailFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    issuer = UUIDListFilter()
    file_download = UUIDListFilter()
    send_to_users = UUIDListFilter()
    service_order = UUIDListFilter(field_name="file_download__service_order")
    status = ListFilter()
    sent_at = DateFromToRangeCustomFilter()
    opened_at = DateFromToRangeCustomFilter()

    class Meta:
        model = QueuedEmail
        fields = [
            "uuid",
            "company",
            "issuer",
            "file_download",
            "send_to_users",
            "service_order",
            "status",
            "sent_at",
            "opened_at",
        ]
