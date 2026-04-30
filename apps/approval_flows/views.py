import uuid

from django.db.models import Q
from django.utils.timezone import now
from django_filters import rest_framework as filters
from django_filters.filters import BooleanFilter, CharFilter
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.approval_flows.models import ApprovalFlow, ApprovalStep, ApprovalTransition
from apps.approval_flows.permissions import (
    ApprovalFlowPermissions,
    ApprovalStepPermissions,
    ApprovalTransitionPermissions,
)
from apps.approval_flows.serializers import (
    ApprovalFlowSerializer,
    ApprovalStepSerializer,
    ApprovalTransitionSerializer,
)
from apps.companies.models import Company
from apps.companies.views import get_access_request_queryset
from apps.daily_reports.models import MultipleDailyReport
from apps.reportings.models import Reporting
from helpers.dates import utc_to_local
from helpers.error_messages import error_message
from helpers.filters import ListFilter, UUIDListFilter
from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset
from helpers.strings import dict_to_casing, get_obj_from_path


class ApprovalFlowFilter(filters.FilterSet):
    uuid = UUIDListFilter()

    class Meta:
        model = ApprovalFlow
        fields = ["company"]


class ApprovalFlowView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = ApprovalFlowSerializer
    permission_classes = [IsAuthenticated, ApprovalFlowPermissions]
    filterset_class = ApprovalFlowFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ApprovalFlow.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ApprovalFlow",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ApprovalFlow.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ApprovalFlow.objects.filter(company_id=user_company),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ApprovalFlow.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ApprovalFlow.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ApprovalStepFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter(field_name="approval_flow__company")
    only_company = UUIDListFilter(field_name="approval_flow__company")
    approval_flow = UUIDListFilter()
    target_model = ListFilter(field_name="approval_flow__target_model")
    previous_steps_is_null = BooleanFilter(
        field_name="previous_steps", lookup_expr="isnull"
    )

    class Meta:
        model = ApprovalStep
        fields = ["company"]


class ApprovalStepView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = ApprovalStepSerializer
    permission_classes = [IsAuthenticated, ApprovalStepPermissions]
    filterset_class = ApprovalStepFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ApprovalStep.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])
            company = Company.objects.get(uuid=user_company)
            is_clustered_access_request = get_obj_from_path(
                company.metadata, "is_clustered_access_request", default_return=False
            )

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ApprovalStep",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ApprovalStep.objects.none())
            if "self" in allowed_queryset:
                if is_clustered_access_request:
                    access_requests = get_access_request_queryset(
                        "list", self.request, self.permissions
                    )
                    queryset = join_queryset(
                        queryset,
                        ApprovalStep.objects.filter(
                            Q(approval_flow__company_id=user_company)
                            | Q(step_requests__in=access_requests)
                        ),
                    )
                else:
                    queryset = join_queryset(
                        queryset,
                        ApprovalStep.objects.filter(
                            approval_flow__company_id=user_company
                        ),
                    )
            if "all" in allowed_queryset:
                if is_clustered_access_request:
                    access_requests = get_access_request_queryset(
                        "list", self.request, self.permissions
                    )
                    queryset = join_queryset(
                        queryset,
                        ApprovalStep.objects.filter(
                            Q(approval_flow__company_id=user_company)
                            | Q(step_requests__in=access_requests)
                        ),
                    )
                else:
                    queryset = join_queryset(
                        queryset,
                        ApprovalStep.objects.filter(
                            approval_flow__company_id=user_company
                        ),
                    )

            # Se os filtros específicos para passo inicial estiverem presentes,
            # retornar apenas o primeiro resultado (mesma lógica do InitialResponsibles e create)
            previous_steps_is_null = self.request.query_params.get(
                "previous_steps_is_null"
            )
            target_model = self.request.query_params.get("target_model")

            if previous_steps_is_null == "true" and target_model:
                # Aplicar a mesma lógica usada no InitialResponsibles e no create do serializer
                first_step = (
                    queryset.filter(
                        approval_flow__company_id=user_company,
                        approval_flow__target_model=target_model,
                        previous_steps__isnull=True,
                    )
                    .distinct()
                    .first()
                )

                # Se encontrou um passo inicial, criar queryset com apenas esse objeto
                if first_step:
                    queryset = ApprovalStep.objects.filter(pk=first_step.pk)
                else:
                    queryset = ApprovalStep.objects.none()

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ApprovalStep.objects.filter(
                approval_flow__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ApprovalTransitionFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="origin__approval_flow__company")
    origin = UUIDListFilter()
    destination = UUIDListFilter()
    approval_flow = UUIDListFilter(field_name="origin__approval_flow")

    class Meta:
        model = ApprovalTransition
        fields = ["company"]


class ApprovalTransitionView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = ApprovalTransitionSerializer
    permission_classes = [IsAuthenticated, ApprovalTransitionPermissions]
    filterset_class = ApprovalTransitionFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ApprovalTransition.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ApprovalTransition",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ApprovalTransition.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ApprovalTransition.objects.filter(
                        origin__approval_flow__company_id=user_company
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ApprovalTransition.objects.filter(
                        origin__approval_flow__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ApprovalTransition.objects.filter(
                origin__approval_flow__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ApprovalFlowNotifications(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        fields = ["company"]

        if not set(fields).issubset(request.query_params.keys()):
            return error_message(
                400,
                "Não é possível realizar esta operação sem todos os parâmetros obrigatórios.",
            )
        date = utc_to_local(now()).strftime("%Y-%m-%dT%H:%M:%S")
        user = request.user
        user_company = uuid.UUID(request.query_params["company"])
        user_firms = list(
            set(
                user.user_firms.filter(company_id=user_company).values_list(
                    "uuid", flat=True
                )
            )
        )
        company = Company.objects.get(uuid=user_company)
        limit = int(request.query_params.get("limit", 25))

        permissions = PermissionManager(
            user=user, company_ids=user_company, model="Reporting"
        )

        can_view_reporting = permissions.has_permission(permission="can_view")
        can_view_rdo = permissions.get_specific_model_permision(
            "MultipleDailyReport", "can_view"
        )
        response = {}
        response["notifications"] = {"reporting": [], "multiple_daily_report": []}
        if can_view_reporting:
            flows = get_obj_from_path(
                company.custom_options,
                "approvalnotificationsrules__reporting__app__flows",
            )
            approval_steps = ApprovalStep.objects.filter(uuid__in=flows)
            reportings = (
                Reporting.objects.filter(
                    company_id=user_company,
                    firm__uuid__in=user_firms,
                    approval_step__in=approval_steps,
                )
                .order_by("-created_at")
                .prefetch_related(
                    "created_by",
                    "firm",
                    "job",
                    "approval_step",
                    "approval_step__responsible_firms",
                    "approval_step__responsible_firms__users",
                    "approval_step__responsible_firms__manager",
                    "approval_step__responsible_users",
                )
                .only(
                    "uuid",
                    "number",
                    "created_by",
                    "approval_step",
                    "approval_step__responsible_firms",
                    "approval_step__responsible_firms__users",
                    "approval_step__responsible_firms__manager",
                    "approval_step__responsible_users",
                )[:limit]
            )

            for reporting in reportings:
                approval_step = reporting.approval_step
                user_flag = False
                created_by_flag = False
                firm_flag = False
                if user in approval_step.responsible_users.all():
                    user_flag = True
                if (
                    approval_step.responsible_created_by
                    and reporting.created_by
                    and reporting.created_by == user
                ):
                    created_by_flag = True
                for firm in approval_step.responsible_firms.all():
                    if (firm.manager and firm.manager == user) or (
                        user in firm.users.all()
                    ):
                        firm_flag = True

                if not any([user_flag, created_by_flag, firm_flag]):
                    continue

                response["notifications"]["reporting"].append(
                    {
                        "id": str(reporting.uuid),
                        "current_flow": approval_step.name,
                        "number": reporting.number,
                        "notified_at": date,
                        "team_name": reporting.firm.name if reporting.firm else "",
                        "job_uuid": (
                            str(reporting.job.uuid) if reporting.job else None
                        ),
                        "job_number": (reporting.job.number if reporting.job else "-"),
                    }
                )
        if can_view_rdo:
            flows = get_obj_from_path(
                company.custom_options,
                "approvalnotificationsrules__multipledailyreport__app__flows",
            )
            approval_steps = ApprovalStep.objects.filter(uuid__in=flows)
            mdrs = (
                MultipleDailyReport.objects.filter(
                    company_id=user_company,
                    firm__uuid__in=user_firms,
                    approval_step__in=approval_steps,
                )
                .order_by("-date")
                .prefetch_related(
                    "created_by",
                    "firm",
                    "approval_step",
                    "approval_step__responsible_firms",
                    "approval_step__responsible_firms__users",
                    "approval_step__responsible_firms__manager",
                    "approval_step__responsible_users",
                )
                .only(
                    "uuid",
                    "number",
                    "date",
                    "firm",
                    "created_by",
                    "approval_step",
                    "approval_step__responsible_firms",
                    "approval_step__responsible_firms__users",
                    "approval_step__responsible_firms__manager",
                    "approval_step__responsible_users",
                )[:limit]
            )

            for mdr in mdrs:
                approval_step = mdr.approval_step
                user_flag = False
                created_by_flag = False
                firm_flag = False
                if user in approval_step.responsible_users.all():
                    user_flag = True
                if (
                    approval_step.responsible_created_by
                    and mdr.created_by
                    and mdr.created_by == user
                ):
                    created_by_flag = True
                for firm in approval_step.responsible_firms.all():
                    if (firm.manager and firm.manager == user) or (
                        user in firm.users.all()
                    ):
                        firm_flag = True

                if not any([user_flag, created_by_flag, firm_flag]):
                    continue

                response["notifications"]["multiple_daily_report"].append(
                    {
                        "id": str(mdr.uuid),
                        "current_flow": approval_step.name,
                        "number": mdr.number,
                        "date": mdr.date.strftime("%d-%m-%Y") if mdr.date else "",
                        "firm": mdr.firm.name if mdr.firm else "",
                        "notified_at": date,
                    }
                )

        return Response(dict_to_casing(response))


class CheckNotificationAvailability(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        required_fields = ["company", "resource_type", "resource_uuid"]

        if not set(required_fields).issubset(request.query_params.keys()):
            return error_message(
                400,
                "Parâmetros obrigatórios: company, resource_type, resource_uuid.",
            )

        user = request.user
        user_company = uuid.UUID(request.query_params["company"])
        resource_type = request.query_params["resource_type"]
        resource_uuid = request.query_params["resource_uuid"]

        try:
            resource_uuid = uuid.UUID(resource_uuid)
        except ValueError:
            return error_message(400, "UUID do recurso inválido.")

        if resource_type not in ["reporting", "multiple_daily_report"]:
            return error_message(
                400, "resource_type deve ser 'reporting' ou 'multiple_daily_report'."
            )

        permissions = PermissionManager(
            user=user, company_ids=user_company, model="Reporting"
        )

        if resource_type == "reporting":
            can_view = permissions.has_permission(permission="can_view")
            if not can_view:
                return Response(
                    dict_to_casing(
                        {
                            "status": "unavailable",
                            "reason": "no_permission",
                            "has_job": False,
                            "job_uuid": None,
                            "job_number": None,
                        }
                    )
                )

            try:
                reporting = Reporting.objects.get(
                    uuid=resource_uuid, company_id=user_company
                )
            except Reporting.DoesNotExist:
                return Response(
                    dict_to_casing(
                        {
                            "status": "unavailable",
                            "reason": "not_found",
                            "has_job": False,
                            "job_uuid": None,
                            "job_number": None,
                        }
                    )
                )

            has_job = reporting.job is not None and not reporting.job.archived
            return Response(
                dict_to_casing(
                    {
                        "status": "available",
                        "reason": None,
                        "has_job": has_job,
                        "job_uuid": (
                            str(reporting.job.uuid)
                            if reporting.job and not reporting.job.archived
                            else None
                        ),
                        "job_number": (
                            reporting.job.number
                            if reporting.job and not reporting.job.archived
                            else None
                        ),
                    }
                )
            )

        elif resource_type == "multiple_daily_report":
            can_view = permissions.get_specific_model_permision(
                "MultipleDailyReport", "can_view"
            )
            if not can_view:
                return Response(
                    dict_to_casing(
                        {
                            "status": "unavailable",
                            "reason": "no_permission",
                            "is_in_last_seven": False,
                        }
                    )
                )

            try:
                mdr = MultipleDailyReport.objects.get(
                    uuid=resource_uuid, company_id=user_company
                )
            except MultipleDailyReport.DoesNotExist:
                return Response(
                    dict_to_casing(
                        {
                            "status": "unavailable",
                            "reason": "not_found",
                            "is_in_last_seven": False,
                        }
                    )
                )

            user_firms = list(
                user.user_firms.filter(company_id=user_company).values_list(
                    "uuid", flat=True
                )
            )

            if mdr.firm and mdr.firm.uuid in user_firms:
                last_seven_rdos = (
                    MultipleDailyReport.objects.filter(
                        company_id=user_company, firm=mdr.firm
                    )
                    .order_by("-date")
                    .values_list("uuid", flat=True)[:7]
                )
                is_in_last_seven = mdr.uuid in list(last_seven_rdos)
            else:
                is_in_last_seven = False

            return Response(
                dict_to_casing(
                    {
                        "status": "available" if is_in_last_seven else "unavailable",
                        "reason": None if is_in_last_seven else "not_in_last_seven",
                        "is_in_last_seven": is_in_last_seven,
                    }
                )
            )
