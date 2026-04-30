import uuid

from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset

from .filters import (
    ConstructionPlantFilter,
    QualityAssayFilter,
    QualityControlExportFilter,
    QualityProjectFilter,
    QualitySampleFilter,
)
from .models import (
    ConstructionPlant,
    QualityAssay,
    QualityControlExport,
    QualityProject,
    QualitySample,
)
from .permissions import (
    ConstructionPlantPermissions,
    QualityAssayPermissions,
    QualityControlExportPermissions,
    QualityProjectPermissions,
    QualitySamplePermissions,
)
from .serializers import (
    ConstructionPlantSerializer,
    QualityAssaySerializer,
    QualityControlExportSerializer,
    QualityProjectSerializer,
    QualitySampleSerializer,
)


class QualityProjectViewSet(ListCacheMixin, ModelViewSet):
    serializer_class = QualityProjectSerializer
    filterset_class = QualityProjectFilter
    permissions = None
    permission_classes = [IsAuthenticated, QualityProjectPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "project_number",
        "firm",
        "created_at",
        "registered_at",
        "expires_at",
        "occurrence_type",
        "form_data",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return QualityProject.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="QualityProject",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, QualityProject.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    QualityProject.objects.filter(firm__company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = QualityProject.objects.filter(firm__company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ConstructionPlantViewSet(ListCacheMixin, ModelViewSet):
    serializer_class = ConstructionPlantSerializer
    filterset_class = ConstructionPlantFilter
    permissions = None
    permission_classes = [IsAuthenticated, ConstructionPlantPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "name",
        "company",
        "created_at",
        "created_by",
        "uuid",
        "name",
        "company",
        "created_at",
        "created_by",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return ConstructionPlant.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ConstructionPlant",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ConstructionPlant.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ConstructionPlant.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ConstructionPlant.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class QualitySampleViewSet(ModelViewSet):
    serializer_class = QualitySampleSerializer
    filterset_class = QualitySampleFilter
    permissions = None
    permission_classes = [IsAuthenticated, QualitySamplePermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "company",
        "collected_at",
        "created_at",
        "created_by",
        "responsible",
        "quality_project",
        "construction_firm",
        "construction_plant",
        "occurrence_type",
        "reportings",
        "form_data",
        "number",
        "received_at",
        "is_proof",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return QualitySample.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="QualitySample",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, QualitySample.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    QualitySample.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = QualitySample.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        # Always inject created_by
        kwargs = {"created_by": self.request.user}

        # If no responsible is provided, use current user
        if "responsible" not in serializer.validated_data:
            kwargs["responsible"] = self.request.user

        serializer.save(**kwargs)


class QualityAssayViewSet(ModelViewSet):
    serializer_class = QualityAssaySerializer
    filterset_class = QualityAssayFilter
    permissions = None
    permission_classes = [IsAuthenticated, QualityAssayPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "number",
        "company",
        "created_at",
        "executed_at",
        "created_by",
        "responsible",
        "quality_project",
        "occurrence_type",
        "related_assays",
        "quality_sample",
        "reportings",
        "form_data",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return QualityAssay.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="QualityAssay",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, QualityAssay.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    QualityAssay.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = QualityAssay.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        # Always inject created_by
        kwargs = {"created_by": self.request.user}

        # If no responsible is provided, use current user
        if "responsible" not in serializer.validated_data:
            kwargs["responsible"] = self.request.user

        serializer.save(**kwargs)


class QualityControlExportViewSet(ModelViewSet):
    serializer_class = QualityControlExportSerializer
    filterset_class = QualityControlExportFilter
    permissions = None
    permission_classes = [IsAuthenticated, QualityControlExportPermissions]

    ordering = "uuid"
    ordering_fields = ["uuid", "reporting", "created_at", "created_by"]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return QualityControlExport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="QualityControlExport",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, QualityControlExport.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    QualityControlExport.objects.filter(
                        reporting__firm__company=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = QualityControlExport.objects.filter(
                reporting__firm__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        # Inject created_by
        kwargs = {"created_by": self.request.user}

        serializer.save(**kwargs)
