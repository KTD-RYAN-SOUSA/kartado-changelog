import uuid

from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from helpers.filters import ListFilter, UUIDListFilter
from helpers.permissions import PermissionManager, join_queryset

from .models import Road
from .permissions import RoadPermissions
from .serializers import RoadListSerializer, RoadSerializer


class RoadFilter(filters.FilterSet):
    id = ListFilter()
    uf = ListFilter()
    company = UUIDListFilter()

    class Meta:
        model = Road
        fields = {"name": ["exact", "contains"], "direction": ["exact"]}


class RoadViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, RoadPermissions]
    filterset_class = RoadFilter
    permissions = None
    ordering = "id"

    def get_serializer_class(self):
        if self.action == "list":
            return RoadListSerializer
        return RoadSerializer

    def get_queryset(self):
        queryset = None
        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return Road.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="Road",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, Road.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, Road.objects.filter(company__in=[user_company])
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = Road.objects.filter(company__in=user_companies)

        # Por padrão, ocultar roads clones (is_default_segment=True)
        # Só mostrar clones quando incluir_default_segments=true
        include_default_segments = (
            self.request.query_params.get("include_default_segments", "false").lower()
            == "true"
        )

        if not include_default_segments:
            queryset = queryset.exclude(is_default_segment=True)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())
