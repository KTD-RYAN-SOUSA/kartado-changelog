import uuid
from collections import defaultdict
from datetime import datetime

import sentry_sdk
from django.db.models import OuterRef, Q, Subquery
from django.db.models.signals import post_init, pre_init
from django.utils import timezone
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework_json_api import serializers

from apps.approval_flows.models import ApprovalTransition
from apps.companies.models import Company, SubCompany
from apps.reportings.models import Reporting
from apps.reportings.serializers import ReportingSerializer
from apps.resources.models import ContractPeriod
from apps.service_orders.const import resource_approval_status
from apps.service_orders.models import ProcedureResource
from apps.services.models import GoalAggregate, ServiceUsage
from helpers.apps.daily_reports import (
    destroy_report_board_items,
    is_holiday_for_firm,
    show_active_on_report_relationships,
)
from helpers.apps.json_logic import apply_json_logic
from helpers.apps.spreadsheet import (
    DailyReportEquipmentSpreadsheetEndpoint,
    DailyReportOccurrenceSpreadsheetEndpoint,
    DailyReportReportingRelationshipSpreadsheetEndpoint,
    DailyReportReportingResourceSpreadsheetEndpoint,
    DailyReportReportingSpreadsheetEndpoint,
    DailyReportResourceSpreadsheetEndpoint,
    DailyReportVehicleSpreadsheetEndpoint,
    DailyReportWorkerSpreadsheetEndpoint,
    MultipleDailyReportSpreadsheetEndpoint,
)
from helpers.dates import format_minutes
from helpers.error_messages import error_message
from helpers.extra_hours import calculate_extra_hours_worker, parse_time_to_minutes
from helpers.fields import get_nested_fields
from helpers.files import check_endpoint
from helpers.histories import bulk_update_with_history
from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset
from helpers.serializers import get_obj_serialized
from helpers.signals import DisableSignals
from helpers.strings import dict_to_casing, get_obj_from_path, to_snake_case
from helpers.views import format_item_payload

from .filters import (
    DailyReportContractUsageFilter,
    DailyReportEquipmentFilter,
    DailyReportExportFilter,
    DailyReportExternalTeamFilter,
    DailyReportFilter,
    DailyReportOccurrenceFilter,
    DailyReportRelationFilter,
    DailyReportResourceFilter,
    DailyReportSignalingFilter,
    DailyReportVehicleFilter,
    DailyReportWorkerFilter,
    MultipleDailyReportFileFilter,
    MultipleDailyReportFilter,
    MultipleDailyReportSignatureFilter,
    ProductionGoalFilter,
)
from .helpers import get_history, get_reportings_history
from .models import (
    DailyReport,
    DailyReportContractUsage,
    DailyReportEquipment,
    DailyReportExport,
    DailyReportExternalTeam,
    DailyReportOccurrence,
    DailyReportRelation,
    DailyReportResource,
    DailyReportSignaling,
    DailyReportVehicle,
    DailyReportWorker,
    MultipleDailyReport,
    MultipleDailyReportFile,
    MultipleDailyReportSignature,
    ProductionGoal,
)
from .notifications import report_transition
from .permissions import (
    DailyReportContractUsagePermissions,
    DailyReportEquipmentPermissions,
    DailyReportExportPermissions,
    DailyReportExternalTeamPermissions,
    DailyReportOccurrencePermissions,
    DailyReportPermissions,
    DailyReportRelationPermissions,
    DailyReportResourcePermissions,
    DailyReportSignalingPermissions,
    DailyReportVehiclePermissions,
    DailyReportWorkerPermissions,
    MultipleDailyReportFilePermissions,
    MultipleDailyReportPermissions,
    MultipleDailyReportSignaturePermissions,
    ProductionGoalPermissions,
)
from .serializers import (
    DailyReportContractUsageSerializer,
    DailyReportEquipmentSerializer,
    DailyReportExportSerializer,
    DailyReportExternalTeamSerializer,
    DailyReportOccurrenceSerializer,
    DailyReportRelationSerializer,
    DailyReportResourceSerializer,
    DailyReportSerializer,
    DailyReportSignalingSerializer,
    DailyReportVehicleSerializer,
    DailyReportWorkerSerializer,
    MultipleDailyReportFileObjectSerializer,
    MultipleDailyReportFileSerializer,
    MultipleDailyReportSerializer,
    MultipleDailyReportSignatureObjectSerializer,
    MultipleDailyReportSignatureSerializer,
    ProductionGoalSerializer,
)


class DailyReportViewSet(ModelViewSet):
    serializer_class = DailyReportSerializer
    filterset_class = DailyReportFilter
    permissions = None
    permission_classes = [IsAuthenticated, DailyReportPermissions]
    # Setting resource_name because we use the JSON API renderer
    # manually when checking approval permissions
    resource_name = "DailyReport"

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "company",
        "date",
        "day_without_work",
        "created_by__first_name",
        "responsible__first_name",
        "created_at",
        "number",
        "use_reporting_resources",
        "editable",
        "approval_step__name",
        # Weather
        "morning_weather",
        "afternoon_weather",
        "night_weather",
        # Conditions
        "morning_conditions",
        "afternoon_conditions",
        "night_conditions",
        # Duration
        "morning_start",
        "morning_end",
        "afternoon_start",
        "afternoon_end",
        "night_start",
        "night_end",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return DailyReport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="DailyReport",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, DailyReport.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, DailyReport.objects.filter(company_id=user_company)
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = DailyReport.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        # Always inject created_by
        kwargs = {"created_by": self.request.user}

        # If no responsible is provided, use current user
        if "responsible" not in serializer.validated_data:
            kwargs["responsible"] = self.request.user

        serializer.save(**kwargs)

    def perform_destroy(self, instance: DailyReport):
        destroy_report_board_items(daily_report=instance)
        return super().perform_destroy(instance)

    @action(methods=["GET"], url_path="Financials", detail=False)
    def get_financials(self, request):
        """
        Returns the financials until a given date
        company (an uuid) and date (2020-12-22 format) are required
        """

        response = []

        # Were the required attributes provided?
        if (
            "company" not in request.query_params.keys()
            or "date" not in request.query_params.keys()
        ):
            raise serializers.ValidationError(
                "Não é possível realizar esta operação sem atributos company ou date."
            )

        # Extract values
        company_id = request.query_params["company"]
        date = request.query_params["date"]

        try:
            date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise serializers.ValidationError(
                "date deve ser informada no formato '2021-12-23'"
            )

        try:
            company = Company.objects.get(uuid=company_id)
        except Company.DoesNotExist:
            raise serializers.ValidationError("company informada não existe")

        try:
            goal_aggregate = company.company_goal.get(
                start_date__date__lte=date, end_date__date__gte=date
            )
        except GoalAggregate.MultipleObjectsReturned:
            raise serializers.ValidationError(
                "Mais de um GoalAggregate foi encontrado para essa data"
            )
        except GoalAggregate.DoesNotExist:
            return Response(response)

        possible_path = "service__fields__group__selectoptions__options"
        group_options = get_obj_from_path(company.custom_options, possible_path)

        executed_reportings = Reporting.objects.filter(
            company=company, executed_at__date=date
        ).distinct("uuid")
        service_usages_day = (
            ServiceUsage.objects.select_related("service")
            .filter(service__company=company, reporting__in=executed_reportings)
            .values_list(
                "amount",
                "service__group",
                "service__unit_price",
                "service__adjustment_coefficient",
            )
        )

        executed_reportings_month = Reporting.objects.filter(
            company=company,
            executed_at__gte=datetime(date.year, date.month, 1, tzinfo=date.tzinfo),
            executed_at__lte=date,
        ).distinct("uuid")
        service_usages_month = (
            ServiceUsage.objects.select_related("service")
            .filter(service__company=company, reporting__in=executed_reportings_month)
            .values_list(
                "amount",
                "service__group",
                "service__unit_price",
                "service__adjustment_coefficient",
            )
        )

        for group_option in group_options:
            display_name = group_option["name"]
            group = group_option["value"]

            if group in goal_aggregate.group_goals:
                goal = goal_aggregate.group_goals[group]
            else:
                goal = 0.0

            # Calculations
            usages_day_for_group = [
                amount * unit_price * coefficient
                for (amount, usage_group, unit_price, coefficient) in service_usages_day
                if to_snake_case(usage_group) == group
            ]
            daily_value = sum(usages_day_for_group)

            usages_month_for_group = [
                amount * unit_price * coefficient
                for (
                    amount,
                    usage_group,
                    unit_price,
                    coefficient,
                ) in service_usages_month
                if to_snake_case(usage_group) == group
            ]
            month_to_date_value = sum(usages_month_for_group)

            response.append(
                {
                    "group": group,
                    "displayName": display_name,
                    "dailyValue": float(daily_value),
                    "monthToDateValue": float(month_to_date_value),
                    "goal": float(goal),
                }
            )

        return Response(response)

    @action(methods=["POST"], url_path="Approval", detail=True)
    def approval(self, request, pk=None):
        # Get all the ApprovalTransitions related to the current ApprovalStep
        daily_report = self.get_object()
        transitions = ApprovalTransition.objects.filter(
            origin=daily_report.approval_step
        )

        # Check if the condition from any ApprovalTransition was met
        # If the condition was met, execute the ApprovalStep change
        serializer = self.get_serializer_class()
        source = get_obj_serialized(daily_report, serializer, DailyReportViewSet)

        data = {"request": request.data, "source": source}

        for transition in transitions:
            if apply_json_logic(transition.condition, data):
                daily_report.approval_step = transition.destination

                for key, callback in transition.callback.items():
                    if key == "change_fields":
                        for field in callback:
                            try:
                                value = get_nested_fields(field["value"], daily_report)
                                setattr(daily_report, field["name"], value)
                            except Exception as e:
                                print("Exception setting model fields", e)
                    if key == "send_notification":
                        functions = {"daily_report_transition": report_transition}

                        for notification in callback:
                            if notification in functions:
                                message = transition.callback.get(
                                    "notification_message", ""
                                )

                                functions[notification](
                                    daily_report, message, request.user
                                )

                daily_report.save()

                # Handle reason
                to_do = request.data.get("to_do")

                hist = daily_report.history.first()
                hist.history_change_reason = to_do
                hist.save()

                return Response({"data": {"status": "OK"}})

        return Response(
            data=[
                {
                    "detail": "Nenhuma condição foi aceita.",
                    "source": {"pointer": "/data"},
                    "status": status.HTTP_400_BAD_REQUEST,
                }
            ],
            status=status.HTTP_400_BAD_REQUEST,
        )


class MultipleDailyReportViewSet(ModelViewSet):
    serializer_class = MultipleDailyReportSerializer
    filterset_class = MultipleDailyReportFilter
    permissions = None
    permission_classes = [IsAuthenticated, MultipleDailyReportPermissions]
    # Setting resource_name because we use the JSON API renderer
    # manually when checking approval permissions
    resource_name = "MultipleDailyReport"
    validated_objs = None
    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "company",
        "date",
        "day_without_work",
        "created_by__first_name",
        "responsible__first_name",
        "created_at",
        "firm__name",
        "reportings",
        "number",
        "use_reporting_resources",
        "editable",
        "approval_step__name",
        "firm__subcompany__name",
        # Weather
        "morning_weather",
        "afternoon_weather",
        "night_weather",
        # Conditions
        "morning_conditions",
        "afternoon_conditions",
        "night_conditions",
        # Duration
        "morning_start",
        "morning_end",
        "afternoon_start",
        "afternoon_end",
        "night_start",
        "night_end",
        "firm__name",
    ]

    def get_serializer_context(self):
        context = super(MultipleDailyReportViewSet, self).get_serializer_context()
        user = context["request"].user

        # The current user is not anonymous and the action is list or retrieve
        if not user.is_anonymous:
            try:
                if context["view"].permissions:
                    context.update(
                        {
                            "user_firms": user.user_firms.filter(
                                company_id=context["view"].permissions.company_id
                            )
                        }
                    )
                    multiple_daily_report_permissions = (
                        self.permissions.get_model_permission("MultipleDailyReport")
                    )
                    can_edit = (
                        multiple_daily_report_permissions.get("can_edit")[0]
                        if multiple_daily_report_permissions.get("can_edit") is not None
                        else False
                    )

                    can_create_and_edit_all_firms = (
                        multiple_daily_report_permissions.get(
                            "can_create_and_edit_all_firms"
                        )[0]
                        if multiple_daily_report_permissions.get(
                            "can_create_and_edit_all_firms"
                        )
                        is not None
                        else False
                    )

                    context.update(
                        {"can_create_and_edit_all_firms": can_create_and_edit_all_firms}
                    )

                    if can_edit:
                        can_create_and_edit_all_firms = (
                            multiple_daily_report_permissions.get(
                                "can_create_and_edit_all_firms"
                            )[0]
                            if multiple_daily_report_permissions.get(
                                "can_create_and_edit_all_firms"
                            )
                            is not None
                            else False
                        )
                        if can_create_and_edit_all_firms:
                            context.update({"can_you_edit": True})
                            return context

                        else:
                            # if the user does not have the permission above, check if is part of the firm in serializer
                            context.update({"can_you_edit": False})

                    else:
                        return context

            except AttributeError as err:
                # Send the exception to Sentry
                sentry_sdk.capture_exception(err)

        return context

    def get_queryset(self, skip_eager_loading=False):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action in [
            "list",
            "spreadsheet_multiple_daily_report",
            "spreadsheet_daily_report_vehicle",
            "spreadsheet_daily_report_equipment",
            "spreadsheet_daily_report_worker",
            "spreadsheet_daily_report_occurrence",
            "spreadsheet_daily_report_resource",
            "spreadsheet_reporting_resource",
            "spreadsheet_reporting",
            "spreadsheet_reporting_relationship",
        ]:
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return MultipleDailyReport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MultipleDailyReport",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, MultipleDailyReport.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MultipleDailyReport.objects.filter(company_id=user_company),
                )

            if "firm" in allowed_queryset:
                multiple_daily_report_permissions = (
                    self.permissions.get_model_permission("MultipleDailyReport")
                )
                can_view_all_firms = (
                    multiple_daily_report_permissions.get("can_view_all_firms")[0]
                    if multiple_daily_report_permissions.get("can_view_all_firms")
                    is not None
                    else False
                )

                if (
                    not self.request.query_params.get("jobs_rdos_user_firms")
                    and can_view_all_firms
                ):
                    queryset = join_queryset(
                        queryset,
                        MultipleDailyReport.objects.filter(company_id=user_company),
                    )
                else:
                    # Returns all multiples daily reports teams the user is a member of
                    queryset = join_queryset(
                        queryset,
                        MultipleDailyReport.objects.filter(
                            Q(company_id=user_company)
                            & Q(
                                Q(firm__inspectors__uuid=self.request.user.uuid)
                                | Q(firm__users__uuid=self.request.user.uuid)
                                | Q(firm__manager_id=self.request.user.uuid)
                            ),
                        ),
                    )

            subcompany_queryset = self.permissions.get_specific_model_permision(
                "SubCompany", "queryset"
            )

            if subcompany_queryset == "self" and queryset is not None:
                user_subcompanies = SubCompany.objects.filter(
                    Q(company_id=user_company)
                    & (
                        Q(responsible=self.request.user)
                        | Q(subcompany_firms__users=self.request.user)
                        | Q(subcompany_firms__inspectors=self.request.user)
                        | Q(subcompany_firms__manager=self.request.user)
                    )
                )
                queryset = queryset.filter(firm__subcompany__in=user_subcompanies)

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MultipleDailyReport.objects.filter(company__in=user_companies)

        # NOTE: When the queryset won't be used in the serializer
        if skip_eager_loading:
            return queryset

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        created_by = serializer.validated_data.get("created_by", self.request.user)
        # If no responsible is provided, use current user
        responsible = serializer.validated_data.get("responsible", self.request.user)

        instance = serializer.save(created_by=created_by, responsible=responsible)
        instance._history_user = created_by
        instance.save()

    def perform_destroy(self, instance: MultipleDailyReport):
        destroy_report_board_items(multiple_daily_report=instance)
        return super().perform_destroy(instance)

    @action(methods=["GET"], url_path="AggregateResources", detail=True)
    def get_aggregate_resources(self, request, pk=None):
        multiple_daily_report = self.get_object()

        reportings_resources = (
            multiple_daily_report.reportings.filter(
                reporting_resources__isnull=False
            ).values_list(
                "uuid",
                "number",
                "reporting_resources__uuid",
                "reporting_resources__amount",
                "reporting_resources__resource__name",
                "reporting_resources__resource__unit",
                "reporting_resources__resource__uuid",
            )
            if multiple_daily_report.reportings
            else []
        )

        aggr_dict = {}
        for (
            reporting_uuid,
            reporting_number,
            proc_res_id,
            proc_res_amount,
            resource_name,
            resource_unit,
            resource_uuid,
        ) in reportings_resources:
            if resource_name in aggr_dict:
                aggr_dict[resource_name]["reportingAmount"] += proc_res_amount
                aggr_dict[resource_name]["procedureResources"].append(str(proc_res_id))
                aggr_dict[resource_name]["reportings"].append(
                    {
                        "uuid": reporting_uuid,
                        "amount": proc_res_amount,
                        "number": reporting_number,
                    }
                )
            else:
                aggr_dict[resource_name] = {
                    "reportingAmount": proc_res_amount,
                    "procedureResources": [str(proc_res_id)],
                    "unit": resource_unit,
                    "dailyReportAmount": 0,  # Sets default value for later
                    "uuid": resource_uuid,
                    "reportings": [
                        {
                            "uuid": reporting_uuid,
                            "amount": proc_res_amount,
                            "number": reporting_number,
                        }
                    ],
                }

        # DailyReportResource
        report_resources = (
            multiple_daily_report.multiple_daily_report_resources.filter(
                resource__isnull=False
            ).values_list(
                "amount", "resource__name", "resource__unit", "resource__uuid"
            )
            if multiple_daily_report.multiple_daily_report_resources
            else []
        )
        for amount, resource_name, resource_unit, resource_uuid in report_resources:
            if resource_name in aggr_dict:
                aggr_dict[resource_name]["dailyReportAmount"] += amount
            else:
                # Getting here means the Resource is only present in the report
                aggr_dict[resource_name] = {
                    "dailyReportAmount": amount,
                    "unit": resource_unit,
                    "reportingAmount": 0,  # Default value
                    "procedureResources": [],  # Default value
                    "reportings": [],  # Default value
                    "uuid": resource_uuid,
                }

        # Turn aggregation dict into list
        response_data = {"data": []}
        for aggr_resource_name, dict_data in aggr_dict.items():
            response_data["data"].append(
                {
                    "resourceName": aggr_resource_name,
                    "reportingAmount": dict_data["reportingAmount"],
                    "dailyReportAmount": dict_data["dailyReportAmount"],
                    "procedureResources": dict_data["procedureResources"],
                    "unit": dict_data["unit"],
                    "uuid": dict_data["uuid"],
                    "reportings": dict_data["reportings"],
                }
            )

        return Response(response_data)

    @action(methods=["POST"], url_path="Approval", detail=True)
    def approval(self, request, pk=None):
        # Get all the ApprovalTransitions related to the current ApprovalStep
        multiple_daily_report = self.get_object()
        transitions = ApprovalTransition.objects.filter(
            origin=multiple_daily_report.approval_step
        )

        # Check if the condition from any ApprovalTransition was met
        # If the condition was met, execute the ApprovalStep change
        serializer = self.get_serializer_class()
        serializer_context = self.get_serializer_context()
        source = get_obj_serialized(
            multiple_daily_report,
            serializer,
            MultipleDailyReportViewSet,
            serializer_context=serializer_context,
        )

        data = {"request": request.data, "source": source}

        for transition in transitions:
            if apply_json_logic(transition.condition, data):
                for key, callback in transition.callback.items():
                    if (
                        key == "save_item_before_action"
                        and isinstance(callback, bool)
                        and callback is True
                        and multiple_daily_report.editable
                    ):
                        item_payload = request.data.get("item_payload", None)
                        if item_payload:
                            item_payload = format_item_payload(request)
                            serializer = MultipleDailyReportSerializer(
                                instance=multiple_daily_report,
                                data=item_payload,
                                partial=True,
                                context=serializer_context,
                            )
                            valid = serializer.is_valid()
                            if valid:
                                serializer.save()
                            else:
                                raise serializers.ValidationError(
                                    "kartado.error.multiple_daily_report.invalid_format"
                                )
                multiple_daily_report.approval_step = transition.destination

                for key, callback in transition.callback.items():
                    if key == "change_fields":
                        for field in callback:
                            try:
                                value = get_nested_fields(
                                    field["value"], multiple_daily_report
                                )
                                setattr(multiple_daily_report, field["name"], value)
                            except Exception as e:
                                print("Exception setting model fields", e)
                    if key == "send_notification":
                        functions = {
                            "multiple_daily_report_transition": report_transition
                        }

                        for notification in callback:
                            if notification in functions:
                                message = transition.callback.get(
                                    "notification_message", ""
                                )

                                functions[notification](
                                    multiple_daily_report, message, request.user
                                )

                multiple_daily_report.save()

                # Handle reason
                if "to_do" in request.data:
                    to_do = request.data.get("to_do")
                    hist = multiple_daily_report.history.first()
                    if hist:
                        hist.history_change_reason = to_do
                        hist.save()

                return Response({"data": {"status": "OK"}})

        return Response(
            data=[
                {
                    "detail": "Nenhuma condição foi aceita.",
                    "source": {"pointer": "/data"},
                    "status": status.HTTP_400_BAD_REQUEST,
                }
            ],
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(methods=["delete"], url_path="Bulk", detail=False)
    def bulk(self, request, pk=None):
        if not all(self.validated_objs.values_list("editable", flat=True)):
            raise serializers.ValidationError(
                "Apenas RDOs editaveis podem ser deletados."
            )
        if self.permissions.has_permission(permission="can_delete_all"):
            self.validated_objs.delete()

        elif self.permissions.has_permission(permission="can_delete"):
            self.validated_objs.filter(created_by=request.user).delete()

        return Response({"data": {"status": "OK"}})

    @action(methods=["post"], url_path="BulkApproval", detail=False)
    def bulk_approval(self, request):
        prefetch_related_fields = [
            "approval_step",
            "approval_step__origin_transitions",
            "approval_step__origin_transitions__destination",
            "created_by",
        ]

        rdo_payload = request.data.get("multiple_daily_reports", [])

        if not (1 <= len(rdo_payload) <= 25):
            return Response(
                data=[
                    {
                        "detail": "A quantidade de RDOs deve ser entre 1 e 25.",
                        "source": {"pointer": "/data"},
                        "status": status.HTTP_400_BAD_REQUEST,
                    }
                ],
                status=status.HTTP_400_BAD_REQUEST,
            )

        rdo_ids = [rdo["id"] for rdo in rdo_payload]
        rdos = MultipleDailyReport.objects.filter(pk__in=rdo_ids).prefetch_related(
            *prefetch_related_fields
        )

        approval_step_ids = list(
            rdos.values_list("approval_step_id", flat=True).distinct()
        )
        all_transitions = ApprovalTransition.objects.filter(
            origin_id__in=approval_step_ids
        ).prefetch_related("origin", "destination")
        transitions_by_origin = defaultdict(list)
        for transition in all_transitions:
            transitions_by_origin[transition.origin_id].append(transition)

        serializer_class = self.get_serializer_class()
        rdo_transition_map = {}

        for rdo in rdos:
            transitions = transitions_by_origin.get(rdo.approval_step_id, [])
            source = get_obj_serialized(
                rdo,
                serializer_class,
                MultipleDailyReportViewSet,
                serializer_context=self.get_serializer_context(),
            )
            data = {"request": request.data, "source": source}

            accepted = False
            for transition in transitions:
                if apply_json_logic(transition.condition, data):
                    rdo_transition_map[rdo] = transition
                    accepted = True
                    break

            if not accepted:
                return Response(
                    data=[
                        {
                            "detail": "Nenhuma condição do RDO {} foi aceita.".format(
                                rdo.number,
                            ),
                            "source": {"pointer": "/data"},
                            "status": status.HTTP_400_BAD_REQUEST,
                        }
                    ],
                    status=status.HTTP_400_BAD_REQUEST,
                )

        notification_functions = {"multiple_daily_report_transition": report_transition}
        rdos_to_update = []
        notifications_to_send = []
        for rdo, transition in rdo_transition_map.items():
            rdo.approval_step = transition.destination

            for key, callback in transition.callback.items():
                if key == "change_fields":
                    for field in callback:
                        try:
                            value = get_nested_fields(field["value"], rdo)
                            setattr(rdo, field["name"], value)
                        except Exception as e:
                            print("Exception setting model fields", e)
                if key == "send_notification":
                    for notification_type in callback:
                        if notification_type in notification_functions:
                            message = transition.callback.get(
                                "notification_message", ""
                            )
                            notifications_to_send.append(
                                (
                                    rdo,
                                    message,
                                    notification_functions[notification_type],
                                )
                            )

            rdos_to_update.append(rdo)

        if rdos_to_update:
            bulk_update_with_history(
                rdos_to_update,
                MultipleDailyReport,
                use_django_bulk=True,
                user=request.user,
                batch_size=25,
            )

        for rdo, message, notify_fn in notifications_to_send:
            notify_fn(rdo, message, request.user)

        if "to_do" in request.data and rdos_to_update:
            to_do = request.data["to_do"]
            rdo_pks = [r.pk for r in rdos_to_update]
            historical_model = MultipleDailyReport.history.model
            latest_history_subquery = (
                historical_model.objects.filter(uuid=OuterRef("uuid"))
                .order_by("-history_date", "-history_id")
                .values("history_id")[:1]
            )
            historical_model.objects.filter(
                uuid__in=rdo_pks,
                history_id=Subquery(latest_history_subquery),
            ).update(history_change_reason=to_do)

        return Response({"data": {"status": "OK"}})

    @action(methods=["get"], url_path="History", detail=True)
    def history(self, request, pk=None):
        with DisableSignals(
            disabled_signals=[
                pre_init,
                post_init,
            ]
        ):
            mdr = self.get_object()
            data = get_history(mdr)
            return Response(data=data, status=status.HTTP_200_OK)

    @action(methods=["get"], url_path="HistoryReportings", detail=True)
    def history_reportings(self, request, pk=None):
        with DisableSignals(
            disabled_signals=[
                pre_init,
                post_init,
            ]
        ):
            mdr = self.get_object()
            data = get_reportings_history(mdr)
            return Response(data=data, status=status.HTTP_200_OK)

    @action(methods=["get"], url_path="Spreadsheet", detail=False)
    def spreadsheet_multiple_daily_report(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        if self.permissions.company_id:
            company = Company.objects.get(uuid=self.permissions.company_id)
        else:
            company = queryset.first().company

        page = self.paginate_queryset(queryset)
        if page is not None:
            data = MultipleDailyReportSpreadsheetEndpoint(page, company).get_data()
            return self.get_paginated_response(data)

        data = MultipleDailyReportSpreadsheetEndpoint(queryset, company).get_data()

        return Response(data)

    @action(methods=["get"], url_path="SpreadsheetVehicle", detail=False)
    def spreadsheet_daily_report_vehicle(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        if self.permissions.company_id:
            company = Company.objects.get(uuid=self.permissions.company_id)
        else:
            company = queryset.first().company

        vehicles_filtered = DailyReportVehicle.objects.filter(
            multiple_daily_reports__in=queryset
        ).distinct()

        page = self.paginate_queryset(vehicles_filtered)
        if page is not None:
            data = DailyReportVehicleSpreadsheetEndpoint(page, company).get_data()
            return self.get_paginated_response(data)

        data = DailyReportVehicleSpreadsheetEndpoint(
            vehicles_filtered, company
        ).get_data()
        return Response(data)

    @action(methods=["get"], url_path="SpreadsheetEquipment", detail=False)
    def spreadsheet_daily_report_equipment(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        if self.permissions.company_id:
            company = Company.objects.get(uuid=self.permissions.company_id)
        else:
            company = queryset.first().company

        equipments_filtered = DailyReportEquipment.objects.filter(
            multiple_daily_reports__in=queryset
        ).distinct()

        page = self.paginate_queryset(equipments_filtered)
        if page is not None:
            data = DailyReportEquipmentSpreadsheetEndpoint(page, company).get_data()
            return self.get_paginated_response(data)

        data = DailyReportEquipmentSpreadsheetEndpoint(
            equipments_filtered, company
        ).get_data()
        return Response(data)

    @action(methods=["get"], url_path="SpreadsheetWorker", detail=False)
    def spreadsheet_daily_report_worker(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        if self.permissions.company_id:
            company = Company.objects.get(uuid=self.permissions.company_id)
        else:
            company = queryset.first().company

        workers_filtered = DailyReportWorker.objects.filter(
            multiple_daily_reports__in=queryset
        ).distinct()

        page = self.paginate_queryset(workers_filtered)
        if page is not None:
            data = DailyReportWorkerSpreadsheetEndpoint(page, company).get_data()
            return self.get_paginated_response(data)

        data = DailyReportWorkerSpreadsheetEndpoint(
            workers_filtered, company
        ).get_data()
        return Response(data)

    @action(methods=["get"], url_path="SpreadsheetOccurrence", detail=False)
    def spreadsheet_daily_report_occurrence(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        if self.permissions.company_id:
            company = Company.objects.get(uuid=self.permissions.company_id)
        else:
            company = queryset.first().company

        occurrences_filtered = DailyReportOccurrence.objects.filter(
            multiple_daily_reports__in=queryset
        ).distinct()

        page = self.paginate_queryset(occurrences_filtered)
        if page is not None:
            data = DailyReportOccurrenceSpreadsheetEndpoint(page, company).get_data()
            return self.get_paginated_response(data)

        data = DailyReportOccurrenceSpreadsheetEndpoint(
            occurrences_filtered, company
        ).get_data()
        return Response(data)

    @action(methods=["get"], url_path="SpreadsheetResource", detail=False)
    def spreadsheet_daily_report_resource(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        if self.permissions.company_id:
            company = Company.objects.get(uuid=self.permissions.company_id)
        else:
            company = queryset.first().company

        resources_filtered = DailyReportResource.objects.filter(
            multiple_daily_reports__in=queryset
        ).distinct()
        page = self.paginate_queryset(resources_filtered)
        if page is not None:
            data = DailyReportResourceSpreadsheetEndpoint(page, company).get_data()
            return self.get_paginated_response(data)

        data = DailyReportResourceSpreadsheetEndpoint(
            resources_filtered, company
        ).get_data()
        return Response(data)

    @action(methods=["get"], url_path="SpreadsheetReportingResource", detail=False)
    def spreadsheet_reporting_resource(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        if self.permissions.company_id:
            company = Company.objects.get(uuid=self.permissions.company_id)
        else:
            company = queryset.first().company

        reportings_filtered = Reporting.objects.filter(
            reporting_multiple_daily_reports__in=queryset
        )
        resources_filtered = (
            ProcedureResource.objects.filter(reporting__in=reportings_filtered)
            .prefetch_related("resource", "reporting")
            .distinct()
        )
        page = self.paginate_queryset(resources_filtered)
        if page is not None:
            data = DailyReportReportingResourceSpreadsheetEndpoint(
                page, company
            ).get_data()
            return self.get_paginated_response(data)

        data = DailyReportReportingResourceSpreadsheetEndpoint(
            resources_filtered, company
        ).get_data()
        return Response(data)

    @action(methods=["get"], url_path="SpreadsheetReporting", detail=False)
    def spreadsheet_reporting(self, request):
        queryset = self.filter_queryset(self.get_queryset(skip_eager_loading=True))
        if self.permissions.company_id:
            company = Company.objects.get(uuid=self.permissions.company_id)
        else:
            company = queryset.first().company
        reps_filtered = (
            Reporting.objects.filter(
                reporting_multiple_daily_reports__in=queryset,
            )
            .exclude(occurrence_type__occurrence_kind="2")
            .prefetch_related(*ReportingSerializer._PREFETCH_RELATED_FIELDS)
            .distinct()
        )
        page = self.paginate_queryset(reps_filtered)
        if page is not None:
            data = DailyReportReportingSpreadsheetEndpoint(page, company).get_data()
            return self.get_paginated_response(data)

        data = DailyReportReportingSpreadsheetEndpoint(
            reps_filtered, company
        ).get_data()
        return Response(data)

    @action(methods=["get"], url_path="SpreadsheetReportingRelationship", detail=False)
    def spreadsheet_reporting_relationship(self, request):
        queryset = self.filter_queryset(self.get_queryset(skip_eager_loading=True))
        if self.permissions.company_id:
            company = Company.objects.get(uuid=self.permissions.company_id)
        else:
            company = queryset.first().company

        mid_queryset = (
            MultipleDailyReport.reportings.through.objects.filter(
                multipledailyreport_id__in=[a.uuid for a in queryset]
            )
            .order_by("id")
            .distinct("id")
        )

        page = self.paginate_queryset(mid_queryset)
        if page is not None:
            data = DailyReportReportingRelationshipSpreadsheetEndpoint(
                page, company
            ).get_data()
            return self.get_paginated_response(data)

        data = DailyReportReportingRelationshipSpreadsheetEndpoint(
            mid_queryset, company
        ).get_data()
        return Response(data)


class DailyReportWorkerViewSet(ModelViewSet):
    serializer_class = DailyReportWorkerSerializer
    filterset_class = DailyReportWorkerFilter
    permissions = None
    permission_classes = [IsAuthenticated, DailyReportWorkerPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "daily_reports",
        "firm__name",
        "company",
        "members",
        "amount",
        "role",
        "creation_date",
        "total_price",
        "contract_item_administration",
        "approval_status",
        "approval_date",
        "approved_by",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return DailyReportWorker.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="DailyReportWorker",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, DailyReportWorker.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    DailyReportWorker.objects.filter(
                        Q(firm__company_id=user_company) | Q(company__uuid=user_company)
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = DailyReportWorker.objects.filter(
                Q(firm__company__in=user_companies) | Q(company__in=user_companies)
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def list(self, request, *args, **kwargs):
        list_response = super().list(request, *args, **kwargs)
        show_active = request.query_params.get("show_active", None) == "true"
        return show_active_on_report_relationships(show_active, list_response, "worker")

    @action(methods=["post"], url_path="Approval", detail=True)
    def approval(self, request, pk=None):
        instance = self.get_object()

        if "approve" in request.data.keys():
            instance.approval_date = timezone.now()
            instance.approved_by = request.user

            approval_flag = request.data.get("approve", False)
            instance.approval_status = (
                resource_approval_status.APPROVED_APPROVAL
                if approval_flag
                else resource_approval_status.DENIED_APPROVAL
            )

            # Call save to trigger signals
            instance.save()

            # Handle reason
            to_do = request.data.get("to_do", None)
            history_change_reason = request.data.get("history_change_reason", None)
            reason = to_do if to_do else history_change_reason
            if reason and isinstance(reason, str):
                hist = instance.history.first()
                hist.history_change_reason = reason
                hist.save()

            return Response({"data": {"status": "OK"}})
        else:
            return Response(
                data=[
                    {
                        "detail": "O parâmetro approve_resource (bool) não foi localizado.",
                        "source": {"pointer": "/data"},
                        "status": status.HTTP_400_BAD_REQUEST,
                    }
                ],
                status=status.HTTP_400_BAD_REQUEST,
            )


class DailyReportExternalTeamViewSet(ModelViewSet):
    serializer_class = DailyReportExternalTeamSerializer
    filterset_class = DailyReportExternalTeamFilter
    permissions = None
    permission_classes = [IsAuthenticated, DailyReportExternalTeamPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "daily_reports",
        "company",
        "contract_number",
        "contractor_name",
        "amount",
        "contract_description",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return DailyReportExternalTeam.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="DailyReportExternalTeam",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(
                    queryset, DailyReportExternalTeam.objects.none()
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    DailyReportExternalTeam.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = DailyReportExternalTeam.objects.filter(
                company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def list(self, request, *args, **kwargs):
        list_response = super().list(request, *args, **kwargs)
        show_active = request.query_params.get("show_active", None) == "true"
        return show_active_on_report_relationships(
            show_active, list_response, "external_team"
        )


class DailyReportEquipmentViewSet(ModelViewSet):
    serializer_class = DailyReportEquipmentSerializer
    filterset_class = DailyReportEquipmentFilter
    permissions = None
    permission_classes = [IsAuthenticated, DailyReportEquipmentPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "daily_reports",
        "company",
        "kind",
        "description",
        "amount",
        "creation_date",
        "total_price",
        "contract_item_administration",
        "approval_status",
        "approval_date",
        "approved_by",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return DailyReportEquipment.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="DailyReportEquipment",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, DailyReportEquipment.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    DailyReportEquipment.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = DailyReportEquipment.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def list(self, request, *args, **kwargs):
        list_response = super().list(request, *args, **kwargs)
        show_active = request.query_params.get("show_active", None) == "true"
        return show_active_on_report_relationships(
            show_active, list_response, "equipment"
        )

    @action(methods=["post"], url_path="Approval", detail=True)
    def approval(self, request, pk=None):
        instance = self.get_object()

        if "approve" in request.data.keys():
            instance.approval_date = timezone.now()
            instance.approved_by = request.user

            approval_flag = request.data.get("approve", False)
            instance.approval_status = (
                resource_approval_status.APPROVED_APPROVAL
                if approval_flag
                else resource_approval_status.DENIED_APPROVAL
            )

            # Call save to trigger signals
            instance.save()

            # Handle reason
            to_do = request.data.get("to_do", None)
            history_change_reason = request.data.get("history_change_reason", None)
            reason = to_do if to_do else history_change_reason
            if reason and isinstance(reason, str):
                hist = instance.history.first()
                hist.history_change_reason = reason
                hist.save()

            return Response({"data": {"status": "OK"}})
        else:
            return Response(
                data=[
                    {
                        "detail": "O parâmetro approve_resource (bool) não foi localizado.",
                        "source": {"pointer": "/data"},
                        "status": status.HTTP_400_BAD_REQUEST,
                    }
                ],
                status=status.HTTP_400_BAD_REQUEST,
            )


class DailyReportVehicleViewSet(ModelViewSet):
    serializer_class = DailyReportVehicleSerializer
    filterset_class = DailyReportVehicleFilter
    permissions = None
    permission_classes = [IsAuthenticated, DailyReportVehiclePermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "daily_reports",
        "company",
        "kind",
        "description",
        "amount",
        "creation_date",
        "total_price",
        "contract_item_administration",
        "approval_status",
        "approval_date",
        "approved_by",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return DailyReportVehicle.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="DailyReportVehicle",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, DailyReportVehicle.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, DailyReportVehicle.objects.filter(company_id=user_company)
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = DailyReportVehicle.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def list(self, request, *args, **kwargs):
        list_response = super().list(request, *args, **kwargs)
        show_active = request.query_params.get("show_active", None) == "true"
        return show_active_on_report_relationships(
            show_active, list_response, "vehicle"
        )

    @action(methods=["post"], url_path="Approval", detail=True)
    def approval(self, request, pk=None):
        instance = self.get_object()

        if "approve" in request.data.keys():
            instance.approval_date = timezone.now()
            instance.approved_by = request.user

            approval_flag = request.data.get("approve", False)
            instance.approval_status = (
                resource_approval_status.APPROVED_APPROVAL
                if approval_flag
                else resource_approval_status.DENIED_APPROVAL
            )

            # Call save to trigger signals
            instance.save()

            # Handle reason
            to_do = request.data.get("to_do", None)
            history_change_reason = request.data.get("history_change_reason", None)
            reason = to_do if to_do else history_change_reason
            if reason and isinstance(reason, str):
                hist = instance.history.first()
                hist.history_change_reason = reason
                hist.save()

            return Response({"data": {"status": "OK"}})
        else:
            return Response(
                data=[
                    {
                        "detail": "O parâmetro approve_resource (bool) não foi localizado.",
                        "source": {"pointer": "/data"},
                        "status": status.HTTP_400_BAD_REQUEST,
                    }
                ],
                status=status.HTTP_400_BAD_REQUEST,
            )


class DailyReportSignalingViewSet(ModelViewSet):
    serializer_class = DailyReportSignalingSerializer
    filterset_class = DailyReportSignalingFilter
    permissions = None
    permission_classes = [IsAuthenticated, DailyReportSignalingPermissions]

    ordering = "uuid"
    ordering_fields = ["uuid", "daily_reports", "company", "kind"]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return DailyReportSignaling.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="DailyReportSignaling",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, DailyReportSignaling.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    DailyReportSignaling.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = DailyReportSignaling.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def list(self, request, *args, **kwargs):
        list_response = super().list(request, *args, **kwargs)
        show_active = request.query_params.get("show_active", None) == "true"
        return show_active_on_report_relationships(
            show_active, list_response, "signaling"
        )


class DailyReportOccurrenceViewSet(ModelViewSet):
    serializer_class = DailyReportOccurrenceSerializer
    filterset_class = DailyReportOccurrenceFilter
    permissions = None
    permission_classes = [IsAuthenticated, DailyReportOccurrencePermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "daily_reports",
        "multiple_daily_reports",
        "firm__name",
        "starts_at",
        "ends_at",
        "impact_duration",
        "description",
        "extra_info",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return DailyReportOccurrence.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="DailyReportOccurrence",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, DailyReportOccurrence.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    DailyReportOccurrence.objects.filter(firm__company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = DailyReportOccurrence.objects.filter(
                firm__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def list(self, request, *args, **kwargs):
        list_response = super().list(request, *args, **kwargs)
        show_active = request.query_params.get("show_active", None) == "true"
        return show_active_on_report_relationships(
            show_active, list_response, "occurrence"
        )


class DailyReportResourceViewSet(ModelViewSet):
    serializer_class = DailyReportResourceSerializer
    filterset_class = DailyReportResourceFilter
    permissions = None
    permission_classes = [IsAuthenticated, DailyReportResourcePermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "daily_reports",
        "multiple_daily_reports",
        "kind",
        "amount",
        "resource",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return DailyReportResource.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="DailyReportResource",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, DailyReportResource.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    DailyReportResource.objects.filter(
                        resource__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = DailyReportResource.objects.filter(
                resource__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def list(self, request, *args, **kwargs):
        list_response = super().list(request, *args, **kwargs)
        show_active = request.query_params.get("show_active", None) == "true"
        return show_active_on_report_relationships(
            show_active, list_response, "resource"
        )


class ProductionGoalViewSet(ModelViewSet):
    serializer_class = ProductionGoalSerializer
    filterset_class = ProductionGoalFilter
    permissions = None
    permission_classes = [IsAuthenticated, ProductionGoalPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "daily_reports",
        "multiple_daily_reports",
        "service",
        "starts_at",
        "ends_at",
        "days_of_work",
        "amount",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return ProductionGoal.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ProductionGoal",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ProductionGoal.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ProductionGoal.objects.filter(service__company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ProductionGoal.objects.filter(
                service__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def list(self, request, *args, **kwargs):
        list_response = super().list(request, *args, **kwargs)
        show_active = request.query_params.get("show_active", None) == "true"
        return show_active_on_report_relationships(
            show_active, list_response, "production_goal"
        )


class DailyReportRelationViewSet(ModelViewSet):
    serializer_class = DailyReportRelationSerializer
    filterset_class = DailyReportRelationFilter
    permissions = None
    permission_classes = [IsAuthenticated, DailyReportRelationPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "active",
        "daily_report",
        "worker",
        "equipment",
        "vehicle",
        "signaling",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return DailyReportRelation.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="DailyReportRelation",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, DailyReportRelation.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    DailyReportRelation.objects.filter(
                        Q(multiple_daily_report__company_id=user_company)
                        | Q(daily_report__company_id=user_company)
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = DailyReportRelation.objects.filter(
                Q(multiple_daily_report__company__in=user_companies)
                | Q(daily_report__company__in=user_companies)
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


@method_decorator(ratelimit(key="user", rate="100/m", block=True), name="dispatch")
class DailyReportContractUsageViewSet(ListCacheMixin, ReadOnlyModelViewSet):
    serializer_class = DailyReportContractUsageSerializer
    filterset_class = DailyReportContractUsageFilter
    permissions = None
    permission_classes = [IsAuthenticated, DailyReportContractUsagePermissions]

    ordering = "uuid"
    ordering_fields = ["uuid", "worker", "equipment", "vehicle", "created_at"]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return DailyReportContractUsage.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="DailyReportContractUsage",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(
                    queryset, DailyReportContractUsage.objects.none()
                )
            if "all" in allowed_queryset:
                # OPTIMIZED: Usar campo company denormalizado ao invés de 3 subqueries
                base_contract_usages = DailyReportContractUsage.objects.filter(
                    company_id=user_company
                )

                queryset = join_queryset(
                    queryset,
                    base_contract_usages.filter(
                        (
                            (
                                Q(worker__multiple_daily_reports__isnull=True)
                                & Q(equipment__multiple_daily_reports__isnull=True)
                                & Q(vehicle__multiple_daily_reports__isnull=True)
                            )
                            | (
                                Q(worker__multiple_daily_reports__isnull=False)
                                & Q(
                                    worker__multiple_daily_reports__day_without_work=False
                                )
                                & Q(worker__worker_relations__active=True)
                            )
                            | (
                                Q(vehicle__multiple_daily_reports__isnull=False)
                                & Q(
                                    vehicle__multiple_daily_reports__day_without_work=False
                                )
                                & Q(vehicle__vehicle_relations__active=True)
                            )
                            | (
                                Q(equipment__multiple_daily_reports__isnull=False)
                                & Q(
                                    equipment__multiple_daily_reports__day_without_work=False
                                )
                                & Q(equipment__equipment_relations__active=True)
                            )
                        ),
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            # OPTIMIZED: Usar campo company_id denormalizado ao invés de 3 subqueries
            base_contract_usages = DailyReportContractUsage.objects.filter(
                company_id__in=user_companies
            )

            queryset = join_queryset(
                queryset,
                base_contract_usages.filter(
                    (
                        (
                            Q(worker__multiple_daily_reports__isnull=True)
                            & Q(equipment__multiple_daily_reports__isnull=True)
                            & Q(vehicle__multiple_daily_reports__isnull=True)
                        )
                        | (
                            Q(worker__multiple_daily_reports__isnull=False)
                            & Q(worker__multiple_daily_reports__day_without_work=False)
                            & Q(worker__worker_relations__active=True)
                        )
                        | (
                            Q(vehicle__multiple_daily_reports__isnull=False)
                            & Q(vehicle__multiple_daily_reports__day_without_work=False)
                            & Q(vehicle__vehicle_relations__active=True)
                        )
                        | (
                            Q(equipment__multiple_daily_reports__isnull=False)
                            & Q(
                                equipment__multiple_daily_reports__day_without_work=False
                            )
                            & Q(equipment__equipment_relations__active=True)
                        )
                    ),
                ),
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class DailyReportExportViewSet(ModelViewSet):
    serializer_class = DailyReportExportSerializer
    filterset_class = DailyReportExportFilter
    permissions = None
    permission_classes = [IsAuthenticated, DailyReportExportPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "created_at",
        "created_by",
        "daily_reports",
        "multiple_daily_reports",
        "done",
        "error",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return DailyReportExport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="DailyReportExport",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, DailyReportExport.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    DailyReportExport.objects.filter(
                        Q(daily_reports__company_id=user_company)
                        | Q(multiple_daily_reports__company_id=user_company)
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = DailyReportExport.objects.filter(
                Q(daily_reports__company__in=user_companies)
                | Q(multiple_daily_reports__company__in=user_companies)
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class MultipleDailyReportFileView(ModelViewSet):
    permission_classes = [IsAuthenticated, MultipleDailyReportFilePermissions]
    filterset_class = MultipleDailyReportFileFilter
    permissions = None
    ordering = "uuid"

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update", "create"]:
            return MultipleDailyReportFileObjectSerializer
        return MultipleDailyReportFileSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list or retrieve action: limit queryset
        if self.action in ["list", "retrieve"]:
            if "company" not in self.request.query_params:
                return MultipleDailyReportFile.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MultipleDailyReportFile",
                )
            allowed_queryset = self.permissions.get_allowed_queryset()

            if self.action == "list":
                if "none" in allowed_queryset:
                    queryset = join_queryset(
                        queryset, MultipleDailyReportFile.objects.none()
                    )
                if "self" in allowed_queryset:
                    queryset = join_queryset(
                        queryset,
                        MultipleDailyReportFile.objects.filter(
                            Q(created_by=self.request.user)
                            | Q(multiple_daily_report__created_by=self.request.user)
                        ),
                    )

                if "all" in allowed_queryset:
                    queryset = join_queryset(
                        queryset,
                        MultipleDailyReportFile.objects.filter(
                            multiple_daily_report__company__in=[user_company]
                        ),
                    )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MultipleDailyReportFile.objects.filter(
                multiple_daily_report__company__in=user_companies
            )
        queryset = self.get_serializer_class().setup_eager_loading(queryset.distinct())
        return queryset

    @action(methods=["get"], url_path="Check", detail=True)
    def check(self, request, pk=None):
        return check_endpoint(self.get_object())


class MultipleDailyReportSignatureView(ModelViewSet):
    permission_classes = [IsAuthenticated, MultipleDailyReportSignaturePermissions]
    filterset_class = MultipleDailyReportSignatureFilter
    permissions = None
    ordering = "uuid"

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update", "create"]:
            return MultipleDailyReportSignatureObjectSerializer
        return MultipleDailyReportSignatureSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list or retrieve action: limit queryset
        if self.action in ["list", "retrieve"]:
            if "company" not in self.request.query_params:
                return MultipleDailyReportSignature.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MultipleDailyReportSignature",
                )
            allowed_queryset = self.permissions.get_allowed_queryset()

            if self.action == "list":
                if "none" in allowed_queryset:
                    queryset = join_queryset(
                        queryset, MultipleDailyReportSignature.objects.none()
                    )
                if "self" in allowed_queryset:
                    queryset = join_queryset(
                        queryset,
                        MultipleDailyReportSignature.objects.filter(
                            Q(created_by=self.request.user)
                            | Q(multiple_daily_report__created_by=self.request.user)
                        ),
                    )

                if "all" in allowed_queryset:
                    queryset = join_queryset(
                        queryset,
                        MultipleDailyReportSignature.objects.filter(
                            multiple_daily_report__company__in=[user_company]
                        ),
                    )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MultipleDailyReportSignature.objects.filter(
                multiple_daily_report__company__in=user_companies
            )
        queryset = self.get_serializer_class().setup_eager_loading(queryset.distinct())
        return queryset

    @action(methods=["get"], url_path="Check", detail=True)
    def check(self, request, pk=None):
        return check_endpoint(self.get_object())


class RecalculateExtraHours(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, format=None):

        required_fields = ["mdr_uuid", "extra_hours"]
        data = request.data

        if not set(required_fields).issubset(data.keys()):
            return error_message(400, "Faltam parâmetros obrigatórios")

        mdr_uuid = data["mdr_uuid"]
        extra_hours_list = data["extra_hours"]

        if not isinstance(extra_hours_list, list):
            return error_message(400, "extra_hours deve ser uma lista")

        # Fetch MDR
        try:
            mdr = MultipleDailyReport.objects.prefetch_related(
                "company", "contract", "firm"
            ).get(uuid=mdr_uuid)
        except MultipleDailyReport.DoesNotExist:
            return error_message(404, "RDO não encontrado")

        # Fetch ContractPeriod for this firm + contract
        contract_period = (
            ContractPeriod.objects.filter(
                contract=mdr.contract,
                firms=mdr.firm,
            )
            .order_by("-created_at")
            .first()
        )

        if not contract_period:
            return error_message(
                404, "Período de contrato não encontrado para esta equipe/contrato"
            )

        is_worker = bool(data.get("is_worker", False))
        working_schedules = contract_period.working_schedules or []
        day_of_week = mdr.date.isoweekday()
        is_holiday = is_holiday_for_firm(mdr.company, mdr.firm_id, mdr.date)
        is_compensation = mdr.compensation
        results = []
        for index, item in enumerate(extra_hours_list):
            item = dict_to_casing(item, format_type="camelize")
            worker_result = calculate_extra_hours_worker(
                worked_periods_item=item,
                working_schedules=working_schedules,
                day_of_week=day_of_week,
                is_holiday=is_holiday,
                is_compensation=is_compensation,
            )

            if is_worker:
                calculated = worker_result
            else:
                total_extra = sum(
                    parse_time_to_minutes(worker_result[k]) or 0
                    for k in (
                        "extra_hours_50_day",
                        "extra_hours_50_night",
                        "extra_hours_100_day",
                        "extra_hours_100_night",
                    )
                )
                calculated = {
                    "extra_hours": format_minutes(total_extra),
                    "absence": worker_result["absence"],
                    "compensation": worker_result["compensation"],
                }

            calculated["index"] = index
            results.append(calculated)

        return Response(
            dict_to_casing(results, format_type="camelize"),
            status=status.HTTP_200_OK,
        )
