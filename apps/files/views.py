import uuid
from datetime import datetime

from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.email_handler.models import QueuedEmail
from apps.files.filters import FileFilter
from apps.files.models import File, FileDownload
from apps.files.permissions import FilePermissions, OccurrenceRecordFilePermissions
from apps.files.serializers import FileObjectSerializer, FileSerializer
from apps.occurrence_records.models import OccurrenceRecord
from apps.users.models import User
from helpers.files import check_endpoint
from helpers.permissions import PermissionManager, join_queryset


class FileView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, FilePermissions]
    filterset_class = FileFilter
    permissions = None
    ordering = "uuid"

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update", "create"]:
            return FileObjectSerializer
        return FileSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return File.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="File",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, File.objects.none())
            if "self" in allowed_queryset:
                occurrence_records = OccurrenceRecord.objects.filter(
                    Q(company_id=user_company)
                    & (
                        Q(created_by=self.request.user)
                        | Q(responsible=self.request.user)
                        | Q(firm__in=self.request.user.user_firms.all())
                        | Q(service_order__actions__created_by=self.request.user)
                        | Q(
                            service_order__actions__procedures__created_by=self.request.user
                        )
                        | Q(
                            service_order__actions__procedures__responsible=self.request.user
                        )
                        | Q(service_order__responsibles=self.request.user)
                        | Q(service_order__managers=self.request.user)
                    )
                ).distinct()
                queryset = join_queryset(
                    queryset,
                    File.objects.filter(
                        Q(company_id=user_company)
                        | Q(record_file__in=occurrence_records)
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    File.objects.filter(company_id=user_company),
                )
            if "supervisor_agency" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    File.objects.filter(
                        company_id=user_company,
                        file_construction_progresses__construction__origin="AGENCY",
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = File.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="Check", detail=True)
    def check(self, request, pk=None):
        return check_endpoint(self.get_object())


class OccurrenceRecordFileView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, OccurrenceRecordFilePermissions]
    filterset_class = FileFilter
    permissions = None
    ordering = "uuid"

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update", "create"]:
            return FileObjectSerializer
        return FileSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return File.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="OccurrenceRecordFile",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, File.objects.none())
            if "self" in allowed_queryset:
                occurrence_records = OccurrenceRecord.objects.filter(
                    Q(company_id=user_company)
                    & (
                        Q(created_by=self.request.user)
                        | Q(responsible=self.request.user)
                        | Q(firm__in=self.request.user.user_firms.all())
                        | Q(service_orders__actions__created_by=self.request.user)
                        | Q(
                            service_orders__actions__procedures__created_by=self.request.user
                        )
                        | Q(
                            service_orders__actions__procedures__responsible=self.request.user
                        )
                        | Q(service_orders__responsibles=self.request.user)
                        | Q(service_orders__managers=self.request.user)
                    )
                ).distinct()
                queryset = join_queryset(
                    queryset,
                    File.objects.filter(
                        Q(company_id=user_company)
                        | Q(record_file__in=occurrence_records)
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    File.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = File.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="Check", detail=True)
    def check(self, request, pk=None):
        return check_endpoint(self.get_object())


class FileDownloadView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, file_download_pk, *args, **kwargs):
        obj = get_object_or_404(FileDownload, pk=file_download_pk)
        try:
            # Retrieve QueuedEmail
            # NOTE: Omit `qe` argument to download the file without marking it as opened
            try:
                qe_pk = request.GET.get("qe", None)
                email = QueuedEmail.objects.get(pk=qe_pk) if qe_pk else None
            except QueuedEmail.DoesNotExist:
                raise serializers.ValidationError(
                    "kartado.error.file_download.provided_queued_email_does_not_exist"
                )

            if obj.access_token:
                user_pk = request.GET.get("access_token", None)
                if request.user.is_authenticated:
                    if not obj.user_download.filter(pk=request.user.pk).exists():
                        obj.user_download.add(request.user)
                elif user_pk is not None:
                    user = User.objects.filter(pk=user_pk).first()
                    if user:
                        obj.user_download.add(user)
                else:
                    raise serializers.ValidationError(
                        "kartado.error.file_download.access_token_not_found"
                    )

            # If there's an associated email, mark the file as opened
            # NOTE: Positioned at the end to match response return time as close as possible
            if email:
                email.opened_at = datetime.now()
                email.save()

            return redirect(obj.file.url)

        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
