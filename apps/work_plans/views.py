import json
import uuid

import sentry_sdk
from django.contrib.postgres.aggregates import StringAgg
from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.db.models import Count, Func, Q, Sum, TextField, Value
from django.db.models.functions import Concat
from django_filters import rest_framework as filters
from django_filters.filters import CharFilter, NumberFilter
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_json_api import serializers

from apps.companies.models import Company, Firm, SubCompany
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import Reporting
from apps.templates.models import MobileSync
from apps.work_plans.const.async_batches import BATCH_SIZE
from helpers.apps.daily_reports import get_uuids_jobs_user_firms
from helpers.apps.job import get_sync_jobs_info_from_uuids
from helpers.error_messages import error_message
from helpers.filters import DateFromToRangeCustomFilter, ListFilter, UUIDListFilter
from helpers.permissions import PermissionManager, join_queryset
from helpers.strings import dict_to_casing, keys_to_camel_case

from .asynchronous import async_bulk_archive
from .models import Job, NoticeViewManager, UserNoticeView
from .permissions import (
    JobPermissions,
    NoticeViewManagerPermissions,
    UserNoticeViewPermissions,
)
from .serializers import (
    JobSerializer,
    JobWithReportingLimitSerializer,
    NoticeViewManagerSerializer,
    UserNoticeViewSerializer,
)


class JobFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    start_date = DateFromToRangeCustomFilter()
    end_date = DateFromToRangeCustomFilter()
    reporting_count__gte = NumberFilter(field_name="reporting_count", lookup_expr="gte")
    reporting_count__lte = NumberFilter(field_name="reporting_count", lookup_expr="lte")
    firm = UUIDListFilter()
    created_by = UUIDListFilter()
    worker = UUIDListFilter()
    inspection = UUIDListFilter()
    only_user_firms = filters.BooleanFilter(method="get_only_user_firms")
    search = CharFilter(label="search", method="get_search")
    lot = ListFilter(label="lot", method="get_lot")
    archived = filters.BooleanFilter()
    auto_scheduling = filters.BooleanFilter(method="get_auto_scheduling")
    processing_async_creation = filters.BooleanFilter()
    progress__gte = NumberFilter(field_name="progress", lookup_expr="gte")
    progress__lte = NumberFilter(field_name="progress", lookup_expr="lte")
    subcompany = UUIDListFilter(field_name="firm__subcompany")
    watcher_subcompanies = UUIDListFilter()
    occurrence_kind = ListFilter(
        field_name="reportings__occurrence_type__occurrence_kind"
    )
    occurrence_type = ListFilter(method="get_occurrence_type")
    notes = CharFilter(method="get_notes")

    class Meta:
        model = Job
        fields = ["company", "firm__subcompany__name"]

    def get_auto_scheduling(self, queryset, name, value):
        if value:
            return queryset.filter(
                Q(is_automatic=True) | Q(has_auto_allocated_reportings=True)
            )
        else:
            return queryset.filter(
                is_automatic=False,
                has_auto_allocated_reportings=False,
            )

    def get_only_user_firms(self, queryset, name, value):
        if value:
            return queryset.filter(firm__in=self.request.user.user_firms.all())
        else:
            return queryset.exclude(firm__in=self.request.user.user_firms.all())

    def get_lot(self, queryset, name, value):
        if not value:
            return queryset

        values = value.split(",")
        job_ids = (
            Reporting.objects.filter(lot__in=values, job__isnull=False)
            .only("job_id")
            .values_list("job_id", flat=True)
        )

        return queryset.filter(pk__in=job_ids).distinct()

    def get_notes(self, queryset, name, value):
        return (
            queryset.annotate(
                reportings_form_data_notes=Func(
                    KeyTextTransform("notes", "reportings__form_data"),
                    function="UNACCENT",
                    output_field=TextField(),
                )
            )
            .filter(
                reportings_form_data_notes__icontains=Func(
                    Value(value), function="UNACCENT"
                )
            )
            .distinct()
        )

    def get_occurrence_type(self, queryset, name, value):
        ids = value.split(",")
        occ = OccurrenceType.objects
        if self.request:
            company_id = uuid.UUID(self.request.query_params["company"])
            occ = occ.filter(company=company_id)
        else:
            occ = occ.filter(reporting_occurrence__job__in=queryset)
        occ_types = occ.values_list("uuid", "previous_version_id")
        list_ids = []

        def get_previous_id(obj_id, occ_types):
            for obj, pre_obj in occ_types:
                if str(obj) == obj_id and pre_obj:
                    return str(pre_obj)
            return None

        for obj_id in ids:
            while obj_id:
                list_ids.append(obj_id)
                obj_id = get_previous_id(obj_id, occ_types)

        return queryset.filter(reportings__occurrence_type_id__in=list_ids).distinct()

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "title",
                Value(" "),
                "description",
                Value(" "),
                "number",
                Value(" "),
                "worker__first_name",
                Value(" "),
                "worker__last_name",
                Value(" "),
                "firm__name",
                Value(" "),
                StringAgg("watcher_firms__name", " "),
                Value(" "),
                StringAgg("watcher_users__first_name", " "),
                Value(" "),
                StringAgg("watcher_users__last_name", " "),
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )


class JobViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, JobPermissions]
    filterset_class = JobFilter
    permissions = None

    ordering_fields = [
        "uuid",
        "number",
        "worker__first_name",
        "firm__name",
        "firm__subcompany__name",
        "title",
        "start_date",
        "end_date",
        "progress",
        "processing_async_creation",
    ]
    ordering = "uuid"

    def get_serializer_class(self):
        # If mobile usage, return the special limited serializer
        if "jobs_rdos_user_firms" in self.request.query_params:
            return JobWithReportingLimitSerializer
        else:
            return JobSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None
        request_user = self.request.user
        watcher_queryset = Job.objects.none()
        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return Job.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=request_user,
                    company_ids=user_company,
                    model="Job",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, Job.objects.none())
            if "self" in allowed_queryset:
                user_firms = list(
                    (request_user.user_firms.filter(company=user_company)).union(
                        request_user.user_firms_manager.filter(company=user_company)
                    )
                )
                queryset = join_queryset(
                    queryset,
                    Job.objects.filter(
                        Q(worker=request_user)
                        | Q(created_by=request_user)
                        | (Q(firm__in=user_firms) & Q(company_id=user_company))
                    ),
                )
            if "firm" in allowed_queryset:
                user_firms = list(
                    (request_user.user_firms.filter(company=user_company)).union(
                        request_user.user_firms_manager.filter(company=user_company)
                    )
                )
                queryset = join_queryset(
                    queryset,
                    Job.objects.filter(
                        Q(company_id=user_company)
                        & (
                            Q(worker=request_user)
                            | Q(created_by=request_user)
                            | Q(firm__in=user_firms)
                        )
                    ),
                )
            if "subcompany" in allowed_queryset:
                subcompany_user_firms = list(
                    (request_user.user_firms.filter(company=user_company)).union(
                        request_user.user_firms_manager.filter(company=user_company)
                    )
                )
                user_subcompanies = SubCompany.objects.filter(
                    subcompany_firms__in=subcompany_user_firms
                ).distinct()
                all_subcompany_firms = Firm.objects.filter(
                    subcompany__in=user_subcompanies
                ).distinct()
                queryset = join_queryset(
                    queryset,
                    Job.objects.filter(
                        company_id=user_company,
                        firm__in=all_subcompany_firms,
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, Job.objects.filter(company_id=user_company)
                )

            # Watcher queryset
            if set(allowed_queryset).issubset(["firm", "self", "subcompany"]):
                watcher_queryset = Job.objects.filter(
                    Q(watcher_users=request_user)
                    | Q(watcher_firms__in=request_user.user_firms.all())
                    | Q(
                        watcher_subcompanies__subcompany_firms__in=request_user.user_firms.all()
                    )
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = request_user.companies.all()
            queryset = Job.objects.filter(company__in=user_companies)

        queryset = join_queryset(queryset, watcher_queryset)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["POST"], url_path="BulkArchive", detail=False)
    def bulk_archive(self, request):
        # Parse input
        input_data = json.loads(request.body)
        if "data" in input_data:
            input_data = input_data["data"]
        else:
            raise serializers.ValidationError(
                "kartado.error.job.data_key_not_found_on_body"
            )
        input_data = keys_to_camel_case(input_data)

        try:
            company_id = str(Company.objects.get(pk=request.query_params["company"]).pk)
        except KeyError:
            raise serializers.ValidationError(
                "kartado.error.job.company_parameter_is_required"
            )
        user_id = str(request.user.pk)

        async_bulk_archive(input_data, company_id, user_id)

        response = {"data": {"result": "OK"}}
        return Response(response)

    @action(methods=["GET"], url_path="CheckAsyncCreation", detail=True)
    def check_async_creation(self, request, pk=None):
        """
        Check if a Job is done processing the async creation or not

        We'll consider the async creation as processing both
        when creating batches and when there are still batches to
        be processed
        """

        job: Job = self.get_object()
        pending_inventory_batches = job.job_async_batches.count()
        pending_reporting_in_reporting_batches = job.rep_in_rep_async_batches.count()

        processing_async_creation = (
            job.creating_batches
            or pending_inventory_batches > 0
            or pending_reporting_in_reporting_batches > 0
        )

        response_data = {
            "type": "JobCheck",
            "attributes": {
                "uuid": job.pk,
                "batch_size": BATCH_SIZE,
                "processing_async_creation": processing_async_creation,
                # Inventory batches
                "total_inventory_batches": (
                    job.total_inventory_batches if processing_async_creation else 0
                ),
                "pending_inventory_batches": pending_inventory_batches,
                # ReportingInReporting batches
                "total_reporting_in_reporting_batches": (
                    job.total_reporting_in_reporting_batches
                    if processing_async_creation
                    else 0
                ),
                "pending_reporting_in_reporting_batches": pending_reporting_in_reporting_batches,
            },
        }

        return Response(dict_to_casing(response_data))

    @action(methods=["GET"], url_path="SyncInfo", detail=False)
    def sync_info(self, request):
        queryset = self.filter_queryset(self.get_queryset())

        jobs_section = None
        if request.query_params.get("jobs_rdos_user_firms"):
            jobs_section, _ = request.query_params["jobs_rdos_user_firms"].split("|")

        if not jobs_section:
            return Response({})
        company_jobs = queryset.prefetch_related("company")

        first_job = company_jobs.first()

        if not first_job:
            return Response({})
        counts = queryset.aggregate(
            total=Count("uuid"), reportings_total=Sum("reporting_count")
        )
        automatic_sync_uuids = get_uuids_jobs_user_firms(
            jobs_section,
            first_job.company,
            request.user,
            use_reporting_limit=False,
        )

        force_sync_jobs_ids_param = request.query_params.get("force_sync_jobs_ids", "")
        automatic_sync_count = get_sync_jobs_info_from_uuids(
            automatic_sync_uuids, company_jobs
        )
        force_sync_count = (
            get_sync_jobs_info_from_uuids(
                force_sync_jobs_ids_param.split(","), company_jobs
            )
            if force_sync_jobs_ids_param
            else dict()
        )

        result = {
            "jobs_total": counts.get("total", 0),
            "reportings_total": counts.get("reportings_total", 0),
            "automatic_sync_jobs_total": automatic_sync_count.get("total", 0),
            "automatic_sync_reportings_total": automatic_sync_count.get(
                "reportings_total", 0
            ),
            "automatic_sync_reportings_files_total": automatic_sync_count.get(
                "reportings_files_total", 0
            ),
            "force_sync_jobs_total": force_sync_count.get("total", 0),
            "force_sync_reportings_total": force_sync_count.get("reportings_total", 0),
            "force_sync_reportings_files_total": force_sync_count.get(
                "reportings_files_total", 0
            ),
        }

        mobile_sync_id = request.query_params.get("mobile_sync_id")

        if mobile_sync_id:
            try:
                MobileSync.objects.filter(pk=mobile_sync_id).update(
                    sync_get_data=result
                )
            except Exception as e:
                sentry_sdk.capture_exception(e)
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        return Response(result)


class NoticeViewManagerFilter(filters.FilterSet):
    uuid = ListFilter()
    notice = CharFilter(lookup_expr="exact")

    class Meta:
        model = NoticeViewManager
        fields = ["uuid", "notice"]


class NoticeViewManagerViewSet(viewsets.ModelViewSet):
    serializer_class = NoticeViewManagerSerializer
    permission_classes = [IsAuthenticated, NoticeViewManagerPermissions]
    filterset_class = NoticeViewManagerFilter
    permissions = None
    http_method_names = ["get", "head", "options"]  # Remove POST method

    ordering_fields = ["uuid", "notice"]
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        if self.action == "list":
            if "company" not in self.request.query_params:
                return NoticeViewManager.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="NoticeViewManager",
                )
            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, NoticeViewManager.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(queryset, NoticeViewManager.objects.all())

        if queryset is None:
            queryset = NoticeViewManager.objects.none()

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["GET"], url_path="MustDisplay", detail=False)
    def must_display(self, request):
        fields = ["notice", "company"]

        if not set(fields).issubset(request.query_params.keys()):
            return error_message(400, "Faltam parâmetros obrigatórios")

        company = Company.objects.get(uuid=request.query_params.get("company"))
        try:
            notice_view = NoticeViewManager.objects.get(
                notice=request.query_params.get("notice")
            )
        except NoticeViewManager.DoesNotExist:
            raise serializers.ValidationError(
                "kartado.error.notice_view_manager.notice_not_exists"
            )

        try:
            user_notice_view = UserNoticeView.objects.get(
                company=company,
                notice_view_manager=notice_view,
                user=self.request.user,
            )
        except UserNoticeView.DoesNotExist:
            user_notice_view = UserNoticeView.objects.create(
                company=company,
                notice_view_manager=notice_view,
                user=self.request.user,
            )
        finally:
            result = user_notice_view.views_quantity < notice_view.views_quantity_limit

            response = {
                "userNoticeView": str(user_notice_view.uuid),
                "mustDisplay": result,
            }
            return Response(response)

    @action(methods=["GET"], url_path="NoticeDisplayed", detail=False)
    def notice_displayed(self, request):
        fields = ["user_notice_view"]

        if not set(fields).issubset(request.query_params.keys()):
            return error_message(400, "Faltam parâmetros obrigatórios")

        try:
            user_notice_view = UserNoticeView.objects.get(
                uuid=request.query_params.get("user_notice_view")
            )
        except UserNoticeView.DoesNotExist:
            raise serializers.ValidationError(
                "kartado.error.notice_view_manager.user_notice_view_not_exists"
            )
        else:
            user_notice_view.views_quantity = user_notice_view.views_quantity + 1
            user_notice_view.save()

            return Response({"status": "OK"})


class UserNoticeViewFilter(filters.FilterSet):
    uuid = ListFilter()
    user = ListFilter()

    class Meta:
        model = UserNoticeView
        fields = ["uuid", "company", "notice_view_manager", "user"]


class UserNoticeViewViewSet(viewsets.ModelViewSet):
    serializer_class = UserNoticeViewSerializer
    permission_classes = [IsAuthenticated, UserNoticeViewPermissions]
    filterset_class = UserNoticeViewFilter
    permissions = None

    ordering_fields = [
        "uuid",
        "company__name",
        "notice_view_manager",
        "user__first_name",
    ]
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        if self.action == "list":
            if "company" not in self.request.query_params:
                return UserNoticeView.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="UserNoticeView",
                )
            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, UserNoticeView.objects.none())

            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    UserNoticeView.objects.filter(
                        company_id=user_company, user=self.request.user
                    ),
                )

        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = UserNoticeView.objects.filter(
                company__in=user_companies, user=self.request.user
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())
