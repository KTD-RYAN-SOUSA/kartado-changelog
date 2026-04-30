import uuid

from django.contrib.contenttypes.models import ContentType
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset

from .filters import ContentTypeFilter, IntegrationConfigFilter, IntegrationRunFilter
from .models import IntegrationConfig, IntegrationRun
from .permissions import IntegrationConfigPermissions, IntegrationRunPermissions
from .serializers import (
    ContentTypeSerializer,
    IntegrationConfigSerializer,
    IntegrationRunSerializer,
)


class IntegrationConfigViewSet(ListCacheMixin, ModelViewSet):
    serializer_class = IntegrationConfigSerializer
    filterset_class = IntegrationConfigFilter
    permissions = None
    permission_classes = [IsAuthenticated, IntegrationConfigPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "name",
        "active",
        "company",
        "created_at",
        "last_run_at",
        "integration_type",
        "instrument_occurrence_type",
        "reading_occurrence_type",
        "field_map",
        "fields_to_copy",
        "frequency_type",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return IntegrationConfig.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="IntegrationConfig",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, IntegrationConfig.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    IntegrationConfig.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = IntegrationConfig.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class IntegrationRunViewSet(ListCacheMixin, ReadOnlyModelViewSet):
    serializer_class = IntegrationRunSerializer
    filterset_class = IntegrationRunFilter
    permissions = None
    permission_classes = [IsAuthenticated, IntegrationRunPermissions]

    ordering = "uuid"
    ordering_fields = ["uuid", "started_at", "finished_at"]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return IntegrationRun.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="IntegrationRun",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, IntegrationRun.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    IntegrationRun.objects.filter(
                        integration_config__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = IntegrationRun.objects.filter(
                integration_config__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ContentTypeViewSet(ListCacheMixin, ReadOnlyModelViewSet):
    """
    Read-only API endpoint for Django ContentTypes.
    Allows listing and retrieving content types.
    """

    serializer_class = ContentTypeSerializer
    filterset_class = ContentTypeFilter
    permission_classes = [IsAuthenticated]
    permissions = None
    ordering = "id"
    ordering_fields = ["id", "app_label", "model"]

    def get_queryset(self):
        queryset = ContentType.objects.exclude(model__istartswith="historical")

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())
