import uuid
from functools import reduce
from operator import __and__ as AND

from django.db.models import Q
from django_filters import rest_framework as filters
from django_filters.filters import CharFilter
from rest_framework import permissions, viewsets

from helpers.filters import ListFilter, UUIDListFilter
from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset

from .models import UserPermission
from .permissions import UserPermissionAccessPermissions
from .serializers import UserPermissionSerializer


class UserPermissionFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="companies")
    all_companies = ListFilter(method="get_all_companies")

    class Meta:
        model = UserPermission
        fields = ["companies", "name", "permission_memberships__user", "is_admin"]

    def get_all_companies(self, queryset, name, value):
        companies = value.split(",")
        conditions = [Q(companies=a) for a in companies]
        return queryset.filter(reduce(AND, conditions))


class PermissionView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = UserPermissionSerializer
    permission_classes = [permissions.IsAuthenticated, UserPermissionAccessPermissions]
    filterset_class = UserPermissionFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        user_companies_ids = self.request.user.companies.all().values_list(
            "uuid", flat=True
        )
        queryset = UserPermission.objects.none()

        try:
            user_company_id = [uuid.UUID(self.request.query_params["company"])]
        except Exception:
            user_company_id = []

        self.permissions = PermissionManager(
            user=self.request.user,
            company_ids=user_companies_ids,
            model="UserPermission",
        )
        allowed_queryset = self.permissions.get_allowed_queryset()

        if "all" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                UserPermission.objects.filter(companies__in=user_companies_ids),
            )
        else:
            queryset = join_queryset(
                queryset,
                UserPermission.objects.filter(
                    permission_memberships__user=self.request.user,
                    companies__in=user_company_id,
                ),
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())
