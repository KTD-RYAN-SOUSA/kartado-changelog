from uuid import UUID

from django.db.models import Case, CharField, Value, When
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.email_handler.filters import QueuedJudiciaryEmailFilter
from apps.email_handler.models import QueuedEmail
from apps.email_handler.permissions import QueuedJudiciaryEmailPermissions
from apps.email_handler.serializers import QueuedJudiciaryEmailSerializer
from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset


class QueuedJudiciaryEmailView(ListCacheMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = QueuedJudiciaryEmailSerializer
    filterset_class = QueuedJudiciaryEmailFilter
    permissions = None
    permission_classes = [IsAuthenticated, QueuedJudiciaryEmailPermissions]
    ordering = "-created_at"
    ordering_fields = [
        "uuid",
        "sent_at",
        "issuer__first_name",
        "send_to_users__first_name",
        "opened_at",
        "status",
        "created_at",
    ]

    def get_queryset(self):
        queryset = None

        if "company" not in self.request.query_params:
            return QueuedEmail.objects.none()

        user_company = UUID(self.request.query_params["company"])

        if not self.permissions:
            self.permissions = PermissionManager(
                user=self.request.user,
                company_ids=user_company,
                model="QueuedEmail",
            )

        allowed_queryset = self.permissions.get_allowed_queryset()

        if "none" in allowed_queryset:
            queryset = join_queryset(queryset, QueuedEmail.objects.none())
        if "all" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                QueuedEmail.objects.filter(
                    company=user_company, file_download__isnull=False
                ),
            )

        queryset = queryset.annotate(
            status=Case(
                When(error=True, then=Value("error")),
                When(error=False, sent=True, then=Value("sent")),
                default=Value("processing"),
                output_field=CharField(),
            )
        )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())
