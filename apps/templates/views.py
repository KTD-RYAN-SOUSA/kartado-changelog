import json
import logging
import uuid

import requests
import sentry_sdk
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from django_filters import rest_framework as filters
from django_filters.filters import CharFilter, ChoiceFilter, DateTimeFromToRangeFilter
from fnc.mappings import get
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_json_api import serializers

from apps.companies.models import Company
from apps.monitorings.models import (
    MonitoringCycle,
    OperationalControl,
    OperationalCycle,
)
from apps.reportings.permissions import ReportingPermissions
from helpers.apps.inventory import return_inventory_fields
from helpers.files import check_endpoint
from helpers.filters import DateFromToRangeCustomFilter, ListFilter, UUIDListFilter
from helpers.import_csv.read_csv import (
    group_csv_json,
    parse_csv_json_to_objs,
    parse_csv_to_json,
)
from helpers.import_excel.read_excel import (
    parse_excel_to_json,
    parse_json_to_objs,
    upload_zip_import_images,
)
from helpers.import_pdf.read_pdf import parse_pdf_json_to_objs, parse_pdf_to_json
from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset

from .const import reporting_export_types
from .models import (
    ActionLog,
    AppVersion,
    CanvasCard,
    CanvasList,
    CSVImport,
    ExcelDnitReport,
    ExcelImport,
    ExcelReporting,
    ExportRequest,
    MobileSync,
    PDFImport,
    PhotoReport,
    ReportingExport,
    SearchTag,
    SearchTagOccurrenceType,
    Template,
)
from .permissions import (
    ActionLogPermissions,
    CanvasCardPermissions,
    CanvasListPermissions,
    CSVImportPermissions,
    ExcelImportPermissions,
    ExcelReportingPermissions,
    ExportRequestPermissions,
    MobileSyncPermissions,
    PDFImportPermissions,
    ReportingExportPermissions,
    SearchTagPermissions,
    TemplatePermissions,
)
from .serializers import (
    ActionLogSerializer,
    AppVersionSerializer,
    CanvasCardSerializer,
    CanvasListSerializer,
    CSVImportObjectSerializer,
    CSVImportSerializer,
    ExcelDnitReportSerializer,
    ExcelImportObjectSerializer,
    ExcelImportSerializer,
    ExcelReportingSerializer,
    ExportRequestSerializer,
    LogSerializer,
    MobileSyncSerializer,
    PDFImportObjectSerializer,
    PDFImportSerializer,
    PhotoReportSerializer,
    ReportingExportSerializer,
    SearchTagSerializer,
    TemplateSerializer,
)


class TemplateFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="companies")

    class Meta:
        model = Template
        fields = {"model_name", "item_name"}


class TemplateView(viewsets.ModelViewSet):
    serializer_class = TemplateSerializer
    permission_classes = [IsAuthenticated, TemplatePermissions]
    filterset_class = TemplateFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return Template.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="Template",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, Template.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    Template.objects.filter(companies__in=[user_company]),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    Template.objects.filter(companies__in=[user_company]),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = Template.objects.filter(companies__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class CanvasListFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    service_order = UUIDListFilter()
    company = CharFilter(field_name="service_order__company")

    class Meta:
        model = CanvasList
        fields = ["company", "service_order"]


class CanvasListView(viewsets.ModelViewSet):
    serializer_class = CanvasListSerializer
    permission_classes = [IsAuthenticated, CanvasListPermissions]
    filterset_class = CanvasListFilter
    permissions = None
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return CanvasList.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="CanvasList",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, CanvasList.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    CanvasList.objects.filter(service_order__company_id=user_company),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    CanvasList.objects.filter(service_order__company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = CanvasList.objects.filter(
                service_order__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class CanvasCardFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="canvas_list__service_order__company")
    service_order = UUIDListFilter(field_name="canvas_list__service_order")
    canvas_list = UUIDListFilter()

    class Meta:
        model = CanvasCard
        fields = ["company", "canvas_list", "service_order"]


class CanvasCardView(viewsets.ModelViewSet):
    serializer_class = CanvasCardSerializer
    permission_classes = [IsAuthenticated, CanvasCardPermissions]
    filterset_class = CanvasCardFilter
    permissions = None
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return CanvasCard.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="CanvasCard",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, CanvasCard.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    CanvasCard.objects.filter(
                        canvas_list__service_order__company_id=user_company
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    CanvasCard.objects.filter(
                        canvas_list__service_order__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = CanvasCard.objects.filter(
                canvas_list__service_order__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class LogView(mixins.CreateModelMixin, generics.GenericAPIView):
    """
    Just POST method allowed.
    """

    permission_classes = []
    serializer_class = LogSerializer

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)


class AppVersionFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    notification_title = CharFilter()
    notification_body = CharFilter()
    target_app = CharFilter()
    target_platform = CharFilter()
    start_date = DateFromToRangeCustomFilter()
    deadline = DateFromToRangeCustomFilter()
    version = CharFilter(label="version", method="get_version")

    class Meta:
        model = AppVersion
        fields = {}

    def get_version(self, queryset, name, value):
        queryset_with_version = queryset.filter(
            version__major__isnull=False,
            version__minor__isnull=False,
            version__patch__isnull=False,
        )
        versions = value.split("-")
        if len(versions) == 3:
            return queryset_with_version.filter(
                Q(version__major__gt=int(versions[0]))
                | (
                    Q(version__major=int(versions[0]))
                    & Q(version__minor__gt=int(versions[1]))
                )
                | (
                    Q(version__major=int(versions[0]))
                    & Q(version__minor=int(versions[1]))
                    & Q(version__patch__gt=int(versions[2]))
                )
            )
        return queryset


class AppVersionView(ListCacheMixin, viewsets.ReadOnlyModelViewSet):
    queryset = AppVersion.objects.all()
    serializer_class = AppVersionSerializer
    permission_classes = []
    filterset_class = AppVersionFilter
    permissions = None

    ordering_fields = ["uuid", "start_date", "deadline"]
    ordering = "uuid"


class ExportRequestFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    created_at = DateTimeFromToRangeFilter()
    done = filters.BooleanFilter()
    error = filters.BooleanFilter()

    class Meta:
        model = ExportRequest
        fields = ["company"]


class ExportRequestView(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [ExportRequestPermissions, IsAuthenticated]
    serializer_class = ExportRequestSerializer
    filterset_class = ExportRequestFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ExportRequest.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ExportRequest",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ExportRequest.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ExportRequest.objects.filter(
                        company_id=user_company, created_by=self.request.user
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ExportRequest.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ExportRequest.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class MobileSyncFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    created_at = DateTimeFromToRangeFilter()
    done = filters.BooleanFilter()

    class Meta:
        model = MobileSync
        fields = ["company"]


class MobileSyncView(ListCacheMixin, viewsets.ModelViewSet):
    permission_classes = [MobileSyncPermissions, IsAuthenticated]
    serializer_class = MobileSyncSerializer
    filterset_class = MobileSyncFilter
    permissions = None
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return MobileSync.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MobileSync",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, MobileSync.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MobileSync.objects.filter(
                        company_id=user_company, created_by=self.request.user
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, MobileSync.objects.filter(company_id=user_company)
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MobileSync.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ActionLogFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    only_company = UUIDListFilter(field_name="company")
    created_at = DateFromToRangeCustomFilter()
    user = UUIDListFilter()
    action = ListFilter()
    content_type = ListFilter()
    user_ip = CharFilter(lookup_expr="icontains")

    class Meta:
        model = ActionLog
        fields = {}


class ActionLogView(viewsets.ModelViewSet):
    serializer_class = ActionLogSerializer
    permission_classes = [ActionLogPermissions, IsAuthenticated]
    filterset_class = ActionLogFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        if "company" in self.request.query_params:
            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ActionLog",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ActionLog.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset, ActionLog.objects.filter(user=self.request.user)
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ActionLog.objects.filter(
                        Q(company_id=user_company)
                        | Q(company_group=self.request.user.company_group)
                    ),
                )

        # If queryset isn't set by any means above (update/partial_update without company param)
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ActionLog.objects.filter(
                Q(company__in=user_companies)
                | Q(company_group=self.request.user.company_group)
            ).distinct()

        return self.get_serializer_class().setup_eager_loading(queryset)


class SearchTagFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    child_tags = UUIDListFilter()
    parent_tags = UUIDListFilter()
    previous_tags = ListFilter(method="get_previous_tags")

    class Meta:
        model = SearchTag
        fields = ["name", "level", "kind"]

    def get_previous_tags(self, queryset, name, value):
        values = value.split(",")
        values_objs = SearchTag.objects.filter(uuid__in=values)
        highest_level = max(values_objs.values_list("level", flat=True).distinct())

        next_levels = (
            queryset.filter(level__gt=highest_level, parent_tags__in=values_objs)
            .annotate(num_parent_tags=Count("parent_tags"))
            .filter(num_parent_tags=len(values))
            .values_list("level", flat=True)
            .distinct()
        )
        if next_levels:
            return (
                queryset.filter(level=min(next_levels), parent_tags__in=values_objs)
                .annotate(num_parent_tags=Count("parent_tags"))
                .filter(num_parent_tags=len(values))
                .distinct()
            )
        return queryset.none()


class SearchTagView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = SearchTagSerializer
    permission_classes = [SearchTagPermissions, IsAuthenticated]
    filterset_class = SearchTagFilter
    permissions = None
    ordering = "uuid"

    def get_serializer_context(self):
        context = super(SearchTagView, self).get_serializer_context()
        previous_tags = self.request.query_params.get("previous_tags", "").split(",")
        previous_tags = [a for a in previous_tags if a]

        if self.action in ["list", "retrieve"]:
            context.update({"previous_tags": previous_tags})

        return context

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return SearchTag.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="SearchTag",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, SearchTag.objects.none())
            elif "all" in allowed_queryset:
                user_companies = self.request.user.companies.all()
                queryset = join_queryset(
                    queryset,
                    SearchTag.objects.filter(Q(company__in=user_companies)).distinct(),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = SearchTag.objects.filter(
                Q(company__in=user_companies)
            ).distinct()

        return self.get_serializer_class().setup_eager_loading(queryset)

    @action(methods=["get"], url_path="GetTree", detail=False)
    def get_search_tag_tree(self, request, pk=None):
        if "company" not in request.query_params.keys():
            raise serializers.ValidationError("É necessário especificar uma unidade.")

        try:
            company = Company.objects.get(pk=request.query_params.get("company"))
        except Exception:
            raise serializers.ValidationError("Unidade não encontrada.")

        first_level_tags = SearchTag.objects.filter(
            level=1, company=company
        ).prefetch_related(
            "parent_tags",
            "child_tags__parent_tags",
            "child_tags__child_tags__parent_tags",
            "child_tags__child_tags__child_tags__parent_tags",
            "child_tags__child_tags__child_tags__child_tags__parent_tags",
            "child_tags__child_tags__child_tags__child_tags__child_tags__parent_tags",
            "company",
        )

        # Determine if OperationalControl will be showed
        user_all_permissions = PermissionManager(
            user=self.request.user,
            company_ids=company.uuid,
            model="OccurrenceRecord",
        ).all_permissions
        can_create_operational = any(
            get("operational_control.can_create", user_all_permissions, default=[])
        )
        can_view_operational = any(
            get("operational_control.can_view", user_all_permissions, default=[])
        )
        now = timezone.now()
        creator_operational_current_cycle = OperationalCycle.objects.filter(
            operational_control__firm__company=company,
            start_date__date__lte=now.date(),
            end_date__date__gte=now.date(),
            creators__in=self.request.user.user_firms.all(),
        )
        operationals_responsible = OperationalControl.objects.filter(
            firm__company=company, responsible=self.request.user
        )

        if (
            not can_view_operational
            or not can_create_operational
            and not creator_operational_current_cycle.exists()
            and not operationals_responsible.exists()
        ):
            first_level_tags = first_level_tags.exclude(
                name__iexact="Controle Operacional"
            )

        # Determine if MonitoringPlan will be showed
        can_create_monitoring = any(
            get(
                "occurrence_record.can_create_monitoring",
                user_all_permissions,
                default=[],
            )
        )
        can_view_monitoring = any(
            get("monitoring_plan.can_view", user_all_permissions, default=[])
        )
        executer_monitoring_current_cycle = MonitoringCycle.objects.filter(
            monitoring_plan__company=company,
            start_date__date__lte=now.date(),
            end_date__date__gte=now.date(),
            executers__in=self.request.user.user_firms.all(),
        )

        if not can_view_monitoring or (
            not can_create_monitoring and not executer_monitoring_current_cycle.exists()
        ):
            first_level_tags = first_level_tags.exclude(name__iexact="Monitoramento")

        st_occurrence_type = SearchTagOccurrenceType.objects.filter(
            company=company
        ).prefetch_related("search_tags", "occurrence_type")

        def get_children(tag, parent_tags):
            all_child_tags = tag.child_tags.all()

            children_parent_tags = [tag, *parent_tags]

            if len(all_child_tags):
                next_level = min([a.level for a in all_child_tags])
                child_tags = [
                    a
                    for a in all_child_tags
                    if a.level == next_level
                    and set(children_parent_tags).issubset(set(a.parent_tags.all()))
                ]
            else:
                child_tags = []

            children = []
            for child_tag in child_tags:
                children.append(
                    {
                        "uuid": str(child_tag.uuid),
                        "name": child_tag.name,
                        "kind": child_tag.kind,
                        "redirect": child_tag.redirect,
                        "level": child_tag.level,
                        "description": child_tag.description,
                        "occurrence_type": get_occurrence_type(
                            child_tag, children_parent_tags
                        ),
                        "children": get_children(child_tag, children_parent_tags),
                    }
                )

            return children

        def get_occurrence_type(tag, parent_tags):
            def check_match(candidate, tags):
                for tag in candidate.search_tags.all():
                    if tag not in tags:
                        return False
                return True

            try:
                occurrence_type = next(
                    a for a in st_occurrence_type if check_match(a, [tag, *parent_tags])
                )

                return occurrence_type.occurrence_type.uuid if occurrence_type else None
            except StopIteration:
                return None

        tags = []
        for tag in first_level_tags:
            tags.append(
                {
                    "uuid": str(tag.uuid),
                    "name": tag.name,
                    "kind": tag.kind,
                    "redirect": tag.redirect,
                    "level": tag.level,
                    "description": tag.description,
                    "occurrence_type": get_occurrence_type(tag, []),
                    "children": get_children(tag, []),
                }
            )

        return Response({"tags": tags})


class ExcelImportFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    created_by = UUIDListFilter()

    class Meta:
        model = ExcelImport
        fields = {"company", "created_by"}


class ExcelImportView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ExcelImportPermissions]
    filterset_class = ExcelImportFilter
    permissions = None
    ordering = "uuid"

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update", "create"]:
            return ExcelImportObjectSerializer
        return ExcelImportSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ExcelImport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ExcelImport",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ExcelImport.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ExcelImport.objects.filter(
                        company__in=[user_company], created_by=self.request.user
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ExcelImport.objects.filter(company__in=[user_company]),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ExcelImport.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="UploadZipImages", detail=True)
    def upload_zip_images(self, request, pk=None):
        excel_import = self.get_object()
        uuid = str(excel_import.pk)

        excel_import.uploading_zip_images = True
        excel_import.save()

        upload_zip_import_images(uuid)
        return Response({"data": {"status": "OK"}})

    @action(methods=["get"], url_path="GeneratePreview", detail=True)
    def generate_preview(self, request, pk=None):
        excel_import = self.get_object()
        if "inventory_code" in request.query_params:
            inventory_code = request.query_params.get("inventory_code")
            company = Company.objects.get(pk=request.query_params.get("company"))
            possible_codes = return_inventory_fields(company)
            if inventory_code not in [a["id"] for a in possible_codes]:
                raise serializers.ValidationError(
                    "kartado.error.excel_import.generate_preview.invalid_inventory_code"
                )
        else:
            inventory_code = None
        excel_import.generating_preview = True
        excel_import.save()
        parse_excel_to_json(
            str(excel_import.pk), str(self.request.user.pk), inventory_code
        )
        return Response({"data": {"status": "OK"}})

    @action(methods=["get"], url_path="Execute", detail=True)
    def execute(self, request, pk=None):
        excel_import = self.get_object()

        if excel_import.error:
            return Response(
                data={
                    "errors": [
                        {
                            "detail": "Excel contém erros.",
                            "source": {"pointer": "/data"},
                            "status": status.HTTP_400_BAD_REQUEST,
                        }
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        parse_json_to_objs(str(excel_import.pk))

        return Response({"data": {"status": "OK"}})

    @action(methods=["get"], url_path="Check", detail=True)
    def check(self, request, pk=None):
        return check_endpoint(self.get_object(), "excel_file")


class ExcelReportingFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter(field_name="excel_import__company")
    created_by = UUIDListFilter(field_name="excel_import__created_by")
    reporting = UUIDListFilter()

    class Meta:
        model = ExcelReporting
        fields = {"reporting"}


class ExcelReportingView(viewsets.ModelViewSet):
    serializer_class = ExcelReportingSerializer
    permission_classes = [IsAuthenticated, ExcelReportingPermissions]
    filterset_class = ExcelReportingFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ExcelReporting.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ExcelReporting",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ExcelReporting.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ExcelReporting.objects.filter(
                        excel_import__company__in=[user_company],
                        excel_import__created_by=self.request.user,
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ExcelReporting.objects.filter(
                        excel_import__company__in=[user_company]
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ExcelReporting.objects.filter(
                excel_import__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class PDFImportFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    created_by = UUIDListFilter()

    class Meta:
        model = PDFImport
        fields = {"company", "created_by"}


class PDFImportView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, PDFImportPermissions]
    filterset_class = PDFImportFilter
    permissions = None
    ordering = "uuid"

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update", "create"]:
            return PDFImportObjectSerializer
        return PDFImportSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return PDFImport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="PDFImport",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, PDFImport.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    PDFImport.objects.filter(
                        company__in=[user_company], created_by=self.request.user
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    PDFImport.objects.filter(company__in=[user_company]),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = PDFImport.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="GeneratePreview", detail=True)
    def generate_preview(self, request, pk=None):
        pdf_import = self.get_object()

        parse_pdf_to_json(str(pdf_import.pk), str(self.request.user.pk))

        return Response({"data": {"status": "OK"}})

    @action(methods=["post"], url_path="Execute", detail=True)
    def execute(self, request, pk=None):
        pdf_import = self.get_object()
        reportings_data = json.loads(request.body)
        if pdf_import.error:
            return Response(
                data={
                    "errors": [
                        {
                            "detail": "PDF contém erros.",
                            "source": {"pointer": "/data"},
                            "status": status.HTTP_400_BAD_REQUEST,
                        }
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        parse_pdf_json_to_objs(str(pdf_import.pk), reportings_data)

        return Response({"data": {"status": "OK"}})

    @action(methods=["get"], url_path="Check", detail=True)
    def check(self, request, pk=None):
        return check_endpoint(self.get_object(), "pdf_file")


class CSVImportFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    created_by = UUIDListFilter()

    class Meta:
        model = CSVImport
        fields = {"company", "created_by"}


class CSVImportView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, CSVImportPermissions]
    filterset_class = CSVImportFilter
    permissions = None
    ordering = "uuid"

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update", "create"]:
            return CSVImportObjectSerializer
        return CSVImportSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return CSVImport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="CSVImport",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, CSVImport.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    CSVImport.objects.filter(
                        company__in=[user_company], created_by=self.request.user
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    CSVImport.objects.filter(company__in=[user_company]),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = CSVImport.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="GeneratePreview", detail=True)
    def generate_preview(self, request, pk=None):
        csv_import = self.get_object()

        parse_csv_to_json(str(csv_import.pk), str(self.request.user.pk))

        return Response({"data": {"status": "OK"}})

    @action(methods=["post"], url_path="Group", detail=True)
    def group(self, request, pk=None):
        csv_import = self.get_object()
        input_data = json.loads(request.body)

        if csv_import.error:
            return Response(
                data={
                    "errors": [
                        {
                            "detail": "CSV contém erros.",
                            "source": {"pointer": "/data"},
                            "status": status.HTTP_400_BAD_REQUEST,
                        }
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        group_csv_json(str(csv_import.pk), input_data)

        return Response({"data": {"status": "OK"}})

    @action(methods=["post"], url_path="Execute", detail=True)
    def execute(self, request, pk=None):
        csv_import = self.get_object()
        input_data = json.loads(request.body)

        if csv_import.error or not input_data:
            return Response(
                data={
                    "errors": [
                        {
                            "detail": "CSVImport contém erros.",
                            "source": {"pointer": "/data"},
                            "status": status.HTTP_400_BAD_REQUEST,
                        }
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        parse_csv_json_to_objs(str(csv_import.pk), input_data)

        return Response({"data": {"status": "OK"}})

    @action(methods=["get"], url_path="Check", detail=True)
    def check(self, request, pk=None):
        return check_endpoint(self.get_object(), "csv_file")


class ReportingExportFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    created_by = UUIDListFilter()
    company = UUIDListFilter()
    export_type = ChoiceFilter(choices=reporting_export_types.REPORTING_EXPORT_TYPES)
    done = filters.BooleanFilter()
    error = filters.BooleanFilter()
    is_inventory = filters.BooleanFilter()

    class Meta:
        model = ReportingExport
        fields = [
            "uuid",
            "created_at",
            "created_by",
            "company",
            "export_type",
            "done",
            "error",
            "is_inventory",
        ]


class ExcelDnitReportFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    created_by = UUIDListFilter()
    company = UUIDListFilter()
    done = filters.BooleanFilter()
    error = filters.BooleanFilter()

    class Meta:
        model = ExcelDnitReport
        fields = [
            "uuid",
            "created_at",
            "created_by",
            "company",
            "done",
            "error",
        ]


class ReportingExportView(viewsets.ModelViewSet):
    serializer_class = ReportingExportSerializer
    permission_classes = [IsAuthenticated, ReportingExportPermissions]
    filterset_class = ReportingExportFilter
    permissions = None

    ordering_fields = ["uuid", "company__name", "created_at", "created_by__first_name"]

    ordering = "-created_at"

    def get_queryset(self):
        queryset = None
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ReportingExport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ReportingExport",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ReportingExport.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ReportingExport.objects.filter(
                        company_id=user_company, created_by=self.request.user
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ReportingExport.objects.filter(company_id=user_company),
                )
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ReportingExport.objects.filter(company_id__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ExcelDnitReportView(viewsets.ModelViewSet):
    serializer_class = ExcelDnitReportSerializer
    permission_classes = [IsAuthenticated, ReportingPermissions]
    filterset_class = ExcelDnitReportFilter
    permissions = None

    ordering_fields = ["uuid", "company__name", "created_at", "created_by__first_name"]

    ordering = "-created_at"

    def get_queryset(self):
        queryset = None
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ExcelDnitReport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="Reporting",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ExcelDnitReport.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ExcelDnitReport.objects.filter(
                        company_id=user_company, created_by=self.request.user
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ExcelDnitReport.objects.filter(company_id=user_company),
                )
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ExcelDnitReport.objects.filter(company_id__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class PhotoReportFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    created_by = UUIDListFilter()
    company = UUIDListFilter()
    export_type = ChoiceFilter(choices=PhotoReport.PHOTO_REPORT_TYPES)
    done = filters.BooleanFilter()
    error = filters.BooleanFilter()
    is_inventory = filters.BooleanFilter()

    class Meta:
        model = PhotoReport
        fields = [
            "uuid",
            "created_at",
            "created_by",
            "company",
            "export_type",
            "done",
            "error",
            "is_inventory",
        ]


class PhotoReportView(viewsets.ModelViewSet):
    serializer_class = PhotoReportSerializer
    permission_classes = [IsAuthenticated, ReportingPermissions]
    filterset_class = PhotoReportFilter
    permissions = None

    ordering_fields = ["uuid", "company__name", "created_at", "created_by__first_name"]

    ordering = "-created_at"

    def get_queryset(self):
        queryset = None
        if self.action == "list":
            if "company" not in self.request.query_params:
                return PhotoReport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="Reporting",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, PhotoReport.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    PhotoReport.objects.filter(
                        company_id=user_company, created_by=self.request.user
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    PhotoReport.objects.filter(company_id=user_company),
                )
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = PhotoReport.objects.filter(company_id__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def get_permissions(self):
        if self.action in ["update", "partial_update", "generate"]:
            return [IsAuthenticated()]
        return [IsAuthenticated(), ReportingPermissions()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(methods=["get"], url_path="Generate", detail=True)
    def generate(self, request, pk=None):
        instance = self.get_object()
        try:
            authorization = request.META.get("HTTP_AUTHORIZATION", "")
            url = f"{settings.KARTADO_REPORTS_URL}/{instance.export_type}"
            payload = {
                "id": str(instance.uuid),
                "authorization": authorization,
                "company": str(instance.company_id),
            }
            response = requests.post(
                url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            if response.status_code >= 300:
                raise Exception(
                    f"kartado-reports returned status {response.status_code}: {response.text}"
                )
        except Exception as e:
            logging.error(f"Error triggering photo report: {e}")
            sentry_sdk.capture_exception(e)
            instance.error = True
            instance.done = True
            instance.save()
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        return Response({"status": "accepted"}, status=status.HTTP_202_ACCEPTED)
