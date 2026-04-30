import json
import uuid
from datetime import datetime
from functools import reduce
from typing import List

import requests
import sentry_sdk
from django.conf import settings
from django.db.models import Prefetch, Q
from django.db.models.signals import post_init, pre_init
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.gzip import gzip_page
from fnc.mappings import get
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_json_api import serializers

from apps.approval_flows.models import ApprovalTransition
from apps.companies.filters import (
    AccessRequestFilter,
    CompanyFilter,
    CompanyUsageFilter,
    EntityFilter,
    FirmFilter,
    InspectorInFirmFilter,
    SingleCompanyUsageFilter,
    SubCompanyFilter,
    UserInCompanyFilter,
    UserInFirmFilter,
    UserUsageFilter,
)
from apps.daily_reports.models import MultipleDailyReport
from apps.service_orders.models import ServiceOrder
from apps.users.models import User
from apps.work_plans.asynchronous import (
    async_bulk_archive,
    async_recalculate_job_progress,
)
from helpers.apps.daily_reports import (
    get_exporter_extra_columns,
    get_exporter_extra_columns_parsed_infos,
    get_fields_to_hide_reporting_location,
    get_reporting_static_columns,
    remove_fields_to_hide_reporting_location,
)
from helpers.apps.job import get_jobs_to_archive
from helpers.apps.json_logic import apply_json_logic
from helpers.json_parser import JSONParserWithUnformattedKeys
from helpers.mixins import ListCacheMixin, RetrieveCacheMixin
from helpers.permissions import PermissionManager, join_queryset
from helpers.signals import DisableSignals
from helpers.strings import (
    dict_to_casing,
    get_obj_from_path,
    keys_to_camel_case,
    keys_to_snake_case,
    to_flatten_str,
    to_snake_case,
)

from .const.metadata_fields import METADATA_FIELD_TO_TYPE
from .models import (
    AccessRequest,
    Company,
    CompanyGroup,
    CompanyUsage,
    Entity,
    Firm,
    InspectorInFirm,
    SingleCompanyUsage,
    SubCompany,
    UserInCompany,
    UserInFirm,
    UserUsage,
)
from .notifications import send_approval_step_email
from .permissions import (
    AccessRequestPermissions,
    CompanyPermissions,
    CompanyUsagePermissions,
    EntityPermissions,
    FirmPermissions,
    InspectorInFirmPermissions,
    SingleCompanyUsagePermissions,
    SubCompanyPermissions,
    UserInCompanyPermissions,
    UserInFirmPermissions,
    UserUsagePermissions,
)
from .serializers import (
    AccessRequestObjectSerializer,
    AccessRequestSerializer,
    CompanyGroupSerializer,
    CompanySerializer,
    CompanyUsageSerializer,
    EntitySerializer,
    FirmSerializer,
    InspectorInFirmSerializer,
    PermissionsFirmSerializer,
    PermissionsSubCompanySerializer,
    ShareableUserInCompanySerializer,
    SingleCompanyUsageSerializer,
    SubCompanySerializer,
    UserInCompanySerializer,
    UserInFirmSerializer,
    UserUsageSerializer,
)


class CompanyView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated, CompanyPermissions]
    parser_classes = [JSONParserWithUnformattedKeys]
    parser_keys_to_keep = ["custom_options"]
    filterset_class = CompanyFilter
    permissions = None
    ordering = "uuid"

    @method_decorator(gzip_page)
    def list(self, request, *args, **kwargs):
        with DisableSignals(disabled_signals=[pre_init, post_init]):
            return super().list(request, *args, **kwargs)

    def get_queryset(self):
        uics = UserInCompany.objects.filter(
            user=self.request.user, permissions__is_inactive=False, is_active=True
        )
        queryset = Company.objects.filter(userincompany__in=uics).order_by("name")
        return self.get_serializer_class().setup_eager_loading(queryset)

    def deny_if_not_allowed(self, user, company_ids, permission):
        permissions = PermissionManager(company_ids, user, model="Company")
        if not permissions.has_permission(permission):
            raise PermissionDenied()

    @action(methods=["POST"], url_path="AddFieldOption", detail=True)
    def add_field_option(self, request, pk=None):
        company = self.get_object()

        # Check if user has permission to change custom_options
        custom_options = company.custom_options

        # Parse input
        input_data = json.loads(request.body)
        if "data" in input_data:
            input_data = input_data["data"]
        else:
            raise serializers.ValidationError(
                "kartado.error.company.data_key_not_found_on_body"
            )
        input_data = keys_to_camel_case(input_data)

        # Validate fields
        required_fields = ["resource", "fieldName", "optionName"]
        for field in required_fields:
            if field not in input_data:
                raise serializers.ValidationError(
                    "kartado.error.company.{}_is_required".format(to_snake_case(field))
                )

        # Extract and validate data
        flat_resource_name = to_flatten_str(input_data["resource"])
        flat_field_name = to_flatten_str(input_data["fieldName"])
        option_name = input_data["optionName"]

        if not option_name:
            raise serializers.ValidationError(
                "kartado.error.company.option_name_cant_be_an_empty_string"
            )

        resource = get_obj_from_path(custom_options, flat_resource_name)
        if not resource:
            raise NotFound()

        possible_field_path = "fields__{}".format(flat_field_name)
        possible_options_path = possible_field_path + "__selectoptions__options"
        field_obj = get_obj_from_path(resource, possible_field_path)
        field_options = get_obj_from_path(resource, possible_options_path)

        if not field_obj:
            raise serializers.ValidationError(
                "kartado.error.company.field_does_not_exist_for_this_resource"
            )

        if not field_options:
            raise serializers.ValidationError(
                "kartado.error.company.field_does_not_have_select_options"
            )

        # Test if an option with that name already exists
        duplicates = [
            option for option in field_options if option["name"] == option_name
        ]
        if duplicates:
            raise serializers.ValidationError(
                "kartado.error.company.option_name_already_exists_for_this_field"
            )

        # Get option with the highest value in field_options
        if field_options:
            last_option = reduce(
                lambda item1, item2: (
                    item1 if int(item1["value"]) > int(item2["value"]) else item2
                ),
                field_options,
            )
            highest_value = int(last_option["value"])
            new_option_value = highest_value + 1
        else:
            new_option_value = 1

        # Build new option
        new_option = {
            "name": input_data["optionName"],
            "value": str(new_option_value),
        }

        # Add new option to custom_options
        field_options.append(new_option)
        company.custom_options = custom_options
        company.save()

        response = {"data": {"result": "OK"}}
        return Response(response)

    @action(methods=["GET", "PATCH"], url_path="CustomOptionsResource", detail=True)
    def custom_options_resource(self, request, pk=None):
        company = self.get_object()

        custom_options = company.custom_options or {}

        # Handle different methods
        if request.method == "GET":
            if "resource" not in request.query_params:
                raise serializers.ValidationError(
                    "kartado.error.company.resource_query_param_is_required"
                )

            # Extract resource
            resource_name = request.query_params["resource"]
            flat_resource_name = to_flatten_str(resource_name)

            # dailyReportHolidays: return empty structure without saving if not exists
            if flat_resource_name == "dailyreportholidays":
                if "dailyReportHolidays" not in custom_options:
                    return Response({"holidays": []})

            resource = get_obj_from_path(custom_options, flat_resource_name)
            resource_fields = get_obj_from_path(resource, "fields")
            if not resource:
                raise NotFound()
        else:
            # Parse input
            input_data = json.loads(request.body)
            if "data" in input_data:
                input_data = input_data["data"]
            else:
                raise serializers.ValidationError(
                    "kartado.error.company.data_key_not_found_on_body"
                )

            # Validate fields
            required_fields = ["resource", "fields"]
            for field in required_fields:
                if field not in input_data:
                    raise serializers.ValidationError(
                        "kartado.error.company.{}_is_required".format(
                            to_snake_case(field)
                        )
                    )

            input_resource_fields = keys_to_camel_case(input_data["fields"])

            # Extract resource
            resource_name = input_data["resource"]
            flat_resource_name = to_flatten_str(resource_name)

            # dailyReportHolidays: handle special case
            if flat_resource_name == "dailyreportholidays":
                holidays_list = input_resource_fields.get("holidays", [])
                # If holidays is empty, remove the key entirely
                if not holidays_list:
                    if "dailyReportHolidays" in custom_options:
                        del custom_options["dailyReportHolidays"]
                    company.custom_options = custom_options
                    company.save()
                    return Response({"holidays": []})
                # Otherwise create structure if not exists
                if "dailyReportHolidays" not in custom_options:
                    custom_options["dailyReportHolidays"] = {"fields": {}}

            resource = get_obj_from_path(custom_options, flat_resource_name)
            if not resource:
                raise NotFound()
            resource_fields = get_obj_from_path(resource, "fields")
            if resource_fields is None:
                resource["fields"] = {}
                resource_fields = resource["fields"]

            # Add or update fields
            for field, field_data in input_resource_fields.items():
                resource_fields[field] = (
                    dict_to_casing(field_data, format_type="camelize")
                    if type(field_data) is dict
                    else field_data
                )

            # Save changes
            company.custom_options = custom_options
            company.save()

        return Response(dict_to_casing(resource_fields, format_type="camelize"))

    @action(methods=["GET", "PATCH"], url_path="ChangeMetadata", detail=True)
    def change_metadata(self, request, pk=None):
        """
        Change metadata based on the user input.
        """

        company: Company = self.get_object()

        if request.method != "GET":
            # Parse input
            input_data = json.loads(request.body).get("data", None)
            if input_data is None:
                raise serializers.ValidationError(
                    "kartado.error.company.data_key_not_found_on_body"
                )

            # Validate field name
            valid_provided_fields: List[str] = [
                field for field in METADATA_FIELD_TO_TYPE.keys() if field in input_data
            ]
            if len(valid_provided_fields) == 0:
                raise serializers.ValidationError(
                    "kartado.error.company.provide_at_least_one_valid_metadata_field_to_be_changed"
                )

            # Flag to trigger async job progress recalculation after save
            should_recalculate_job_progress = False

            for valid_field_name in valid_provided_fields:
                # NOTE: field_data will only be None if the user explicitly provides the value None
                field_data = input_data.get(valid_field_name)
                expected_field_type = METADATA_FIELD_TO_TYPE[valid_field_name]

                # Validate field data type
                if field_data and type(field_data) is not expected_field_type:
                    expected_type_name = expected_field_type.__name__
                    raise serializers.ValidationError(
                        f"kartado.error.company.{valid_field_name}_needs_to_be_a_{expected_type_name}"
                    )

                # Set value for the current Company instance
                # WARN: This will only be saved to the database further down on the .save() method call
                if valid_field_name == "altimetry_enable":
                    companies_permissions = (
                        self.request.user.get_companies_permissions()
                    )
                    user_permission = companies_permissions.get(company.name, None)

                    if user_permission is not None:
                        for user_permission, permission in user_permission.items():
                            permission = keys_to_snake_case(permission)
                            company_permission = permission.get("company", None)
                            if company_permission:
                                company_permission = keys_to_snake_case(
                                    company_permission
                                )
                                if company_permission.get("can_enable_altimetry", None):
                                    company.metadata[valid_field_name] = field_data
                                    break

                elif valid_field_name == "auto_archive_completed_jobs":
                    company.metadata[valid_field_name] = field_data

                    if field_data is True:
                        job_ids_to_archive = get_jobs_to_archive(company)
                        if job_ids_to_archive:
                            archive_data = {
                                "archiveJobs": [
                                    str(job_id) for job_id in job_ids_to_archive
                                ],
                                "unarchiveJobs": [],
                                "removeUnexecutedReportings": False,
                            }
                            async_bulk_archive(
                                archive_data,
                                str(company.pk),
                                str(self.request.user.pk),
                            )

                elif valid_field_name == "consider_approval_for_job_progress":
                    company.metadata[valid_field_name] = field_data
                    # Flag to trigger async recalculation after save
                    should_recalculate_job_progress = field_data is True

                else:
                    company.metadata[valid_field_name] = field_data
            # NOTE: Operation is atomic and won't apply field changes partially
            company.save()

            # When enabling consider_approval_for_job_progress, recalculate progress
            # for all jobs at 100% to ensure they consider approval status.
            # This must happen AFTER company.save() so the async function can read
            # the updated metadata from the database.
            if should_recalculate_job_progress:
                async_recalculate_job_progress(str(company.pk))

        return Response(
            {
                field_name: company.metadata.get(field_name, None)
                for field_name in METADATA_FIELD_TO_TYPE.keys()
            }
        )

    @action(
        methods=["GET"],
        url_path="ReportingSectionFieldsIndividualRDOExport",
        detail=True,
    )
    def get_reporting_section_fields(self, request, pk=None):
        company = self.get_object()
        response = {"fields": []}
        hide_reporting_location = company.metadata.get("hide_reporting_location", False)
        static_fields = get_reporting_static_columns()
        extra_fields = get_exporter_extra_columns(company)
        extra_fields = get_exporter_extra_columns_parsed_infos(
            extra_fields, skip_array_fields=True
        )
        if hide_reporting_location is True:
            fields_to_hide = get_fields_to_hide_reporting_location()
            static_fields = remove_fields_to_hide_reporting_location(
                fields_to_hide, static_fields
            )
        response_fields = {**static_fields, **extra_fields}
        for field_name, translated_field_name in response_fields.items():
            response["fields"].append(
                {"field": field_name, "name": translated_field_name}
            )
        response.update(
            {"defaultFields": ["occurrence_kind", "occurrence_type", "status"]}
        )
        return Response(data=response)


class SubCompanyView(ListCacheMixin, RetrieveCacheMixin, viewsets.ModelViewSet):
    serializer_class = SubCompanySerializer
    permission_classes = [IsAuthenticated, SubCompanyPermissions]
    filterset_class = SubCompanyFilter
    permissions = None
    ordering = "uuid"

    ordering_fields = [
        "uuid",
        "subcompany_type",
        "company",
        "name",
        "cnpj",
        "responsible",
        "responsible__first_name",
        "contract",
        "contract_start_date",
        "contract_end_date",
        "office",
        "construction_name",
        "hired_by_subcompany",
        "active",
    ]

    def has_necessary_query_params(self, query_params: list):
        # check necessary params
        return any(
            [
                self.request.query_params.get(query_param) != "false"
                for query_param in query_params
            ]
        )

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return SubCompany.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="SubCompany",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            NECESSARY_QUERY_PARAMS = ["can_rdo_view", "can_rdo_create"]
            if self.has_necessary_query_params(NECESSARY_QUERY_PARAMS):
                model_permissions_to_verify = "MultipleDailyReport"
                if (
                    self.permissions.get_specific_model_permision(
                        model_permissions_to_verify, "can_view_all_firms"
                    )
                    is True
                    or self.permissions.get_specific_model_permision(
                        model_permissions_to_verify, "can_create_and_edit_all_firms"
                    )
                    is True
                ):
                    allowed_queryset = ["all"]

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, SubCompany.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    SubCompany.objects.filter(
                        Q(company_id=user_company)
                        & (
                            Q(responsible=self.request.user)
                            | Q(subcompany_firms__users=self.request.user)
                            | Q(subcompany_firms__inspectors=self.request.user)
                            | Q(subcompany_firms__manager=self.request.user)
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, SubCompany.objects.filter(company_id=user_company)
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = SubCompany.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if (
            self.request.method == "GET"
            and self.request.query_params.get("perms_on_rdo") == "true"
        ):
            multiple_daily_report_permissions = self.permissions.get_model_permission(
                "MultipleDailyReport"
            )
            can_view = (
                multiple_daily_report_permissions.get("can_view")[0]
                if multiple_daily_report_permissions.get("can_view") is not None
                else False
            )
            can_view_all_firms = (
                multiple_daily_report_permissions.get("can_view_all_firms")[0]
                if multiple_daily_report_permissions.get("can_view_all_firms")
                is not None
                else False
            )
            if bool(can_view and can_view_all_firms):
                context.update(
                    {
                        "can_view": True,
                    }
                )
            else:
                context.update(
                    {
                        "can_view": "verify_firm",
                    }
                )
            can_create = (
                multiple_daily_report_permissions.get("can_create")[0]
                if multiple_daily_report_permissions.get("can_create") is not None
                else False
            )
            can_create_and_edit_all_firms = (
                multiple_daily_report_permissions.get("can_create_and_edit_all_firms")[
                    0
                ]
                if multiple_daily_report_permissions.get(
                    "can_create_and_edit_all_firms"
                )
                is not None
                else False
            )
            if bool(can_create and can_create_and_edit_all_firms):
                context.update(
                    {
                        "can_create": True,
                    }
                )
            else:
                context.update(
                    {
                        "can_create": "verify_firm",
                    }
                )
            return context
        return context

    def get_serializer_class(self):
        if (
            self.request.method == "GET"
            and self.request.query_params.get("perms_on_rdo") == "true"
        ):
            return PermissionsSubCompanySerializer
        return self.serializer_class


def service_order_queryset(request):
    if "company" not in request.query_params:
        return ServiceOrder.objects.none()
    company = uuid.UUID(request.query_params["company"])
    return ServiceOrder.objects.filter(company=company)


class FirmView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = FirmSerializer
    permission_classes = [IsAuthenticated, FirmPermissions]
    filterset_class = FirmFilter
    permissions = None
    ordering = "uuid"

    ordering_fields = [
        "uuid",
        "manager__first_name",
        "is_company_team",
        "cnpj",
        "name",
        "active",
        "subcompany__name",
        "members_amount",
    ]

    def has_necessary_query_params(self, query_params: list):
        # check necessary params
        return any(
            [
                self.request.query_params.get(query_param) != "false"
                for query_param in query_params
            ]
        )

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return Firm.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="Firm",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()
            all_permission = self.permissions.all_permissions

            # Filter queryset if is creating/editing a operational record
            is_available_operational = self.request.query_params.get(
                "is_available_operational", ""
            )
            if is_available_operational:
                can_create_operational = any(
                    get(
                        "occurrence_record.can_create_operational",
                        all_permission,
                        default=[],
                    )
                )
                if can_create_operational:
                    allowed_queryset = ["all"]

            # Filter queryset if is creating/editing a monitoring record
            is_available_monitoring = self.request.query_params.get(
                "is_available_monitoring", ""
            )
            if is_available_monitoring:
                can_create_monitoring = any(
                    get(
                        "occurrence_record.can_create_monitoring",
                        all_permission,
                        default=[],
                    )
                )
                if can_create_monitoring:
                    allowed_queryset = ["all"]

            NECESSARY_QUERY_PARAMS = ["can_rdo_view", "can_rdo_create"]
            if self.has_necessary_query_params(NECESSARY_QUERY_PARAMS):
                model_permissions_to_verify = "MultipleDailyReport"
                if (
                    self.permissions.get_specific_model_permision(
                        model_permissions_to_verify, "can_view_all_firms"
                    )
                    is True
                    or self.permissions.get_specific_model_permision(
                        model_permissions_to_verify, "can_create_and_edit_all_firms"
                    )
                    is True
                ):
                    allowed_queryset = ["all"]

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, Firm.objects.none())
            if "self" in allowed_queryset or "self_and_created" in allowed_queryset:
                now = timezone.now()
                user_firms = Firm.objects.filter(users__in=[self.request.user])
                if "self" in allowed_queryset:
                    if is_available_operational:
                        queryset = join_queryset(
                            queryset,
                            Firm.objects.filter(
                                Q(uuid__in=user_firms)
                                & Q(
                                    operational_cycles_creators__operational_control_id=is_available_operational
                                )
                                & (
                                    Q(firm_op_controls__responsible=self.request.user)
                                    | (
                                        Q(
                                            operational_cycles_creators__start_date__date__lte=now.date()
                                        )
                                        & Q(
                                            operational_cycles_creators__end_date__date__gte=now.date()
                                        )
                                    )
                                )
                            ),
                        )
                    elif is_available_monitoring:
                        queryset = join_queryset(
                            queryset,
                            Firm.objects.filter(
                                uuid__in=user_firms,
                                cycles_executers__start_date__date__lte=now.date(),
                                cycles_executers__end_date__date__gte=now.date(),
                                cycles_executers__monitoring_plan_id=is_available_monitoring,
                            ),
                        )
                    else:
                        queryset = join_queryset(
                            queryset,
                            Firm.objects.filter(
                                Q(uuid__in=user_firms)
                                | Q(firm_jobs__watcher_users=self.request.user)
                                | Q(firm_jobs__watcher_firms__in=user_firms)
                                | Q(
                                    firm_jobs__watcher_subcompanies__subcompany_firms__in=user_firms
                                )
                            ),
                        )
                if "self_and_created" in allowed_queryset:
                    # Get users related to the request user's firms
                    related_users = User.objects.filter(
                        user_firms__in=user_firms
                    ).distinct()

                    queryset = join_queryset(
                        queryset,
                        Firm.objects.filter(
                            Q(uuid__in=user_firms)
                            | Q(firm_jobs__watcher_users=self.request.user)
                            | Q(firm_jobs__watcher_firms__in=user_firms)
                            | Q(created_by__in=related_users)
                            | Q(
                                firm_jobs__watcher_subcompanies__subcompany_firms__in=user_firms
                            )
                        ),
                    )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, Firm.objects.filter(company_id=user_company)
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = Firm.objects.filter(company__in=user_companies)

        queryset = self.get_serializer_class().setup_eager_loading(queryset.distinct())

        # Otimização: Prefetch MultipleDailyReport quando has_rdo_on_date estiver presente
        # para evitar N+1 queries em get_rdo_found_on_date
        has_rdo_on_date = self.request.query_params.get("has_rdo_on_date")
        if has_rdo_on_date:
            try:
                date = datetime.strptime(has_rdo_on_date, "%Y-%m-%d").date()
                user = self.request.user

                # Prefetch apenas o MultipleDailyReport que corresponde à data e usuário
                queryset = queryset.prefetch_related(
                    Prefetch(
                        "firm_multiple_daily_report",
                        queryset=MultipleDailyReport.objects.filter(
                            date=date, created_by=user
                        ),
                        to_attr="prefetched_rdo_on_date",
                    )
                )
            except (ValueError, TypeError) as e:
                # Se a data for inválida, não adiciona o prefetch
                # O erro será tratado no serializer
                sentry_sdk.capture_exception(e)

        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if (
            self.request.method == "GET"
            and self.request.query_params.get("perms_on_rdo") == "true"
        ):
            multiple_daily_report_permissions = self.permissions.get_model_permission(
                "MultipleDailyReport"
            )
            can_view = (
                multiple_daily_report_permissions.get("can_view")[0]
                if multiple_daily_report_permissions.get("can_view") is not None
                else False
            )
            can_view_all_firms = (
                multiple_daily_report_permissions.get("can_view_all_firms")[0]
                if multiple_daily_report_permissions.get("can_view_all_firms")
                is not None
                else False
            )
            if bool(can_view and can_view_all_firms):
                context.update(
                    {
                        "can_view": True,
                    }
                )
            elif not can_view:
                context.update(
                    {
                        "can_view": False,
                    }
                )
            else:
                context.update(
                    {
                        "can_view": "verify_firm",
                    }
                )
            can_create = (
                multiple_daily_report_permissions.get("can_create")[0]
                if multiple_daily_report_permissions.get("can_create") is not None
                else False
            )
            can_create_and_edit_all_firms = (
                multiple_daily_report_permissions.get("can_create_and_edit_all_firms")[
                    0
                ]
                if multiple_daily_report_permissions.get(
                    "can_create_and_edit_all_firms"
                )
                is not None
                else False
            )
            if bool(can_create and can_create_and_edit_all_firms):
                context.update(
                    {
                        "can_create": True,
                    }
                )
            elif not can_create:
                context.update(
                    {
                        "can_create": False,
                    }
                )
            else:
                context.update(
                    {
                        "can_create": "verify_firm",
                    }
                )
            return context
        return context

    def get_serializer_class(self):
        if (
            self.request.method == "GET"
            and self.request.query_params.get("perms_on_rdo") == "true"
        ):
            return PermissionsFirmSerializer
        return self.serializer_class

    @action(methods=["PATCH"], url_path="BatchAddJudiciary", detail=False)
    def batch_add_judiciary(self, request, pk=None):
        """
        Change the judiciary_firms field to True of many instances at the same time
        """

        try:
            company = Company.objects.get(pk=request.query_params.get("company"))
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.companies.please_provide_a_valid_company_param"
            )

        # Validate input
        input_data = dict_to_casing(json.loads(request.body), format_type="underscore")
        if "data" not in input_data or "judiciary_firms" not in input_data["data"]:
            raise serializers.ValidationError(
                "kartado.error.companies.invalid_body_structure_was_provided"
            )
        else:
            judiciary_firms_ids = input_data["data"]["judiciary_firms"]

        # Update the provided instances to is_judiciary=True if not already that
        Firm.objects.filter(
            company=company, is_judiciary=False, pk__in=judiciary_firms_ids
        ).update(is_judiciary=True)

        # Update the instances to is_judiciary=False if not on input list
        Firm.objects.filter(company=company, is_judiciary=True).exclude(
            pk__in=judiciary_firms_ids
        ).update(is_judiciary=False)

        # Build response with all is_judiciary=True Firm instances
        full_judiciary_firms_ids = Firm.objects.filter(
            company=company, is_judiciary=True
        ).values_list("pk", flat=True)
        response_dict = {
            "data": {
                "judiciary_firms": [
                    str(firm_id) for firm_id in full_judiciary_firms_ids
                ]
            }
        }
        response_dict = dict_to_casing(response_dict)

        return Response(response_dict)


class UserInCompanyView(viewsets.ModelViewSet):
    serializer_class = UserInCompanySerializer
    permission_classes = [IsAuthenticated, UserInCompanyPermissions]
    filterset_class = UserInCompanyFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = UserInCompany.objects.none()

        memberships = self.request.user.companies_membership.all()

        for membership in memberships:
            queryset |= UserInCompany.objects.filter(
                company_id=membership.company_id, user=self.request.user
            )

        queryset = queryset.distinct()

        return self.get_serializer_class().setup_eager_loading(queryset)


class ShareableUserInCompanyView(viewsets.ReadOnlyModelViewSet):
    serializer_class = ShareableUserInCompanySerializer
    permission_classes = [IsAuthenticated]
    filterset_class = UserInCompanyFilter
    ordering = "uuid"
    queryset = UserInCompany.objects.all()


class UserInFirmView(viewsets.ModelViewSet):
    serializer_class = UserInFirmSerializer
    permission_classes = [IsAuthenticated, UserInFirmPermissions]
    filterset_class = UserInFirmFilter
    permissions = None

    ordering_fields = ["uuid", "user__first_name", "user__last_name"]
    ordering = "uuid"

    def get_queryset(self):
        queryset = None
        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return UserInFirm.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="UserInFirm",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, UserInFirm.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    UserInFirm.objects.filter(firm__company_id=user_company),
                )
            if "firm" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    UserInFirm.objects.filter(
                        firm__company_id=user_company,
                        firm__users=self.request.user,
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    UserInFirm.objects.filter(firm__company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = UserInFirm.objects.filter(firm__company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class InspectorInFirmView(viewsets.ModelViewSet):
    serializer_class = InspectorInFirmSerializer
    permission_classes = [IsAuthenticated, InspectorInFirmPermissions]
    filterset_class = InspectorInFirmFilter
    permissions = None

    ordering_fields = ["uuid", "user__first_name", "user__last_name"]
    ordering = "uuid"

    def get_queryset(self):
        queryset = None
        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return InspectorInFirm.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="InspectorInFirm",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, InspectorInFirm.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    InspectorInFirm.objects.filter(firm__company_id=user_company),
                )
            if "firm" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    InspectorInFirm.objects.filter(
                        firm__company_id=user_company,
                        firm__users=self.request.user,
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    InspectorInFirm.objects.filter(firm__company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = InspectorInFirm.objects.filter(firm__company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class CompanyGroupView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = CompanyGroupSerializer
    permission_classes = [IsAuthenticated]
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        if "company" not in self.request.query_params:
            return CompanyGroup.objects.none()

        company = uuid.UUID(self.request.query_params["company"])
        queryset = CompanyGroup.objects.filter(group_companies=company)

        return self.get_serializer_class().setup_eager_loading(queryset)


def get_access_request_queryset(action, request, permissions):
    queryset = None
    if action == "list":
        if "company" not in request.query_params:
            return AccessRequest.objects.none()
        user_company = uuid.UUID(request.query_params["company"])
        if not permissions:
            permissions = PermissionManager(
                user=request.user,
                company_ids=user_company,
                model="AccessRequest",
            )
        allowed_queryset = permissions.get_allowed_queryset()
        if "none" in allowed_queryset:
            queryset = join_queryset(queryset, AccessRequest.objects.none())
        if "self" in allowed_queryset:
            queryset = join_queryset(
                queryset, AccessRequest.objects.filter(created_by=request.user)
            )
        if "all" in allowed_queryset:
            user_companies = request.user.companies.all()
            queryset = join_queryset(
                queryset,
                AccessRequest.objects.filter(
                    Q(company__in=user_companies) | Q(companies__in=user_companies)
                ),
            )
    # If queryset isn't set by any means above
    if queryset is None:
        if request.user.is_supervisor:
            queryset = AccessRequest.objects.filter(
                company__company_group=request.user.company_group
            )
        else:
            user_companies = request.user.companies.all()
            queryset = AccessRequest.objects.filter(
                Q(company__in=user_companies) | Q(companies__in=user_companies)
            )
    return queryset


class AccessRequestView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccessRequestPermissions]
    filterset_class = AccessRequestFilter
    authentication_types = ["approvalOnly", "all"]
    permissions = None

    ordering_fields = [
        "uuid",
        "user__is_internal",
        "user__first_name",
        "user__email",
        "permissions__name",
        "company__name",
        "approval_step__name",
        "created_at",
    ]
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_serializer_class(self):
        if self.action in ["retrieve"]:
            return AccessRequestObjectSerializer
        return AccessRequestSerializer

    def get_queryset(self):
        queryset = get_access_request_queryset(
            self.action, self.request, self.permissions
        )
        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["POST"], url_path="Approval", detail=True)
    def approval(self, request, pk=None):
        # Get all the ApprovalTransitions related to the current ApprovalStep
        access_request = self.get_object()
        transitions = ApprovalTransition.objects.filter(
            origin=access_request.approval_step
        )

        # Check if the condition from any ApprovalTransition was met
        # If the condition was met, execute the ApprovalStep change
        data = {"request": request.data, "source": access_request}

        for transition in transitions:
            if apply_json_logic(transition.condition, data):
                access_request.approval_step = transition.destination

                send_approval_step_email(transition.destination, access_request)

                for key, callback in transition.callback.items():
                    if key == "change_fields":
                        for field in callback:
                            try:
                                setattr(
                                    access_request,
                                    field["name"],
                                    field["value"],
                                )
                            except Exception as e:
                                print("Exception setting model fields", e)

                    elif key == "create_user_in_company" and callback is True:
                        if not access_request.permissions:
                            return Response(
                                data=[
                                    {
                                        "detail": "Nenhum nível de permissão foi especificado.",
                                        "source": {"pointer": "/data"},
                                        "status": status.HTTP_400_BAD_REQUEST,
                                    }
                                ],
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                        is_clustered_access_request = get_obj_from_path(
                            access_request.company.metadata,
                            "is_clustered_access_request",
                            default_return=False,
                        )
                        if is_clustered_access_request:
                            for company in access_request.companies.all():
                                if UserInCompany.objects.filter(
                                    user=access_request.user,
                                    company=access_request.company,
                                ).exists():
                                    uic = UserInCompany.objects.get(
                                        user=access_request.user,
                                        company=access_request.company,
                                    )
                                    uic.permissions = access_request.permissions
                                    uic.expiration_date = (
                                        access_request.expiration_date
                                        if uic.is_active
                                        else None
                                    )
                                    uic.save()
                                else:
                                    UserInCompany.objects.create(
                                        user=access_request.user,
                                        company=access_request.company,
                                        permissions=access_request.permissions,
                                        expiration_date=access_request.expiration_date,
                                    )
                        else:
                            if UserInCompany.objects.filter(
                                user=access_request.user,
                                company=access_request.company,
                            ).exists():
                                uic = UserInCompany.objects.get(
                                    user=access_request.user,
                                    company=access_request.company,
                                )
                                uic.permissions = access_request.permissions
                                uic.expiration_date = (
                                    access_request.expiration_date
                                    if uic.is_active
                                    else None
                                )
                                uic.save()
                            else:
                                UserInCompany.objects.create(
                                    user=access_request.user,
                                    company=access_request.company,
                                    permissions=access_request.permissions,
                                    expiration_date=access_request.expiration_date,
                                )

                if "source" in request.data and request.data["source"] == "email":
                    access_request._change_reason = "E-mail / Link"
                else:
                    access_request._change_reason = "Interface Web"

                access_request.save()

                return Response({"data": {"status": "OK"}})

        return Response(
            data=[
                {
                    "detail": "Erro! Essa ação não é válida para esse estágio de aprovação, ou essa solicitação já foi aprovada anteriormente",
                    "source": {"pointer": "/data"},
                    "status": status.HTTP_400_BAD_REQUEST,
                }
            ],
            status=status.HTTP_400_BAD_REQUEST,
        )


class AccessRequestApprovalView(APIView):
    authentication_types = ["approvalOnly"]

    def get(self, request, format=None):
        # Get credentials
        fields = ["name", "access", "tk"]

        if not set(fields).issubset(request.query_params.keys()):
            raise serializers.ValidationError("Faltam credenciais.")

        access_id = request.query_params["access"]
        name = request.query_params["name"]
        token = request.query_params["tk"]
        base_url = request.query_params.get("base", settings.BACKEND_URL)

        # Post to approval endpoint
        url = "{}/AccessRequest/{}/Approval/".format(base_url, access_id)

        data = {
            "data": {
                "type": "AccessRequest",
                "attributes": {"action": name, "source": "email"},
                "relationships": {},
            }
        }
        headers = {
            "Authorization": "JWT " + token,
            "Content-Type": "application/vnd.api+json",
            "X-ORIGINAL-HEADERS": json.dumps(
                {
                    "remote_ip": getattr(request, "META", {}).get("REMOTE_ADDR", ""),
                    "user_agent": getattr(request, "META", {}).get(
                        "HTTP_USER_AGENT", ""
                    ),
                }
            ),
        }

        approval_post = requests.post(url, data=json.dumps(data), headers=headers)

        # Return Template response
        if approval_post.status_code == 200:
            context = {"text": "Ação executada com sucesso"}
        else:
            try:
                error_message = approval_post.json()["errors"][0]["detail"]
            except Exception:
                error_message = "Erro na Solicitação"
            context = {"text": error_message}

        return render(request, "companies/email/approval.html", context)


class EntityView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = EntitySerializer
    permission_classes = [IsAuthenticated, EntityPermissions]
    filterset_class = EntityFilter
    permissions = None

    ordering_fields = [
        "uuid",
        "name",
        "company__name",
        "approver_firm__name",
        "address",
    ]
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return Entity.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="Entity",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, Entity.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, Entity.objects.filter(company_id=user_company)
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = Entity.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class CompanyUsageView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = CompanyUsageSerializer
    filterset_class = CompanyUsageFilter
    permissions = None
    permission_classes = [IsAuthenticated, CompanyUsagePermissions]

    ordering_fields = [
        "uuid",
        "plan_name",
        "date",
        "cnpj",
        "user_count",
        "created_at",
        "updated_at",
    ]
    ordering = "-date"

    def get_queryset(self):
        queryset = None

        if self.action == "list":
            if "company" not in self.request.query_params:
                return CompanyUsage.objects.none()
            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="CompanyUsage",
                )
            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, CompanyUsage.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, CompanyUsage.objects.filter(companies=user_company)
                )

        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = CompanyUsage.objects.filter(companies__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class UserUsageView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = UserUsageSerializer
    filterset_class = UserUsageFilter
    permissions = None
    permission_classes = [IsAuthenticated, UserUsagePermissions]

    ordering_fields = [
        "uuid",
        "is_counted",
        "full_name",
        "email",
        "username",
        "usage_date",
        "created_at",
        "updated_at",
    ]
    ordering = ["-is_counted", "full_name"]

    def get_queryset(self):
        queryset = None

        if self.action == "list":
            if "company" not in self.request.query_params:
                return UserUsage.objects.none()
            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="UserUsage",
                )
            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, UserUsage.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    UserUsage.objects.filter(company_usage__companies=user_company),
                )

        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = UserUsage.objects.filter(
                company_usage__companies__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class SingleCompanyUsageView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = SingleCompanyUsageSerializer
    filterset_class = SingleCompanyUsageFilter
    permissions = None
    permission_classes = [IsAuthenticated, SingleCompanyUsagePermissions]

    ordering_fields = ["user_count", "company__name", "created_at", "updated_at"]
    ordering = "-user_count"

    def get_queryset(self):
        if self.action == "list":
            if "company_usage" not in self.request.query_params:
                return SingleCompanyUsage.objects.none()

            company_usage_id = uuid.UUID(self.request.query_params["company_usage"])

            if not self.permissions:
                try:
                    company_usage = CompanyUsage.objects.get(pk=company_usage_id)
                    company_id = company_usage.company_id
                except CompanyUsage.DoesNotExist:
                    return SingleCompanyUsage.objects.none()

                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=company_id,
                    model="CompanyUsage",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                return SingleCompanyUsage.objects.none()
            if "all" in allowed_queryset:
                return self.get_serializer_class().setup_eager_loading(
                    SingleCompanyUsage.objects.filter(
                        company_usage_id=company_usage_id
                    ).distinct()
                )

        user_companies = self.request.user.companies.all()
        return self.get_serializer_class().setup_eager_loading(
            SingleCompanyUsage.objects.filter(
                company_usage__companies__in=user_companies
            ).distinct()
        )
