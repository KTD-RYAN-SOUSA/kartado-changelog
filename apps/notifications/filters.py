from django_filters import rest_framework as filters
from django_filters.filters import ModelChoiceFilter

from apps.companies.models import Company
from apps.notifications.models import PushNotification
from helpers.filters import DateFromToRangeCustomFilter, UUIDListFilter


class PushNotificationFilter(filters.FilterSet):
    user = UUIDListFilter(field_name="users")
    created_at = DateFromToRangeCustomFilter()
    updated_at = DateFromToRangeCustomFilter()
    sent = filters.BooleanFilter()
    read = filters.BooleanFilter()
    only_company = ModelChoiceFilter(
        field_name="companies", queryset=Company.objects.all()
    )
    just_unread = filters.BooleanFilter(method="get_just_unread", label="just_unread")

    class Meta:
        model = PushNotification
        fields = ["id", "user"]

    def get_just_unread(self, queryset, name, value):
        if value is True:
            return queryset.filter(users=self.request.user, push_message__read=False)
        else:
            return queryset
