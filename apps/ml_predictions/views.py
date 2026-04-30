import uuid

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from helpers.permissions import PermissionManager, join_queryset

from .filters import MLPredictionFilter
from .models import MLPrediction
from .permissions import MLPredictionPermissions
from .serializers import MLPredictionSerializer


class MLPredictionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, MLPredictionPermissions]
    filterset_class = MLPredictionFilter
    permissions = None
    ordering = "-created_at"
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        queryset = None

        if self.action in ["list", "retrieve"]:
            if "company" not in self.request.query_params:
                return MLPrediction.objects.none()

            try:
                user_company = uuid.UUID(self.request.query_params["company"])
            except (ValueError, AttributeError):
                return MLPrediction.objects.none()

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MLPrediction",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if self.action == "list":
                if "none" in allowed_queryset:
                    queryset = join_queryset(queryset, MLPrediction.objects.none())
                if "all" in allowed_queryset:
                    queryset = join_queryset(
                        queryset,
                        MLPrediction.objects.filter(company_id=user_company),
                    )

        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MLPrediction.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def get_serializer_class(self):
        return MLPredictionSerializer
