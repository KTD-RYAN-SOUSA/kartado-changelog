import gzip
import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from functools import reduce
from uuid import UUID

import sentry_sdk
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta
from django.db.models import Exists, F, OuterRef, Q, Subquery, Sum, TextField
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Cast, Length
from django.db.models.query import QuerySet
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.text import compress_string
from django.views.decorators.gzip import gzip_page
from django_filters import rest_framework as filters
from fnc.mappings import get
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_json_api import serializers
from storages.utils import clean_name

from apps.approval_flows.models import ApprovalTransition
from apps.companies.const.app_types import ENERGY
from apps.companies.models import Company, UserInCompany
from apps.maps.models import ShapeFile
from apps.monitorings.models import MonitoringPlan, OperationalControl
from apps.occurrence_records.const.custom_table import (
    DAILY,
    DATA_DAILY,
    DATA_HOURLY,
    DATA_MONTHLY,
    HOURLY,
    MONTHLY,
    VLR_DAILY,
    VLR_HOURLY,
    VLR_MONTHLY,
)
from apps.occurrence_records.const.forms_size import TOTAL_STORAGE, TOTAL_STORAGE_IN_KB
from apps.occurrence_records.const.property_intersections import (
    MAX_PROPERTY_INTERSECTIONS,
)
from apps.occurrence_records.filters import (
    CustomDashboardFilter,
    CustomTableFilter,
    DataSeriesFilter,
    InstrumentMapFilter,
    OccurrenceRecordFilter,
    OccurrenceRecordOrderingFilter,
    OccurrenceRecordWatcherFilter,
    OccurrenceTypeFilter,
    OccurrenceTypeSpecsFilter,
    ParameterGroupFilter,
    RecordPanelFilter,
    TableDataSeriesFilter,
)
from apps.occurrence_records.helpers.gen.pdf import (
    PDFGeneratorWrittenNotification,
    PDFGenericGenerator,
)
from apps.occurrence_records.models import OccurrenceRecord
from apps.reportings.helpers.default_menus import rebalance_visible_panels_orders
from apps.reportings.models import RecordMenuRelation, Reporting
from apps.reportings.serializers import ReportingGeoGZIPSerializer
from apps.reportings.views import ReportingFilter
from apps.service_orders.helpers.report_config_map_default import (
    get_default_config_map_to_report,
)
from apps.service_orders.models import Procedure, ServiceOrder
from apps.users.models import User
from helpers.apis.hidro_api.functions import hidro_api
from helpers.apps.json_logic import apply_json_logic
from helpers.apps.occurrence_record_bi import OccurrenceRecordBIEndpoint
from helpers.apps.occurrence_records import (
    add_occurrence_record_changes_debounce_data,
    apply_conditions_to_query,
    convert_conditions_to_query_params,
    execute_transition,
)
from helpers.apps.pdfs import PDFEndpoint
from helpers.apps.record_panel_fields import get_response
from helpers.apps.reportings import get_lane, get_occurrence_kind, refine_direction
from helpers.custom_endpoints import get_pagination_info
from helpers.dates import date_tz, utc_to_local
from helpers.error_messages import error_message
from helpers.fields import FeatureCollectionField
from helpers.json_parser import JSONParserWithUnformattedKeys
from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset
from helpers.serializers import get_obj_serialized
from helpers.sih_integration import fetch_sih_data
from helpers.sih_table import SihTable
from helpers.strings import (
    dict_to_casing,
    get_obj_from_path,
    keys_to_snake_case,
    strtobool,
    to_snake_case,
)

from .const import data_series_kinds as data_kinds
from .models import (
    CustomDashboard,
    CustomTable,
    DataSeries,
    OccurrenceRecordWatcher,
    OccurrenceType,
    OccurrenceTypeSpecs,
    RecordPanel,
    RecordPanelShowList,
    TableDataSeries,
)
from .notifications import occurrence_record_approval, occurrence_record_approval_todo
from .permissions import (
    AdditionalDocumentPermissions,
    CustomDashboardPermissions,
    CustomTablePermissions,
    DataSeriesPermissions,
    InstrumentMapPermissions,
    OccurrenceRecordPermissions,
    OccurrenceRecordWatcherPermissions,
    OccurrenceTypePermissions,
    OccurrenceTypeSpecsPermissions,
    ParameterGroupPermissions,
    RecordPanelPermissions,
    SIHMonitoringPointMapPermissions,
    TableDataSeriesPermissions,
)
from .serializers import (
    CustomDashboardSerializer,
    CustomTableSerializer,
    DashboardOccurrenceRecordSerializer,
    DataSeriesSerializer,
    InstrumentMapSerializer,
    OccurrenceRecordGeoGZIPSerializer,
    OccurrenceRecordGeoSerializer,
    OccurrenceRecordObjectSerializer,
    OccurrenceRecordSerializer,
    OccurrenceRecordWatcherSerializer,
    OccurrenceTypeObjectSerializer,
    OccurrenceTypeSerializer,
    OccurrenceTypeSpecsSerializer,
    RecordPanelSerializer,
    SIHMonitoringPointMapSerializer,
    TableDataSeriesSerializer,
)


class OccurrenceTypeView(ListCacheMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, OccurrenceTypePermissions]
    filterset_class = OccurrenceTypeFilter
    permissions = None
    ordering = "uuid"
    parser_classes = [JSONParserWithUnformattedKeys]
    parser_keys_to_keep = ["form_fields"]

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update"]:
            return OccurrenceTypeObjectSerializer
        return OccurrenceTypeSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None
        # On list action: limit queryset
        if self.action in ["list", "get_storage"]:
            if "company" not in self.request.query_params:
                return OccurrenceType.objects.none()

            user_company = UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="OccurrenceType",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, OccurrenceType.objects.none())
            if "self" in allowed_queryset:
                user_firms_manager = self.request.user.user_firms_manager.all()
                user_firms = list(
                    (self.request.user.user_firms.all()).union(user_firms_manager)
                )
                queryset = join_queryset(
                    queryset,
                    OccurrenceType.objects.filter(
                        Q(company=user_company), Q(firms__in=user_firms)
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    OccurrenceType.objects.filter(company=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = OccurrenceType.objects.filter(
                company__in=user_companies
            ).distinct()

        # Filter by allowed occurrence kinds (whitelist) - only for list actions
        # For retrieve/update, allow access to existing records even if occurrence_kind is restricted
        if self.permissions and self.action in ["list", "get_storage"]:
            allowed_kinds = self.permissions.get_allowed_occurrence_kinds()
            if allowed_kinds:
                queryset = queryset.filter(occurrence_kind__in=allowed_kinds)

        return self.get_serializer_class().setup_eager_loading(
            queryset.filter(monitoring_plan__isnull=True).distinct()
        )

    @method_decorator(gzip_page)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @action(methods=["GET"], url_path="GZIP", detail=True)
    def get_gzip(self, request, pk=None):
        queryset = self.get_queryset()
        occurrence_type = get_object_or_404(queryset, pk=pk)

        try:
            user_company = UUID(self.request.query_params["company"])
            company = Company.objects.get(pk=user_company)
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.occurrence_type.please_provide_a_valid_company_id"
            )

        if not self.permissions:
            self.permissions = PermissionManager(
                user=self.request.user,
                company_ids=user_company,
                model="OccurrenceType",
            )

        can_view_inventory = bool(
            self.permissions.get_specific_model_permision("Inventory", "can_view")
        )
        can_view_reporting = bool(
            self.permissions.get_specific_model_permision("Reporting", "can_view")
        )
        is_energy = (
            company.mobile_app_override or company.company_group.mobile_app
        ) == ENERGY

        if not (can_view_inventory or can_view_reporting) and is_energy:
            queryset_input = get_occurrence_record_queryset(
                "list", request, None
            ).filter(occurrence_type_id=occurrence_type.pk, geometry__isnull=False)
            filtered_queryset = OccurrenceRecordFilter(
                request.GET, queryset=queryset_input, request=request
            ).qs.prefetch_related(
                *OccurrenceRecordGeoGZIPSerializer._PREFETCH_RELATED_FIELDS
            )

            # Handle pagination (if any)
            page = self.paginate_queryset(filtered_queryset)
            serialized_queryset = OccurrenceRecordGeoGZIPSerializer(
                page or filtered_queryset, many=True
            )
            feature_collection = serialized_queryset.data["features"]

            response_data = {
                "type": "FeatureCollection",
                "features": feature_collection,
                "meta": get_pagination_info(self.request, filtered_queryset.count()),
            }

            json_response = JsonResponse(response_data)
            compressed_content = gzip.compress(json_response.content)

            response = HttpResponse(compressed_content, content_type="application/gzip")
            response["Content-Encoding"] = "gzip"
            response[
                "Content-Disposition"
            ] = f'attachment; filename="{occurrence_type.name}.json"'

            return response
        else:
            queryset_input = Reporting.objects.filter(
                occurrence_type_id=occurrence_type.pk,
                company_id=self.request.query_params["company"],
                geometry__isnull=False,
            )

            filtered_queryset = ReportingFilter(
                request.GET, queryset=queryset_input, request=request
            ).qs.prefetch_related(*ReportingGeoGZIPSerializer._PREFETCH_RELATED_FIELDS)

            # Handle pagination (if any)
            page = self.paginate_queryset(filtered_queryset)
            serialized_queryset = ReportingGeoGZIPSerializer(
                page or filtered_queryset, many=True
            )
            feature_collection = serialized_queryset.data["features"]

            response_data = {
                "type": "FeatureCollection",
                "features": feature_collection,
                "meta": get_pagination_info(self.request, filtered_queryset.count()),
            }

            json_response = JsonResponse(response_data)
            compressed_content = gzip.compress(json_response.content)

            response = HttpResponse(compressed_content, content_type="application/gzip")
            response["Content-Encoding"] = "gzip"
            response[
                "Content-Disposition"
            ] = f'attachment; filename="{occurrence_type.name}.json"'

            return response

    @action(methods=["GET"], url_path="PBF", detail=True)
    def get_pbf(self, request, pk=None):
        # Get instance without filtering the OccurrenceType queryset
        # WARN: self.get_object() should not be used to avoid double filtering
        queryset = self.get_queryset()
        occurrence_type = get_object_or_404(queryset, pk=pk)

        try:
            user_company = UUID(self.request.query_params["company"])
            company = Company.objects.get(pk=user_company)
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.occurrence_type.please_provide_a_valid_company_id"
            )

        if not self.permissions:
            self.permissions = PermissionManager(
                user=self.request.user,
                company_ids=user_company,
                model="OccurrenceType",
            )

        can_view_inventory = bool(
            self.permissions.get_specific_model_permision("Inventory", "can_view")
        )
        can_view_reporting = bool(
            self.permissions.get_specific_model_permision("Reporting", "can_view")
        )
        is_energy = (
            company.mobile_app_override or company.company_group.mobile_app
        ) == ENERGY

        if not (can_view_inventory or can_view_reporting) and is_energy:
            queryset_input = get_occurrence_record_queryset(
                "list", request, None
            ).filter(occurrence_type_id=occurrence_type.pk, geometry__isnull=False)
            filtered_queryset = OccurrenceRecordFilter(
                request.GET, queryset=queryset_input, request=request
            ).qs.prefetch_related(
                *OccurrenceRecordGeoGZIPSerializer._PREFETCH_RELATED_FIELDS
            )

            # Handle pagination (if any)
            page = self.paginate_queryset(filtered_queryset)
            serialized_queryset = OccurrenceRecordGeoGZIPSerializer(
                page or filtered_queryset, many=True
            )

            feature_collection = serialized_queryset.data["features"]

            response_data = {
                "type": "FeatureCollection",
                "features": feature_collection,
                "meta": get_pagination_info(self.request, filtered_queryset.count()),
            }

            json_response = JsonResponse(response_data)
            compressed_content = gzip.compress(json_response.content)
            response = HttpResponse(compressed_content, content_type="application/gzip")
            response["Content-Encoding"] = "gzip"
            response[
                "Content-Disposition"
            ] = f'attachment; filename="{occurrence_type.name}.json"'

            return response
        else:
            queryset_input = Reporting.objects.filter(
                occurrence_type_id=occurrence_type.pk,
                company_id=self.request.query_params["company"],
                geometry__isnull=False,
            )
            filtered_queryset = ReportingFilter(
                request.GET, queryset=queryset_input
            ).qs.prefetch_related(*ReportingGeoGZIPSerializer._PREFETCH_RELATED_FIELDS)

            # Handle pagination (if any)
            page = self.paginate_queryset(filtered_queryset)
            serialized_queryset = ReportingGeoGZIPSerializer(
                page or filtered_queryset, many=True
            )

            feature_collection = serialized_queryset.data["features"]

            response_data = {
                "type": "FeatureCollection",
                "features": feature_collection,
                "meta": get_pagination_info(self.request, filtered_queryset.count()),
            }

            json_response = JsonResponse(response_data)
            compressed_content = gzip.compress(json_response.content)
            response = HttpResponse(compressed_content, content_type="application/gzip")
            response["Content-Encoding"] = "gzip"
            response[
                "Content-Disposition"
            ] = f'attachment; filename="{occurrence_type.name}.json"'

            return response

    @action(methods=["POST"], url_path="NameAvailability", detail=False)
    def get_name_availability(self, request, pk=None):
        if "company" not in request.query_params:
            return error_message(400, 'Parâmetro "Unidade" é obrigatório')
        company = request.query_params["company"]
        input_data = json.loads(request.body).get("data", None)
        if input_data is None:
            raise serializers.ValidationError(
                "kartado.error.occurrence_type.data_key_not_found_on_body"
            )
        name = input_data.get("name")
        if not name:
            return error_message(400, "Insira um valor válido para o nome da Classe")
        does_name_exists = OccurrenceType.objects.filter(
            company__uuid=company, name=name.strip()
        ).exists()

        data = {"is_name_available_for_usage": not does_name_exists}
        return Response(dict_to_casing(data))

    @action(methods=["GET"], url_path="Storage", detail=False)
    def get_storage(self, request, pk=None):
        if "company" not in request.query_params:
            return error_message(400, 'Parâmetro "Unidade" é obrigatório')

        queryset = OccurrenceType.objects.filter(
            company=request.query_params["company"]
        )
        response_data = {}

        if "active" in request.query_params:
            active = strtobool(request.query_params["active"])
            queryset = (
                queryset.filter(active=active)
                .only("form_fields")
                .annotate(
                    forms_size=Length(Cast("form_fields", output_field=TextField()))
                )
            )
        elif "uuid" in request.query_params:
            uuid_queryset = queryset.filter(uuid=request.query_params.get("uuid"))
            response_data.update(
                {
                    "created_at": utc_to_local(
                        uuid_queryset.first().created_at
                    ).strftime("%Y-%m-%dT%H:%M")
                }
            )
            queryset = uuid_queryset.only("form_fields").annotate(
                forms_size=Length(Cast("form_fields", output_field=TextField()))
            )

        else:
            queryset = queryset.only("form_fields").annotate(
                forms_size=Length(Cast("form_fields", output_field=TextField()))
            )

        if queryset:
            form_fields_json = json.dumps([obj.form_fields for obj in queryset])
            compressed_size = round(
                len(compress_string(form_fields_json.encode("utf-8"))) / 1024, 1
            )
            queryset = queryset.aggregate(total_size=Sum("forms_size"))
            used_storage = (
                round((queryset["total_size"] / 1024), 1)
                if queryset["total_size"]
                else 0
            )
            free_storage = round(TOTAL_STORAGE_IN_KB - compressed_size, 1)
            response_data.update(
                {
                    "used_storage": compressed_size,
                    "free_storage": free_storage,
                    "total_storage": TOTAL_STORAGE_IN_KB,
                    "uncompressed_size": used_storage,
                }
            )
            return Response(dict_to_casing(response_data))

        return Response({})

    @action(methods=["POST"], url_path="CanSave", detail=False)
    def get_can_save(self, request, pk=None):
        if "company" not in request.query_params:
            return error_message(400, 'Parâmetro "Unidade" é obrigatório')

        input_data = json.loads(request.body).get("data", None)

        form_fields = input_data.get("form_fields", {})
        if not form_fields:
            return error_message(400, "É necessário informar os campos do formulário")

        queryset = OccurrenceType.objects.filter(
            active=True, company=request.query_params["company"]
        )

        if input_data is None:
            raise serializers.ValidationError(
                "kartado.error.occurrence_type.data_key_not_found_on_body"
            )
        if "uuid" in input_data:
            queryset = queryset.exclude(uuid=input_data.get("uuid"))
        queryset = queryset.only("form_fields")

        form_fields_json = json.dumps([obj.form_fields for obj in queryset])
        compressed_size = len(compress_string(form_fields_json.encode("utf-8")))

        new_form_size = len(compress_string(json.dumps(form_fields).encode("utf-8")))
        new_total_size = compressed_size + new_form_size
        can_save = new_total_size <= TOTAL_STORAGE

        data = {"can_save": can_save}
        return Response(dict_to_casing(data))


class ParameterGroupView(OccurrenceTypeView):
    permission_classes = [IsAuthenticated, ParameterGroupPermissions]
    filterset_class = ParameterGroupFilter
    resource_name = "ParameterGroup"

    def get_queryset(self):
        queryset = None
        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return OccurrenceType.objects.none()

            user_company = UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="OccurrenceType",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, OccurrenceType.objects.none())
            if "self" in allowed_queryset:
                user_firms_manager = self.request.user.user_firms_manager.all()
                user_firms = list(
                    (self.request.user.user_firms.all()).union(user_firms_manager)
                )
                queryset = join_queryset(
                    queryset,
                    OccurrenceType.objects.filter(
                        Q(company__in=[user_company])
                        & (
                            Q(monitoring_plan__cycles_plan__executers__in=user_firms)
                            | Q(monitoring_plan__cycles_plan__viewers__in=user_firms)
                            | Q(monitoring_plan__cycles_plan__evaluators__in=user_firms)
                            | Q(monitoring_plan__cycles_plan__approvers__in=user_firms)
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    OccurrenceType.objects.filter(company__in=[user_company]),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = OccurrenceType.objects.filter(
                company__in=user_companies
            ).distinct()

        return self.get_serializer_class().setup_eager_loading(
            queryset.filter(monitoring_plan__isnull=False).distinct()
        )


class OccurrenceTypeSpecsView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = OccurrenceTypeSpecsSerializer
    permission_classes = [IsAuthenticated, OccurrenceTypeSpecsPermissions]
    filterset_class = OccurrenceTypeSpecsFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None
        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return OccurrenceTypeSpecs.objects.none()

            user_company = UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="OccurrenceTypeSpecs",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, OccurrenceTypeSpecs.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    OccurrenceTypeSpecs.objects.filter(company_id=user_company),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    OccurrenceTypeSpecs.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = OccurrenceTypeSpecs.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


def get_occurrence_record_queryset(
    action, request=None, permissions=None, user_company=None, user=None
):
    queryset = None
    user = request.user if request else user

    if action in ["list", "retrieve"]:
        if request:
            if "company" not in request.query_params:
                return OccurrenceRecord.objects.none()

            user_company = UUID(request.query_params["company"])
        elif not user_company or not user:
            raise ValueError(
                "Both user_company and user are required arguments when not providing a request"
            )

        if not permissions:
            permissions = PermissionManager(
                user=user,
                company_ids=user_company,
                model="OccurrenceRecord",
            )

        all_permission = permissions.all_permissions
        can_view_monitoring = any(
            get("monitoring_plan.can_view", all_permission, default=[])
        )
        can_create_monitoring = any(
            get(
                "monitoring_plan.can_create_monitoring",
                all_permission,
                default=[],
            )
        )
        can_view_operational = any(
            get("operational_control.can_view", all_permission, default=[])
        )
        can_create_operational = any(
            get(
                "operational_control.can_create_operational",
                all_permission,
                default=[],
            )
        )

        allowed_queryset = permissions.get_allowed_queryset()

        if "none" in allowed_queryset:
            queryset = join_queryset(queryset, OccurrenceRecord.objects.none())
        if "self" in allowed_queryset:
            now = timezone.now()
            user_firms = user.user_firms.all()

            # Get accepted_op_controls
            if can_create_operational:
                accepted_op_controls = OperationalControl.objects.filter(
                    firm__company=user_company
                )
            else:
                accepted_op_controls = OperationalControl.objects.filter(
                    Q(firm__company=user_company)
                    & (
                        Q(responsible=user)
                        # Show instances related to the current cycle if user is part of it
                        | (
                            # Consider only current cycle
                            Q(
                                operational_control_cycles__start_date__date__lte=now.date()
                            )
                            & Q(
                                operational_control_cycles__end_date__date__gte=now.date()
                            )
                            # The user firm can be either a creator or a viewer
                            & (
                                Q(operational_control_cycles__creators__in=user_firms)
                                | Q(operational_control_cycles__viewers__in=user_firms)
                            )
                        )
                    )
                )

            # Get accepted_monitorings
            if can_create_monitoring:
                accepted_monitorings = MonitoringPlan.objects.filter(
                    company=user_company
                )
            else:
                accepted_monitorings = MonitoringPlan.objects.filter(
                    Q(company=user_company)
                    & Q(cycles_plan__start_date__date__lte=now.date())
                    & Q(cycles_plan__end_date__date__gte=now.date())
                    & (
                        Q(cycles_plan__executers__in=user_firms)
                        | Q(cycles_plan__viewers__in=user_firms)
                        | Q(cycles_plan__evaluators__in=user_firms)
                        | Q(cycles_plan__approvers__in=user_firms)
                        | Q(cycles_plan__responsibles=user)
                    )
                )

            # Get service_orders
            service_orders = ServiceOrder.objects.filter(
                Q(actions__created_by=user)
                | Q(actions__procedures__created_by=user)
                | Q(actions__procedures__responsible=user)
                | Q(responsibles=user)
                | Q(managers=user)
            )

            # Filter queryset
            queryset = join_queryset(
                queryset,
                OccurrenceRecord.objects.filter(
                    (
                        Q(operational_control__isnull=True)
                        & (
                            Q(created_by=user)
                            | Q(responsible=user)
                            | Q(firm__users=user)
                            | Q(service_orders__in=service_orders)
                        )
                    )
                    | Q(operational_control__in=accepted_op_controls)
                ).filter(
                    Q(monitoring_plan__isnull=True)
                    | Q(monitoring_plan__in=accepted_monitorings)
                ),
            )
        if "all" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                OccurrenceRecord.objects.filter(company=user_company),
            )

        if not can_view_operational:
            queryset = queryset.exclude(operational_control__isnull=False)
        if not can_view_monitoring:
            queryset = queryset.exclude(monitoring_plan__isnull=False)

    # If queryset isn't set by any means above
    if queryset is None:
        user_companies = user.companies.all()
        queryset = OccurrenceRecord.objects.filter(company__in=user_companies)

    return queryset.distinct()


class OccurrenceRecordView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, OccurrenceRecordPermissions]
    filter_backends = [
        filters.DjangoFilterBackend,
        OccurrenceRecordOrderingFilter,
    ]
    filterset_class = OccurrenceRecordFilter
    permissions = None
    resource_name = "OccurrenceRecord"
    ordering = "uuid"

    authentication_types = ["recordbiOnly", "all"]

    # NOTE: One level nested form_data fields are valid in this endpoint due to the OccurrenceRecordOrderingFilter
    ordering_fields = [
        "uuid",
        "status",
        "status__name",
        "created_at",
        "datetime",
        "number",
        "occurrence_type__occurrence_kind",
        "occurrence_type__name",
        "created_by",
        "created_by__first_name",
        "service_orders__number",
        "record_panel",
        "record",
        "type",
        "kind",
        "subject",
        "search_tag_description",
        "location",
        "location__name",
        "created_by",
        "city",
        "city__name",
        "river__name",
        "uf_code",
        "validation_deadline",
        "validated_at",
    ]

    def get_serializer_class(self):
        if self.action in ["retrieve"]:
            return OccurrenceRecordObjectSerializer
        return OccurrenceRecordSerializer

    def get_serializer_context(self):
        context = super(OccurrenceRecordView, self).get_serializer_context()
        user = context["request"].user

        # The current user is not anonymous and the action is list or retrieve
        if not user.is_anonymous and self.action in ["list", "retrieve"]:
            try:
                if context["view"].permissions:
                    context.update(
                        {
                            "user_firms": user.user_firms.filter(
                                company_id=context["view"].permissions.company_id
                            )
                        }
                    )
            except AttributeError as err:
                # Send the exception to Sentry
                sentry_sdk.capture_exception(err)
        return context

    def update(self, request, *args, **kwargs):
        # use get_object to call the permissions
        self.get_object()

        if (
            hasattr(self, "has_permission_operational")
            and not self.has_permission_operational
        ):
            # has no permission and returns 200 to not block the app
            return Response({})

        # TODO: validar se todos properties estão sendo salvos corretamente e não
        # os existente. feito para coletar os proprietary de cada features
        if (
            request.data.get("feature_collection", None) is not None
            and request.data["feature_collection"].get("features", None) is not None
        ):
            data_properties = []
            for features in request.data["feature_collection"].get("features"):
                prop = features.get("properties", {})
                data_properties.append(prop)

            request.data["properties"] = data_properties

        return super(OccurrenceRecordView, self).update(request, args, kwargs)

    def create(self, request, *args, **kwargs):
        if (
            hasattr(self, "has_permission_operational")
            and not self.has_permission_operational
        ):
            # has no permission and returns 201 to not block the app
            return Response({}, status=status.HTTP_201_CREATED)
        return super(OccurrenceRecordView, self).create(request, args, kwargs)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, responsible=self.request.user)

    def get_queryset(self):
        queryset = get_occurrence_record_queryset(
            self.action, self.request, self.permissions
        )

        return self.get_serializer_class().setup_eager_loading(queryset)

    @method_decorator(gzip_page)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @action(methods=["post"], url_path="FindIntersects", detail=False)
    def find_intersects(self, request, pk=None):
        if (
            "company" not in request.data.keys()
            or "feature_collection" not in request.data.keys()
        ):
            raise serializers.ValidationError(
                "Não é possível realizar esta operação sem atributos company ou feature_collection."
            )

        try:
            company = Company.objects.get(pk=request.data.get("company").get("id"))
        except Exception:
            raise serializers.ValidationError("Company não encontrada.")

        feature_collection = FeatureCollectionField(
            geometry_field="geometry", properties_field="properties"
        )
        collection = feature_collection.to_internal_value(
            request.data["feature_collection"]
        )

        if collection["geometry"] and "properties_shape" in company.metadata:
            try:
                shape = ShapeFile.objects.get(uuid=company.metadata["properties_shape"])
            except Exception:
                pass
            else:
                intersects = []
                for index, geometry in enumerate(shape.geometry):
                    try:
                        if geometry.intersects(collection["geometry"]):
                            intersects.append((index, geometry))
                    except Exception:
                        pass

                if len(intersects) > MAX_PROPERTY_INTERSECTIONS:
                    raise serializers.ValidationError(
                        "kartado.error.occurrence_records.provided_geometry_contains_too_many_property_intersections"
                    )

                intersects = [
                    {
                        "geometry": json.loads(geometry[1].json),
                        "attributes": {
                            "uuid": "{}-{}".format(
                                str(shape.uuid),
                                shape.properties[geometry[0]]["OBJECTID"],
                            ),
                            **shape.properties[geometry[0]],
                        },
                    }
                    for geometry in intersects
                ]

                return Response({"data": {"intersects": intersects}})

        return Response({"data": {"intersects": []}})

    @action(methods=["get"], url_path="GetHydrology", detail=False)
    def get_hydrology(self, request, pk=None):
        # /OccurrenceRecord/GetHydrology/?company={}&datetime={}
        # company (an uuid) and datetime (in ISOString format) are required.
        # This endpoint returns the values we get from the hidro_api.
        if (
            "company" not in request.query_params.keys()
            or "datetime" not in request.query_params.keys()
        ):
            raise serializers.ValidationError(
                "Não é possível realizar esta operação sem atributos company ou datetime."
            )

        try:
            company = Company.objects.get(pk=request.query_params.get("company"))
        except Exception:
            raise serializers.ValidationError("Company não encontrada.")

        date = date_tz(request.query_params.get("datetime"))

        level = hidro_api(company.metadata.get("company_prefix", ""), date)["response"]

        return Response(level)

    @action(methods=["post"], url_path="ChangeStatus", detail=True)
    def change_status(self, request, pk=None):
        action_map = {
            "reject": "Rejeitar",
            "approve": "Homologar",
            "requestReview": "Solicitar Revisão",
            "sendToApproval": "Solicitar Homologação",
        }

        try:
            request.data["action"] = action_map[request.data["action"]]
        except KeyError:
            raise serializers.ValidationError("Ação não encontrada.")

        return self.approval(request)

    @action(methods=["get"], url_path="PDF", detail=True)
    def pdf_occurrence_record(self, request, pk=None):
        obj = self.get_object()
        endpoint = PDFEndpoint(obj, pk, request, "OccurrenceRecord")
        return endpoint.get_response()

    @action(methods=["post"], url_path="PDFReport", detail=True)
    def pdf_report_occurrence_record(self, request, pk=None):
        if pk is None:
            obj = self.get_object()
        if pk is not None:
            obj = OccurrenceRecord.objects.filter(pk=pk).first()
        if obj is None:
            raise serializers.ValidationError(
                "kartado.error.pdf_report_occurrence_record.occurrence_record_not_found"
            )

        template_name = "occurrence_records/pdf/template_record.html"
        data = keys_to_snake_case(request.data)
        config_map = data.get("map_settings", "")

        if not config_map:
            data.update(get_default_config_map_to_report(obj))

        pdf_config = data
        pdf = PDFGenericGenerator(
            request,
            obj,
            template_name,
            pdf_config,
        )

        context = pdf.get_context()

        response = HttpResponse(
            pdf.build_pdf(),
            content_type="application/pdf",
        )
        number = context.get("number", {})
        response["Content-Disposition"] = f'filename="Kartado - Registro {number}.pdf"'

        return response

    @action(methods=["post"], url_path="ChangeServiceOrder", detail=True)
    def change_service_order(self, request, pk=None):
        occurrence_record = self.get_object()

        if not occurrence_record.is_approved:
            raise serializers.ValidationError("O registro ainda não foi homologado.")

        if "service_order" in request.data.keys():
            current_ids = [
                str(item)
                for item in occurrence_record.service_orders.values_list(
                    "uuid", flat=True
                )
            ]
            new_ids = request.data["service_order"]
            ids_to_remove = list(set(current_ids) - set(new_ids))
            ids_to_add = list(set(new_ids) - set(current_ids))

            if ids_to_remove:
                procedure_objs = get(
                    "form_data.procedure_objects", occurrence_record, default=[]
                )
                procedure_uuids = [
                    get("uuid", item)
                    for item in procedure_objs
                    if get("service_order.id", item) in ids_to_remove
                ]

                if Procedure.objects.filter(
                    uuid__in=procedure_uuids, procedure_next__isnull=False
                ).exists():
                    raise serializers.ValidationError(
                        "kartado.error.occurrence_record.service_remove_error"
                    )
                elif procedure_objs:
                    Procedure.objects.filter(uuid__in=procedure_uuids).delete()
                    for item in occurrence_record.form_data["procedure_objects"]:
                        if get("service_order.id", item) in ids_to_remove:
                            item.pop("uuid")

                try:
                    occurrence_record.service_orders.remove(*ids_to_remove)
                except Exception:
                    raise serializers.ValidationError(
                        "kartado.error.occurrence_record.service_not_found"
                    )

                occurrence_record.save()
            elif ids_to_add:
                try:
                    occurrence_record.service_orders.add(*ids_to_add)
                except Exception:
                    raise serializers.ValidationError(
                        "kartado.error.occurrence_record.service_not_found"
                    )

                # Debounce added services notification
                add_occurrence_record_changes_debounce_data(
                    occurrence_record, added_services_ids=ids_to_add
                )
            else:
                raise serializers.ValidationError(
                    "kartado.error.occurrence_record.no_service"
                )
            return Response({"data": {"status": "OK"}})

        raise serializers.ValidationError("kartado.error.occurrence_record.no_service")

    def process_approval(self, occurrence_records: list, user, request_data):
        """Handles the approval of one or more instances"""
        # Get flags
        use_all_transitions = request_data.pop("use_all", False)
        action = (
            request_data["action"]
            if "action" in request_data and isinstance(request_data["action"], list)
            else None
        )
        to_do = request_data["to_do"] if "to_do" in request_data else None

        for occurrence_record in occurrence_records:
            # Get all the necessary ApprovalTransitions
            if use_all_transitions:
                transitions = ApprovalTransition.objects.filter(
                    origin__approval_flow__company=occurrence_record.company
                )
            else:
                transitions = ApprovalTransition.objects.filter(
                    origin=occurrence_record.approval_step
                )

            # Check if the condition from any ApprovalTransition was met
            # If the condition was met, execute the ApprovalStep change
            source = get_obj_serialized(
                occurrence_record,
                OccurrenceRecordSerializer,
                OccurrenceRecordView,
            )

            # Check if request action is multiple
            if action:
                for item in action:
                    new_data = {**request_data, "action": item}
                    occurrence_record = execute_transition(
                        new_data, transitions, occurrence_record, source
                    )
            else:
                occurrence_record = execute_transition(
                    request_data, transitions, occurrence_record, source
                )

            occurrence_record_approval(str(occurrence_record.uuid))
            occurrence_record_approval_todo(occurrence_record, user)

            if to_do is not None:
                hist = occurrence_record.history.first()
                hist.history_change_reason = (
                    to_do if to_do else "Registro necessita de revisão."
                )
                hist.save()

        return {"data": {"status": "OK"}}

    @action(methods=["post"], url_path="Approval", detail=True)
    def approval(self, request, pk=None):
        occurrence_record = self.get_object()
        request_data = dict_to_casing(self.request.data, "underscore")
        response_data = self.process_approval(
            [occurrence_record], self.request.user, request_data
        )

        return Response(response_data)

    @action(methods=["post"], url_path="BulkApproval", detail=False)
    def bulk_approval(self, request, pk=None):
        request_data = dict_to_casing(self.request.data, "underscore")

        try:
            occ_record_ids_list = [
                uuid.UUID(occ_record_uuid)
                for occ_record_uuid in request_data["occurrence_records"]
            ]
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.occurrence_record.malformed_occurrence_record_uuid_list"
            )

        occ_records = OccurrenceRecord.objects.filter(
            pk__in=occ_record_ids_list
        ).prefetch_related("approval_step")

        response_data = self.process_approval(
            occ_records, self.request.user, request_data
        )

        return Response(response_data)

    @action(methods=["get"], url_path="BI", detail=False)
    def occurrence_record_bi(self, request, pk=None):
        # OccurrenceRecord/BI endpoint. Returns all OccurrenceRecords.
        # OccurrenceRecords filters and sorts are available
        companies_with_permission = []
        for perm in self.permission_classes:
            if hasattr(perm, "companies_with_permission"):
                companies_with_permission = perm.companies_with_permission

        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(company__in=companies_with_permission)
        page = self.paginate_queryset(queryset)
        if page is not None:
            data = OccurrenceRecordBIEndpoint(page).get_data()
            return self.get_paginated_response(data)

        data = OccurrenceRecordBIEndpoint(queryset).get_data()
        return Response(data)

    @action(methods=["GET"], url_path="DashboardOccurrenceRecord", detail=False)
    def dashboard_occurrence_record(self, request, pk=None):
        orig_filtered_qs = self.filter_queryset(self.get_queryset())

        # Parse, validate and extract the layers
        try:
            str_layers = self.request.query_params["layers"]
            layers = dict_to_casing(json.loads(str_layers), "underscore")

            assert "record_panels" in layers
            assert "occurrence_types" in layers
            assert all(isinstance(item, str) for item in layers["record_panels"])
            assert all(isinstance(item, str) for item in layers["occurrence_types"])

            record_panel_ids = layers["record_panels"]
            occurrence_type_ids = layers["occurrence_types"]

            record_panels = RecordPanel.objects.filter(uuid__in=record_panel_ids)
            occurrence_types = OccurrenceType.objects.filter(
                uuid__in=occurrence_type_ids
            )
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.occurrence_record.malformed_layers_query_param"
            )

        # Get raw data
        raw_seri_rec_panels = record_panels.values(
            "uuid", "name", "color", "icon", "conditions"
        )
        raw_seri_occ_types = occurrence_types.values(
            "uuid",
            "name",
            "color",
            "icon",
            "occurrencetype_specs__color",
            "occurrencetype_specs__company",
        )

        def serialize_layers(layer_type: str, raw_layer_data: QuerySet) -> dict:
            """
            Serialize the necessary layer data

            Args:
                layer_type (str): The name of the layer's model
                raw_layer_data (QuerySet): QuerySet of that model's raw values

            Returns:
                dict: Serialized data
            """

            seri_layer_data = {}
            for raw_layer_data_dict in raw_layer_data:
                # Base info
                layer_id = str(raw_layer_data_dict["uuid"])
                name = raw_layer_data_dict["name"]
                icon = raw_layer_data_dict["icon"]

                # Handle diff color sources
                if "occurrencetype_specs__color" in raw_layer_data_dict:
                    if raw_layer_data_dict[
                        "occurrencetype_specs__color"
                    ] and raw_layer_data_dict[
                        "occurrencetype_specs__company"
                    ] == uuid.UUID(
                        self.request.query_params["company"]
                    ):
                        color = raw_layer_data_dict["occurrencetype_specs__color"]
                        seri_layer_data[layer_id] = {
                            "type": layer_type,
                            "uuid": layer_id,
                            "name": name,
                            "color": color,
                            "icon": icon,
                        }
                else:
                    color = raw_layer_data_dict["color"]
                    seri_layer_data[layer_id] = {
                        "type": layer_type,
                        "uuid": layer_id,
                        "name": name,
                        "color": color,
                        "icon": icon,
                    }

            return seri_layer_data

        seri_rec_panels = serialize_layers("RecordPanel", raw_seri_rec_panels)
        seri_occ_types = serialize_layers("OccurrenceType", raw_seri_occ_types)

        # Build a list of OccurrenceRecords according to the respective related model
        # NOTE: This is done due to the fact that we're doing an OR operation further down
        # and also the fact that this separation might be useful in the future (check KTD-1700)
        rec_panel_to_qs = {
            str(record_panel["uuid"]): apply_conditions_to_query(
                record_panel["conditions"], orig_filtered_qs
            )
            for record_panel in raw_seri_rec_panels
        }
        occ_type_to_qs = {
            str(occ_type["uuid"]): orig_filtered_qs.filter(
                occurrence_type_id=occ_type["uuid"]
            )
            for occ_type in raw_seri_occ_types
        }

        def gen_record_to_seri_layer_dict(layer_to_qs: dict, seri_layers: dict) -> dict:
            """
            Generate a reference dict to relate the OccurrenceRecord ID
            with the serialized layer data

            Args:
                layer_to_qs (dict): Reference dict relating the layer ID to the OccurrenceRecord queryset
                seri_layers (dict): The dict containing the serialized layer data

            Returns:
                dict: Reference dict relating the OccurrenceRecord ID to the serialized layer data
            """
            occ_to_layers = {}

            for layer_id, qs in layer_to_qs.items():
                occ_record_ids = qs.values_list("uuid", flat=True)
                for occ_record_id in occ_record_ids:
                    str_id = str(occ_record_id)
                    if str_id not in occ_to_layers:
                        occ_to_layers[str_id] = []

                    occ_to_layers[str_id].append(seri_layers[layer_id])

            return occ_to_layers

        occ_to_panels = gen_record_to_seri_layer_dict(rec_panel_to_qs, seri_rec_panels)
        occ_to_occ_types = gen_record_to_seri_layer_dict(occ_type_to_qs, seri_occ_types)

        def gen_full_queryset() -> QuerySet:
            """
            Merge all the OccurrenceRecord QuerySets

            Returns:
                QuerySet: Merged QuerySet
            """

            qs_list = []
            qs_list += [qs for qs in rec_panel_to_qs.values()]
            qs_list += [qs for qs in occ_type_to_qs.values()]

            joined_queryset = reduce(
                lambda qs1, qs2: join_queryset(qs1, qs2),
                qs_list,
                OccurrenceRecord.objects.none(),
            )

            return joined_queryset

        merged_queryset = gen_full_queryset()

        # Serialize & paginate the OccurrenceRecord queryset
        page = self.paginate_queryset(merged_queryset)
        if page is not None:
            seri_occurrence_records = DashboardOccurrenceRecordSerializer(
                page, many=True
            ).data
        else:
            seri_occurrence_records = DashboardOccurrenceRecordSerializer(
                merged_queryset, many=True
            ).data

        # Add serialized layers to their respective serialized OccurrenceRecords
        response = []
        for seri_occ_record in seri_occurrence_records:
            occ_record_id = seri_occ_record["uuid"]
            occ_record_panels = occ_to_panels.get(occ_record_id, [])
            occ_record_occ_types = occ_to_occ_types.get(occ_record_id, [])

            all_layers = occ_record_panels + occ_record_occ_types
            seri_occ_record["layers"] = all_layers

            response.append(seri_occ_record)

        return self.get_paginated_response(response)


class AdditionalDocumentView(OccurrenceRecordView):
    permission_classes = [IsAuthenticated, AdditionalDocumentPermissions]
    resource_name = "AdditionalDocument"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return OccurrenceRecord.objects.none()

            user_company = UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="AdditionalDocument",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, OccurrenceRecord.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    OccurrenceRecord.objects.filter(
                        Q(created_by=self.request.user)
                        | Q(service_orders__actions__created_by=self.request.user)
                        | Q(
                            service_orders__actions__procedures__created_by=self.request.user
                        )
                        | Q(
                            service_orders__actions__procedures__responsible=self.request.user
                        )
                        | Q(service_orders__responsibles=self.request.user)
                        | Q(service_orders__managers=self.request.user)
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    OccurrenceRecord.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = OccurrenceRecord.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(
            queryset.filter(parent_action__isnull=False).distinct()
        )


class OccurrenceRecordGeoView(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, OccurrenceRecordPermissions]
    filterset_class = OccurrenceRecordFilter
    serializer_class = OccurrenceRecordGeoSerializer
    permissions = None
    ordering = "uuid"

    ordering_fields = [
        "uuid",
        "status__name",
        "created_at",
        "datetime",
        "number",
        "occurrence_type__occurrence_kind",
        "occurrence_type__name",
        "created_by__first_name",
    ]

    def get_queryset(self):
        queryset = get_occurrence_record_queryset(
            self.action, self.request, self.permissions
        )

        return self.get_serializer_class().setup_eager_loading(queryset)


class OccurrenceRecordWatcherView(viewsets.ModelViewSet):
    serializer_class = OccurrenceRecordWatcherSerializer
    filterset_class = OccurrenceRecordWatcherFilter
    permissions = None
    ordering = "uuid"

    def get_permissions(self):
        if self.action == "change_status_email":
            self.permission_classes = []
        else:
            self.permission_classes = [
                IsAuthenticated,
                OccurrenceRecordWatcherPermissions,
            ]

        return super(OccurrenceRecordWatcherView, self).get_permissions()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def get_queryset(self):
        queryset = None
        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return OccurrenceRecordWatcher.objects.none()

            user_company = UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="OccurrenceRecordWatcher",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(
                    queryset, OccurrenceRecordWatcher.objects.none()
                )
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    OccurrenceRecordWatcher.objects.filter(
                        Q(user=self.request.user)
                        | Q(created_by=self.request.user)
                        | Q(updated_by=self.request.user)
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    OccurrenceRecordWatcher.objects.filter(
                        occurrence_record__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            if self.request.user.is_anonymous:
                obj_uuid = self.request.path.split("/")[2]
                queryset = OccurrenceRecordWatcher.objects.filter(uuid=obj_uuid)
            else:
                user_companies = self.request.user.companies.all()
                queryset = OccurrenceRecordWatcher.objects.filter(
                    occurrence_record__company__in=user_companies
                )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["GET"], url_path="Status", detail=True)
    def change_status_email(self, request, pk=None):
        watcher = self.get_object()
        watcher.status_email = False
        watcher.save()

        html = "occurrence_records/email/watcher_unsubscribed.html"

        return render(request, html)


class RecordPanelView(viewsets.ModelViewSet):
    serializer_class = RecordPanelSerializer
    filterset_class = RecordPanelFilter
    permissions = None
    permission_classes = [IsAuthenticated, RecordPanelPermissions]
    parser_classes = [JSONParserWithUnformattedKeys]
    parser_keys_to_keep = ["kanban_columns"]

    ordering = "panel_order"
    ordering_fields = [
        "uuid",
        "name",
        "panel_type",
        "conditions",
        "company",
        "viewer_users",
        "viewer_firms",
        "viewer_permissions",
        "editor_users",
        "editor_firms",
        "editor_permissions",
        "list_columns",
        "list_order_by",
        "kanban_columns",
        "kanban_group_by",
        "created_at",
        "created_by",
        "panel_order",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return RecordPanel.objects.none()

            user_company = UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="RecordPanel",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, RecordPanel.objects.none())
            if "default" in allowed_queryset:
                request_user = self.request.user
                user_firms = request_user.user_firms.all()
                user_permissions = UserInCompany.objects.filter(
                    company_id=user_company, user=request_user
                ).values_list("permissions", flat=True)

                queryset = join_queryset(
                    queryset,
                    RecordPanel.objects.filter(
                        Q(company_id=user_company)
                        & (
                            Q(created_by=request_user)
                            | Q(name="Todos")
                            | Q(viewer_users__in=[request_user])
                            | Q(viewer_firms__in=user_firms)
                            | Q(viewer_permissions__in=user_permissions)
                            | Q(editor_users__in=[request_user])
                            | Q(editor_firms__in=user_firms)
                            | Q(editor_permissions__in=user_permissions)
                            | Q(viewer_subcompanies__subcompany_firms__in=user_firms)
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    RecordPanel.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = RecordPanel.objects.filter(company__in=user_companies)

        order_sub = RecordPanelShowList.objects.filter(
            user=self.request.user, panel=OuterRef("pk")
        )
        menu_relation_sub = RecordMenuRelation.objects.filter(
            record_menu=OuterRef("menu"), user=self.request.user, hide_menu=True
        ).values("pk")

        # Annotations para evitar N+1 nos SerializerMethodField
        # Cada um desses elimina 1 query POR RecordPanel
        show_in_list_sub = RecordPanel.show_in_list_users.through.objects.filter(
            panel_id=OuterRef("pk"), user_id=self.request.user.pk
        )
        show_in_web_map_sub = RecordPanel.show_in_web_map_users.through.objects.filter(
            panel_id=OuterRef("pk"), user_id=self.request.user.pk
        )
        show_in_app_map_sub = RecordPanel.show_in_app_map_users.through.objects.filter(
            panel_id=OuterRef("pk"), user_id=self.request.user.pk
        )
        new_to_user_sub = RecordPanelShowList.objects.filter(
            panel_id=OuterRef("pk"), user_id=self.request.user.pk, new_to_user=True
        )

        queryset = queryset.distinct().annotate(
            panel_order=Subquery(order_sub.values("order")[:1]),
            hidden_menu=Exists(menu_relation_sub),
            # Flags para eliminar N+1
            show_in_list_flag=Exists(show_in_list_sub),
            show_in_web_map_flag=Exists(show_in_web_map_sub),
            show_in_app_map_flag=Exists(show_in_app_map_sub),
            new_to_user_flag=Exists(new_to_user_sub),
        )

        return self.get_serializer_class().setup_eager_loading(queryset)

    def get_serializer_context(self):
        context = super(RecordPanelView, self).get_serializer_context()
        user = context["request"].user

        # The current user is not anonymous and the action is list or retrieve
        if not user.is_anonymous and self.action in [
            "list",
            "retrieve",
            "update",
            "partial_update",
        ]:
            try:
                if "company" in self.request.query_params:
                    user_company = UUID(self.request.query_params["company"])
                elif "company" in self.request.data:
                    user_company = UUID(self.request.data["company"]["id"])
                else:
                    user_company = self.permissions.company_id

                context.update(
                    {
                        # List of UUIDs of the user firms in that company
                        "user_firms": user.user_firms.filter(
                            company_id=user_company
                        ).values_list("uuid", flat=True),
                        # List of UUIDs of the user permissions in that company. Usually a single one
                        "user_permissions": user.companies_membership.filter(
                            company_id=user_company
                        ).values_list("permissions_id", flat=True),
                    }
                )
            except (KeyError, AttributeError) as err:
                # Send the exception to Sentry
                sentry_sdk.capture_exception(err)
        return context

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(methods=["POST"], url_path="ChangeOrder", detail=False)
    def change_order(self, request):
        input_data = json.loads(request.body)
        panel_order = get_obj_from_path(input_data, "data__attributes__panelorder")
        panel_order_tuples = []

        # Validate and build tuple list
        for item in panel_order:
            is_dict = isinstance(item, dict)
            panel = item.get("panel", None) if is_dict else None
            order = item.get("order", None) if is_dict else None
            order_is_int = isinstance(order, int)

            # Convert panel to UUID
            try:
                panel = UUID(panel)
            except Exception:
                raise serializers.ValidationError(
                    "kartado.error.record_panel.invalid_record_panel_uuid_provided"
                )

            if all([is_dict, panel, order, order_is_int]):
                panel_order_tuples.append((panel, order))
            else:
                raise serializers.ValidationError(
                    "kartado.error.record_panel.badly_formed_request_body"
                )

        # Do all uuids match a RecordPanel?
        uuid_list = [panel_id for (panel_id, _) in panel_order_tuples]
        record_panel_qs = RecordPanel.objects.filter(uuid__in=uuid_list).only(
            "uuid", "company_id"
        )
        if record_panel_qs.count() != len(uuid_list):
            raise serializers.ValidationError(
                "kartado.error.record_panel.invalid_record_panel_uuid_provided"
            )
        else:
            company_id = str(record_panel_qs[0].company_id)
            menu_id = (
                str(record_panel_qs[0].menu_id)
                if record_panel_qs[0].menu_id is not None
                else None
            )

        # Handle RecordPanelShowList
        user = request.user
        status_list = []

        def add_resp_status(panel_id, order_value, status_message):
            """Add status message to the response for the provided panel ID"""
            status_list.append(
                {
                    "uuid": str(panel_id),
                    "order": order_value,
                    "status": status_message,
                }
            )

        for panel_id, order_value in panel_order_tuples:
            try:
                show_list_instance = RecordPanelShowList.objects.get(
                    panel=panel_id, user=user
                )
            except RecordPanelShowList.DoesNotExist:
                try:
                    system_default = (
                        RecordPanel.objects.only("system_default")
                        .get(pk=panel_id)
                        .system_default
                    )
                    order_value = 99999 if system_default is True else order_value
                except Exception:
                    pass
                RecordPanelShowList.objects.create(
                    panel_id=panel_id, user=user, order=order_value
                )

                add_resp_status(panel_id, order_value, "RecordPanelShowList created")
            else:
                if show_list_instance.order != order_value:
                    show_list_instance.order = order_value
                    show_list_instance.save()

                    add_resp_status(
                        panel_id,
                        order_value,
                        "RecordPanelShowList order updated",
                    )
                else:
                    add_resp_status(
                        panel_id,
                        order_value,
                        "RecordPanelShowList order maintained",
                    )

        # Remove other RecordPanelShowList
        if menu_id:
            removal_qs = RecordPanelShowList.objects.filter(
                Q(user=user) & Q(panel__menu_id=menu_id) & ~Q(panel__in=record_panel_qs)
            )
        else:
            removal_qs = RecordPanelShowList.objects.filter(
                Q(user=user) & ~Q(panel__in=record_panel_qs)
            )
        if removal_qs:
            removal_list = list(removal_qs.values_list("panel", "order"))
            for panel_id, order_value in removal_list:
                add_resp_status(panel_id, order_value, "RecordPanelShowList removed")

            removal_qs.delete()

        rebalance_visible_panels_orders(
            user_id=str(user.uuid), company_id=company_id, menu_id=menu_id
        )

        return Response({"data": {"panelOrder": status_list}})

    @action(methods=["GET"], url_path="KanBan", detail=True)
    def get_kanban(self, request, pk=None):
        QUERY_LIMIT = 500
        GROUP_OPTIONS = [
            "datetime",
            "record",
            "type",
            "kind",
            "created_by",
            "status",
            "firm",
            "subcompany",
            "due_at",
            "occurrence_kind",
            "occurrence_type",
        ]

        ITEM_WITHOUT_VALUE_TITLE = "Itens sem valor de agrupamento"
        record_panel = self.get_object()
        if record_panel.content_type.model == "occurrencerecord":
            record_panel_type = "occurrence_record"
            model = OccurrenceRecord
        elif record_panel.content_type.model == "reporting":
            record_panel_type = "reporting"
            model = Reporting
        else:
            raise serializers.ValidationError(
                "kartado.error.record_panel.not_valid_record_panel"
            )
        kanban_columns = dict_to_casing(record_panel.kanban_columns, "underscore")
        kanban_group_by_dict = dict_to_casing(
            record_panel.kanban_group_by, "underscore"
        )
        kanban_group_by = (
            to_snake_case(kanban_group_by_dict["group_by"])
            if "group_by" in kanban_group_by_dict
            else None
        )
        order_items_without_value = (
            to_snake_case(kanban_group_by_dict["order_items_without_value"])
            if "order_items_without_value" in kanban_group_by_dict
            else None
        )

        if "company" not in request.query_params.keys():
            raise serializers.ValidationError(
                "kartado.error.record_panel.company_uuid_needs_to_be_provided"
            )
        else:
            try:
                company_id = uuid.UUID(request.query_params["company"])
                company_obj = Company.objects.get(uuid=company_id)
            except Exception:
                raise serializers.ValidationError(
                    "kartado.error.record_panel.invalid_company_uuid"
                )

        if record_panel.panel_type == "KANBAN":
            if not kanban_columns:
                raise serializers.ValidationError(
                    "kartado.error.record_panel.record_panel_doesnt_have_kanban_columns"
                )

            # Process query
            query_params = Q(company_id=company_id)

            # Handle conditions
            if record_panel.conditions:
                if not record_panel.conditions.get("logic"):
                    raise serializers.ValidationError(
                        "kartado.error.record_panel.record_panel_conditions_does_not_have_logic_field"
                    )
                conditions_query_params = convert_conditions_to_query_params(
                    record_panel.conditions["logic"]
                )

                query_params = (
                    (query_params & conditions_query_params)
                    if conditions_query_params
                    else query_params
                )

            # Remove special column and add query param to remove records with that column's status
            try:
                available_status_column = kanban_columns["columns"].pop(
                    "available_status", None
                )
                query_params = query_params & ~Q(
                    status__in=available_status_column["status_ids"]
                )
            except Exception:
                pass

            # NOTE: Two queries happen here since the query needs to be filtered further down and slicing removes this ability
            # NOTE: A second query is made to remove this limitation
            try:
                base_record_list = (
                    model.objects.filter(query_params)
                    .only("uuid")
                    .values_list("uuid", flat=True)
                )
            except Exception:
                raise serializers.ValidationError(
                    "kartado.error.record_panel.invalid_query_params_for_{}_object.".format(
                        record_panel_type
                    )
                )
            limited_record_list = base_record_list[:QUERY_LIMIT]
            limited_record_list = model.objects.filter(uuid__in=limited_record_list)
            # Data gathering
            # kanban_status = kanban_columns["status"]
            kanban_order = kanban_columns["column_order"]
            kanban_columns = kanban_columns["columns"]

            response_data = {
                "columns": {},
                "column_order": kanban_order,
                "record_count": limited_record_list.count(),
                "total_count": base_record_list.count(),
            }

            def get_avatar_url(avatar):
                """Returns the full URL of a avatar"""
                try:
                    if avatar.name:
                        params = {
                            "Bucket": avatar.storage.bucket.name,
                            "Key": avatar.storage._normalize_name(
                                clean_name(avatar.name)
                            ),
                        }

                        return avatar.storage.bucket.meta.client.generate_presigned_url(
                            "get_object", Params=params, ExpiresIn=3600
                        )
                    else:
                        return None
                except Exception:
                    return None

            def process_related_users(user_instances: list):
                """
                Small helper to aid user data extraction
                """
                if user_instances:
                    user_instances = list(set(user_instances))

                    return [
                        {
                            "avatar_url": get_avatar_url(user.avatar),
                            "full_name": user.get_full_name(),
                        }
                        for user in user_instances
                        if user is not None
                    ]
                else:
                    return []

            def entry_sort_func(item: dict):
                return item["number"]

            def group_sort_func(item: dict):
                if item["grouped_by"] == "datetime":
                    (month, year) = item["title"].split("/")
                    return year + month

                else:
                    return item["title"]

            for column_id, column_info in kanban_columns.items():
                column_title = column_info.get("title", "")
                status_ids = column_info["status_ids"]
                if record_panel_type == "occurrence_record":
                    column_records = limited_record_list.filter(
                        status__in=status_ids
                    ).prefetch_related(
                        "status",
                        "status__status_specs",
                        "search_tags",
                        "created_by",
                    )
                else:
                    column_records = limited_record_list.filter(
                        status__in=status_ids
                    ).prefetch_related(
                        "status",
                        "status__status_specs",
                        "created_by",
                        "approval_step",
                        "firm",
                        "firm__subcompany",
                        "occurrence_type",
                    )

                record_entries = []
                for record in column_records:
                    if record_panel_type == "occurrence_record":
                        # Handle SearchTags
                        lv_one_tag = record.search_tags.filter(level=1).first()
                        lv_one_tag = lv_one_tag.name if lv_one_tag else None

                        lv_two_tag = record.search_tags.filter(level=2).first()
                        lv_two_tag = lv_two_tag.name if lv_two_tag else None

                        lv_three_tag = record.search_tags.filter(level=3).first()
                        lv_three_tag = lv_three_tag.name if lv_three_tag else None

                        lv_four_tag = record.search_tags.filter(level=4).first()
                        lv_four_tag = lv_four_tag.name if lv_four_tag else None

                    # Handle related users
                    user_instances = []

                    # Creator
                    if record.created_by:
                        user_instances.append(record.created_by)

                    # History/approval users
                    user_uuids = record.history.all().values_list(
                        "history_user", flat=True
                    )
                    if user_uuids:
                        user_instances += list(User.objects.filter(uuid__in=user_uuids))

                    # Status color
                    status_color = record.status.status_specs.first().color

                    default_entry = {
                        "uuid": record.uuid,
                        "status_name": record.status.name,
                        "status_color": status_color,
                        "number": record.number,
                        "related_users": process_related_users(user_instances),
                    }

                    if model == OccurrenceRecord:
                        default_entry.update(
                            {
                                "record": lv_one_tag,
                                "datetime": (
                                    record.datetime.isoformat()
                                    if record.datetime
                                    else None
                                ),
                                "date": (
                                    record.datetime.strftime("%m/%Y")
                                    if record.datetime
                                    else None
                                ),
                                "created_by": (
                                    record.created_by.get_full_name()
                                    if record.created_by
                                    else None
                                ),
                                "type": lv_two_tag,
                                "kind": lv_three_tag,
                                "subject": lv_four_tag,
                                "description": record.search_tag_description,
                            }
                        )
                    else:
                        default_entry.update(
                            {
                                "road_name": record.road_name,
                                "occurrence_kind": get_occurrence_kind(
                                    record.occurrence_type.occurrence_kind,
                                    company_obj,
                                ),
                                "occurrence_type": (
                                    record.occurrence_type.name
                                    if record.occurrence_type
                                    else ""
                                ),
                                "km": record.km,
                                "direction": refine_direction(record, company_obj),
                                "lane": get_lane(record.lane, company_obj),
                                "subcompany_name": (
                                    record.firm.subcompany.name
                                    if record.firm and record.firm.subcompany
                                    else ""
                                ),
                                "firm_name": record.firm.name if record.firm else "",
                                "approval_step": (
                                    record.approval_step.name
                                    if record.approval_step
                                    else ""
                                ),
                                "due_at": record.due_at if record.due_at else "",
                            }
                        )

                    record_entries.append(default_entry)

                # Base response data structure
                response_data["columns"][column_id] = {
                    "id": column_id,
                    "title": column_title,
                    "record_count": len(record_entries),
                }

                # Is the result grouped or not?
                if kanban_group_by and kanban_group_by in GROUP_OPTIONS:
                    raw_groups = defaultdict(list)
                    groups_list = []

                    # Process raw groups first for easy manipulation
                    if kanban_group_by in [
                        "record",
                        "type",
                        "kind",
                        "created_by",
                        "occurrence_kind",
                        "occurrence_type",
                    ]:
                        for record_entry in record_entries:
                            key = record_entry[kanban_group_by]
                            if key is None or key == "":
                                key = ITEM_WITHOUT_VALUE_TITLE
                            raw_groups[key].append(record_entry)
                    elif kanban_group_by == "datetime":
                        for record_entry in record_entries:
                            key = record_entry["date"]
                            if key is None:
                                key = ITEM_WITHOUT_VALUE_TITLE
                            raw_groups[key].append(record_entry)
                    elif kanban_group_by == "status":
                        for record_entry in record_entries:
                            key = record_entry["status_name"]
                            if key is None:
                                key = ITEM_WITHOUT_VALUE_TITLE
                            raw_groups[key].append(record_entry)
                    elif kanban_group_by == "firm":
                        for record_entry in record_entries:
                            key = record_entry["firm_name"]
                            if key is None or key == "":
                                key = ITEM_WITHOUT_VALUE_TITLE
                            raw_groups[key].append(record_entry)
                    elif kanban_group_by == "subcompany":
                        for record_entry in record_entries:
                            key = record_entry["subcompany_name"]
                            if key is None or key == "":
                                key = ITEM_WITHOUT_VALUE_TITLE
                            raw_groups[key].append(record_entry)
                    elif kanban_group_by == "due_at":
                        for record_entry in record_entries:
                            key = (
                                record_entry["due_at"].strftime("%d/%m/%y")
                                if isinstance(record_entry["due_at"], datetime)
                                else ""
                            )
                            if key is None or key == "":
                                key = ITEM_WITHOUT_VALUE_TITLE
                            raw_groups[key].append(record_entry)

                    else:
                        raise serializers.ValidationError(
                            "kartado.error.record_panel.invalid_group_by_option"
                        )

                    # Process the raw_groups and morph into the desired structure
                    if raw_groups:
                        groups_list = []
                        positioned_group = None

                        for title, grouped_entries in raw_groups.items():
                            grouped_entries.sort(key=entry_sort_func, reverse=True)
                            group_dict = {
                                "title": title,
                                "record_count": len(grouped_entries),
                                "grouped_by": kanban_group_by,
                                "records": grouped_entries,
                            }

                            if (
                                order_items_without_value
                                and title == ITEM_WITHOUT_VALUE_TITLE
                            ):
                                positioned_group = group_dict
                            else:
                                groups_list.append(group_dict)

                        # Sort groups by title
                        groups_list.sort(key=group_sort_func)

                        # Handle positioned group
                        if positioned_group and order_items_without_value == "start":
                            groups_list.insert(0, positioned_group)
                        elif positioned_group and order_items_without_value == "end":
                            groups_list.append(positioned_group)

                    response_data["columns"][column_id].update({"groups": groups_list})
                else:
                    record_entries.sort(key=entry_sort_func, reverse=True)

                    response_data["columns"][column_id].update(
                        {"records": record_entries}
                    )

            return Response(dict_to_casing(response_data))

        else:
            raise serializers.ValidationError(
                "kartado.error.record_panel.record_panel_type_is_not_kanban"
            )

    @action(methods=["GET"], url_path="Fields", detail=False)
    def get_fields(self, request, pk=None):
        if "company" not in request.query_params.keys():
            raise serializers.ValidationError("É necessário especificar uma company.")

        try:
            company_id = UUID(request.query_params["company"])
        except ValueError:
            raise serializers.ValidationError("badly formed hexadecimal UUID string")

        try:
            company = Company.objects.get(uuid=company_id)
        except Exception:
            raise serializers.ValidationError("Nao foi possivel encontrar a unidade.")

        self.permissions = PermissionManager(
            user=self.request.user,
            company_ids=company_id,
            model="RecordPanel",
        )
        response_fields = get_response(company, self.permissions.all_permissions)

        return Response({"fields": response_fields})

    @action(methods=["GET"], url_path="GZIP", detail=True)
    def get_gzip(self, request, pk=None):
        queryset = self.get_queryset()
        record_panel = get_object_or_404(queryset, pk=pk)

        if not self.permissions:
            user_company = UUID(self.request.query_params["company"])
            self.permissions = PermissionManager(
                user=self.request.user,
                company_ids=user_company,
                model="OccurrenceType",
            )

        can_view_inventory = bool(
            self.permissions.get_specific_model_permision("Inventory", "can_view")
        )
        can_view_reporting = bool(
            self.permissions.get_specific_model_permision("Reporting", "can_view")
        )

        if not (can_view_inventory or can_view_reporting):
            input_queryset = get_occurrence_record_queryset(
                "list", request, None
            ).filter(geometry__isnull=False)
            queryset = apply_conditions_to_query(
                record_panel.conditions, input_queryset
            )

            filtered_queryset = OccurrenceRecordGeoGZIPSerializer.setup_eager_loading(
                OccurrenceRecordFilter(
                    request.GET, queryset=queryset, request=request
                ).qs
            )

            page = self.paginate_queryset(filtered_queryset)
            serialized_queryset = OccurrenceRecordGeoGZIPSerializer(
                page or filtered_queryset, many=True
            )
        else:
            input_queryset = Reporting.objects.filter(
                company_id=self.request.query_params["company"],
                geometry__isnull=False,
            )
            queryset = apply_conditions_to_query(
                record_panel.conditions, input_queryset
            )

            filtered_queryset = ReportingFilter(
                request.GET, queryset=queryset
            ).qs.prefetch_related(*ReportingGeoGZIPSerializer._PREFETCH_RELATED_FIELDS)

            page = self.paginate_queryset(filtered_queryset)
            serialized_queryset = ReportingGeoGZIPSerializer(
                page or filtered_queryset, many=True
            )

        geojson_features = serialized_queryset.data["features"]

        total_count = (
            self.paginator.page.paginator.count
            if page is not None
            else filtered_queryset.count()
        )

        geojson_data = {
            "type": "FeatureCollection",
            "features": geojson_features,
            "meta": get_pagination_info(self.request, total_count),
        }

        json_response = JsonResponse(geojson_data)
        compressed_content = gzip.compress(json_response.content)

        response = HttpResponse(compressed_content, content_type="application/gzip")
        response["Content-Encoding"] = "gzip"
        response[
            "Content-Disposition"
        ] = f'attachment; filename="{record_panel.name}.json"'

        return response

    @action(methods=["GET"], url_path="PBF", detail=True)
    def get_pbf(self, request, pk=None):
        # Get instance without filtering the OccurrenceType queryset
        # WARN: self.get_object() should not be used to avoid double filtering
        queryset = self.get_queryset()
        record_panel = get_object_or_404(queryset, pk=pk)

        # Determine if OccurrenceRecord or Reporting usage
        if not self.permissions:
            user_company = UUID(self.request.query_params["company"])
            self.permissions = PermissionManager(
                user=self.request.user,
                company_ids=user_company,
                model="OccurrenceType",
            )

        can_view_inventory = bool(
            self.permissions.get_specific_model_permision("Inventory", "can_view")
        )
        can_view_reporting = bool(
            self.permissions.get_specific_model_permision("Reporting", "can_view")
        )

        if not (can_view_inventory or can_view_reporting):
            input_queryset = get_occurrence_record_queryset(
                "list", request, None
            ).filter(geometry__isnull=False)
            queryset = apply_conditions_to_query(
                record_panel.conditions, input_queryset
            )
            filtered_queryset = OccurrenceRecordFilter(
                request.GET, queryset=queryset
            ).qs.prefetch_related(
                "parent_action",
                "occurrence_type__occurrencetype_specs__company",
                "occurrence_type",
                "status__status_specs__company",
                "location",
                "city",
                "status",
                "company",
                "monitoring_plan",
                "monitoring_points",
            )
            page = self.paginate_queryset(filtered_queryset)
            serialized_queryset = OccurrenceRecordGeoGZIPSerializer(
                page or filtered_queryset, many=True
            )
        else:
            input_queryset = Reporting.objects.filter(
                company_id=self.request.query_params["company"],
                geometry__isnull=False,
            )
            queryset = apply_conditions_to_query(
                record_panel.conditions, input_queryset
            )
            filtered_queryset = ReportingFilter(
                request.GET, queryset=queryset
            ).qs.prefetch_related(*ReportingGeoGZIPSerializer._PREFETCH_RELATED_FIELDS)
            page = self.paginate_queryset(filtered_queryset)
            serialized_queryset = ReportingGeoGZIPSerializer(
                page or filtered_queryset, many=True
            )

        # Structure the serialized features
        geojson_features = serialized_queryset.data["features"]
        geojson_data = {"type": "FeatureCollection", "features": geojson_features}
        json_response = JsonResponse(geojson_data)
        compressed_content = gzip.compress(json_response.content)

        response = HttpResponse(compressed_content, content_type="application/gzip")
        response["Content-Encoding"] = "gzip"
        response[
            "Content-Disposition"
        ] = f'attachment; filename="{record_panel.name}.json"'

        return response

    @action(detail=True, methods=["POST"])
    def mark_panel_as_seen(self, request, pk=None):
        panel = self.get_object()
        user = request.user
        show_list_entry = RecordPanelShowList.objects.filter(
            panel=panel, user=user
        ).first()

        if show_list_entry:
            show_list_entry.new_to_user = False
            show_list_entry.save()
            return Response({"status": "marked as seen"}, status=status.HTTP_200_OK)

        raise serializers.ValidationError("kartado.error.record_panel.entry_not_found")


class CustomDashboardView(viewsets.ModelViewSet):
    serializer_class = CustomDashboardSerializer
    filterset_class = CustomDashboardFilter
    permissions = None
    permission_classes = [IsAuthenticated, CustomDashboardPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "name",
        "description",
        "created_at",
        "created_by",
        "company",
        "instrument_types",
        "instrument_records",
        "sih_monitoring_points",
        "can_be_viewed_by",
        "can_be_edited_by",
        "sih_monitoring_parameters",
        "hidro_basins",
        "cities",
        "sih_frequency",
    ]

    def get_queryset(self):
        queryset = None
        request_user = self.request.user

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return CustomDashboard.objects.none()

            user_company = UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=request_user,
                    company_ids=user_company,
                    model="CustomDashboard",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, CustomDashboard.objects.none())
            if "default" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    CustomDashboard.objects.filter(
                        Q(company_id=user_company)
                        & (
                            Q(can_be_viewed_by__in=[request_user])
                            | Q(can_be_edited_by__in=[request_user])
                            | Q(created_by=request_user)
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    CustomDashboard.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = CustomDashboard.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class CustomTableView(viewsets.ModelViewSet):
    serializer_class = CustomTableSerializer
    filterset_class = CustomTableFilter
    permissions = None
    permission_classes = [IsAuthenticated, CustomTablePermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "name",
        "description",
        "created_at",
        "created_by",
        "company",
        "instrument_records",
        "sih_monitoring_points",
        "can_be_viewed_by",
        "can_be_edited_by",
        "hidro_basins",
        "cities",
        "sih_frequency",
    ]

    def get_queryset(self):
        queryset = None
        request_user = self.request.user

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return CustomTable.objects.none()

            user_company = UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=request_user,
                    company_ids=user_company,
                    model="CustomTable",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, CustomTable.objects.none())
            if "default" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    CustomTable.objects.filter(
                        Q(company_id=user_company)
                        & (
                            Q(can_be_viewed_by__in=[request_user])
                            | Q(can_be_edited_by__in=[request_user])
                            | Q(created_by=request_user)
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    CustomTable.objects.filter(
                        Q(company_id=user_company)
                        | Q(can_be_viewed_by__in=[request_user])
                        | Q(can_be_edited_by__in=[request_user])
                        | Q(created_by=request_user)
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = CustomTable.objects.filter(
                Q(company__in=user_companies)
                | Q(can_be_viewed_by__in=[request_user])
                | Q(can_be_edited_by__in=[request_user])
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(methods=["get"], url_path="Excel", detail=True)
    def get_excel(self, request, pk=None):
        custom_table = self.get_object()
        # try:
        sih_table = SihTable(table=custom_table)
        excel_url = sih_table.get_excel()

        return Response({"excel_url": excel_url})

    @action(methods=["get"], url_path="Preview", detail=False)
    def get_preview(self, request, pk=None):
        # /OccurrenceRecord/GetHydrology/?company={}&datetime={}
        # company (an uuid) and datetime (in ISOString format) are required.
        # This endpoint returns the values we get from the hidro_api.
        if "company" not in request.query_params.keys():
            raise serializers.ValidationError(
                "Não é possível realizar esta operação sem atributo company."
            )

        try:
            _ = Company.objects.get(pk=request.query_params.get("company"))
        except Exception:
            raise serializers.ValidationError("Company não encontrada.")

        required_args = [
            "line_frequency",
            "start_period",
            "end_period",
            "table_data_series",
            "table_type",
            "dynamic_period_in_days",
        ]
        optional_args = ["additional_columns", "additional_lines"]

        if request.query_params.get("table_type") == "ANALYSIS":
            required_args.append("columns_break")

        if not set(required_args).issubset(request.query_params.keys()):
            raise serializers.ValidationError(
                "kartado.custom_table_preview.required_data_missing"
            )

        raw_data = {a: request.query_params.get(a) for a in required_args}
        for a in optional_args:
            if request.query_params.get(a):
                raw_data[a] = request.query_params.get(a)

        # Adjust for dynamic date - Geral 4 customization
        if raw_data["dynamic_period_in_days"] != "null":
            raw_data["end_period"] = datetime.now().strftime("%Y-%m-%d")
            raw_data["start_period"] = (
                datetime.now() - timedelta(days=int(raw_data["dynamic_period_in_days"]))
            ).strftime("%Y-%m-%d")

        sih_table = SihTable(raw_data=raw_data)

        table_description = sih_table.get_table_description()

        return Response(table_description)


class TableDataSeriesView(viewsets.ModelViewSet):
    serializer_class = TableDataSeriesSerializer
    filterset_class = TableDataSeriesFilter
    permissions = None
    permission_classes = [IsAuthenticated, TableDataSeriesPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "name",
        "kind",
        "operational_position",
        "field_name",
        "company",
        "instrument_type",
        "instrument_record",
        "created_at",
        "created_by",
        "sih_monitoring_parameter",
        "sih_frequency",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return TableDataSeries.objects.none()

            user_company = UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="TableDataSeries",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, TableDataSeries.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    TableDataSeries.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = TableDataSeries.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class DataSeriesView(viewsets.ModelViewSet):
    serializer_class = DataSeriesSerializer
    filterset_class = DataSeriesFilter
    permissions = None
    permission_classes = [IsAuthenticated, DataSeriesPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "name",
        "kind",
        "operational_position",
        "field_name",
        "data_type",
        "json_logic",
        "company",
        "instrument_type",
        "instrument_record",
        "created_at",
        "created_by",
        "sih_monitoring_parameter",
        "sih_frequency",
        "start_date_hydrological_parameters",
        "end_date_hydrological_parameters",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return DataSeries.objects.none()

            user_company = UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="DataSeries",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, DataSeries.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, DataSeries.objects.filter(company_id=user_company)
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = DataSeries.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(methods=["GET"], url_path="Data", detail=True)
    def get_data(self, request, pk=None):
        data_series: DataSeries = self.get_object()
        kind = data_series.kind
        company = Company.objects.get(uuid=request.query_params["company"])
        start_date = request.query_params.get("start_date", None)
        end_date = request.query_params.get("end_date", None)

        if start_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        # The instrument_record is used by all kinds, so it's required for this endpoint to work
        instrument_record = data_series.instrument_record
        if data_series.sih_monitoring_point:
            instrument_record = data_series.sih_monitoring_point

        if not instrument_record:
            raise serializers.ValidationError(
                "kartado.error.data_series.filled_instrument_record_field_required_for_this_endpoint"
            )

        if data_series.kind == data_kinds.SERIES_KIND:
            qs_query = {
                "company": company,
                "form_data__instrument": str(instrument_record.uuid),
            }
            # if json_logic field is filled, use it as filter
            if data_series.json_logic:
                qs_query = {**qs_query, **data_series.json_logic}

            occ_record_query = OccurrenceRecord.objects.filter(**qs_query).order_by(
                "datetime"
            )

            if start_date:
                occ_record_query = occ_record_query.filter(datetime__gte=start_date)
            if end_date:
                occ_record_query = occ_record_query.filter(
                    datetime__lte=end_date + timedelta(days=1)
                )

            if occ_record_query:
                try:
                    occ_record_data = occ_record_query.values_list(
                        data_series.field_name, flat=True
                    ).order_by("datetime")
                except Exception:
                    raise serializers.ValidationError(
                        "kartado.error.data_series.invalid_data_series_field_name"
                    )

                data = [occ_data for occ_data in occ_record_data]

                return Response(data)

        if kind == data_kinds.LOGIC_KIND:
            # Get reading data
            qs_record = (
                OccurrenceRecord.objects.filter(
                    form_data__instrument=str(instrument_record.uuid),
                    occurrence_type__isnull=False,
                )
                .order_by("-datetime")
                .only("occurrence_type", "form_data")
            )

            if start_date:
                qs_record = qs_record.filter(datetime__gte=start_date)
            if end_date:
                qs_record = qs_record.filter(datetime__lte=end_date + timedelta(days=1))

            record = qs_record.first()
            can_apply_logic = record and data_series.json_logic

            if can_apply_logic:
                input_data = {
                    "data": instrument_record.form_data,
                    "reading_data": record.form_data,
                }

                result = apply_json_logic(
                    data_series.json_logic, dict_to_casing(input_data)
                )

                return Response(result)

        if kind in [
            data_kinds.SIH_KIND,
            data_kinds.SIH_LAST_VALUE_KIND,
        ]:
            use_latest_value = kind == data_kinds.SIH_LAST_VALUE_KIND
            sih_frequency = data_series.sih_frequency
            sih_monitoring_parameter = data_series.sih_monitoring_parameter
            if not sih_monitoring_parameter:
                raise serializers.ValidationError(
                    "kartado.error.data_series.filled_sih_monitoring_parameter_field_required_for_sih_kind"
                )

            # Extract the codes
            posto = instrument_record.form_data.get("uposto", None)
            item = sih_monitoring_parameter.form_data.get("uabrev", None)

            # Ensure both OccurrenceRecord have the required code on their form_data
            if posto is None:
                raise serializers.ValidationError(
                    "kartado.error.data_series.code_not_found_on_instrument_record_form_data"
                )
            if item is None:
                raise serializers.ValidationError(
                    "kartado.error.data_series.code_not_found_on_sih_monitoring_parameter_form_data"
                )

            try:
                sih_frequency = data_series.sih_frequency

                if start_date:
                    start_date = start_date.strftime("%d/%m/%Y")
                if end_date:
                    end_date = end_date.strftime("%d/%m/%Y")

                if use_latest_value:
                    today = timezone.now()
                    delta_time = today - timedelta(days=14)
                    start_date = delta_time.strftime("%d/%m/%Y")
                    end_date = None

                if data_series.sih_monitoring_point:
                    start_date = request.query_params.get(
                        "startDateHydrologicalParameters", None
                    )
                    end_date = request.query_params.get(
                        "endDateHydrologicalParameters", None
                    )

                fetched_items = fetch_sih_data(
                    [str(posto)],
                    [str(item)],
                    sih_frequency,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                return Response([])
            else:
                if fetched_items and len(fetched_items) > 0:
                    field_name = to_snake_case(data_series.field_name)

                    # NOTE: Assumes all items have the same fields and that the first item is representative of all of them
                    # See https://kartado.atlassian.net/browse/KTD-2330?focusedCommentId=24001
                    available_keys = fetched_items[0].keys()

                    # Validate that the provided field_name is present on the items
                    if field_name not in available_keys:
                        raise serializers.ValidationError(
                            "kartado.error.data_series.bad_field_name_configuration"
                        )

                    if use_latest_value:
                        # Items sorted from latest to oldest (which means that the first items is always the most recent)
                        sih_response_date_key_dict = {
                            "HOURLY": DATA_HOURLY,
                            "DAILY": DATA_DAILY,
                            "MONTHLY": DATA_MONTHLY,
                        }
                        DATE_KEY = sih_response_date_key_dict[data_series.sih_frequency]
                        sorted_items = sorted(
                            fetched_items,
                            key=lambda x: date_parser.parse(x[DATE_KEY]),
                            reverse=True,
                        )
                        latest_item = sorted_items[0]

                        return Response(latest_item[field_name])
                    else:
                        return Response([item[field_name] for item in fetched_items])

                # containing this field it is determined which endpoint to be called
                if fetched_items and sih_frequency:
                    sih_frequency = data_series.sih_frequency

                    available_keys = fetched_items[0].keys()
                    return Response([item[sih_frequency] for item in fetched_items])

        return Response([])


class InstrumentMapView(ListCacheMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = InstrumentMapSerializer
    filterset_class = InstrumentMapFilter
    permissions = None
    permission_classes = [IsAuthenticated, InstrumentMapPermissions]

    ordering = "uuid"
    ordering_fields = ["uuid", "occurrence_record_dashboards__instrument_type"]

    def extract_date(self):
        try:
            raw_date = self.request.query_params.get("date")
            if raw_date:
                date = datetime.strptime(raw_date, "%Y-%m-%d")
            else:
                date = None
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.instrument_map.invalid_date_format"
            )
        else:
            return date

    def get_serializer_context(self):
        context = super(InstrumentMapView, self).get_serializer_context()

        queryset = self.get_queryset()
        latest_readings = {}

        for obj in queryset:
            # Base filters
            kwargs = {
                "company": str(obj.company.uuid),
                "occurrence_type__isnull": False,
                "instrument_id": str(obj.uuid),
            }

            # Handle date param filter
            date = self.extract_date()
            if date:
                kwargs["datetime__date__lte"] = date

            record = (
                OccurrenceRecord.objects.annotate(
                    instrument_id=KeyTextTransform("instrument", "form_data"),
                    operational_control_kind=F("operational_control__kind"),
                    occurrence_type_name=F("occurrence_type__name"),
                    occurrence_type_form_fields=F("occurrence_type__form_fields"),
                )
                .only(
                    "form_data",
                    "operational_control_id",
                    "occurrence_type_id",
                    "number",
                    "uuid",
                )
                .filter(**kwargs)
                .order_by("-datetime")
                .first()
            )
            latest_readings[str(obj.uuid)] = record

        context.update({"latest_readings": latest_readings})

        return context

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return OccurrenceRecord.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="OccurrenceRecord",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, OccurrenceRecord.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    OccurrenceRecord.objects.filter(
                        company_id=user_company,
                        occurrence_type__occurrence_kind="701",
                        geometry__isnull=False,
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = OccurrenceRecord.objects.filter(
                company__in=user_companies,
                occurrence_type__occurrence_kind="701",
                geometry__isnull=False,
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class SIHMonitoringPointMapView(viewsets.ReadOnlyModelViewSet):
    serializer_class = SIHMonitoringPointMapSerializer
    filterset_class = OccurrenceRecordFilter
    permissions = None
    permission_classes = [IsAuthenticated, SIHMonitoringPointMapPermissions]

    ordering = "uuid"
    ordering_fields = ["uuid"]

    def get_serializer_context(self):
        context = super(SIHMonitoringPointMapView, self).get_serializer_context()

        queryset = self.get_queryset()
        context["view"].get_queryset = None
        context["view"].queryset = queryset

        all_parameters = (
            queryset.annotate(
                monitoring_parameters=KeyTransform(
                    "monitoring_parameters_map", "form_data"
                )
            )
            .filter(monitoring_parameters__isnull=False)
            .values_list("monitoring_parameters", flat=True)
        )
        all_postos = (
            queryset.annotate(
                posto=KeyTransform("uposto", "form_data"),
                monitoring_parameters=KeyTransform(
                    "monitoring_parameters_map", "form_data"
                ),
            )
            .filter(monitoring_parameters__isnull=False)
            .values_list("posto", flat=True)
        )

        unique_parameters = list(
            set([item for sublist in all_parameters for item in sublist])
        )

        all_parameters_dict = {
            str(a.uuid): a
            for a in OccurrenceRecord.objects.filter(uuid__in=unique_parameters)
        }

        context["all_parameters_dict"] = all_parameters_dict

        postos = list(all_postos)

        items = [
            a.form_data["uabrev"]
            for a in all_parameters_dict.values()
            if "uabrev" in a.form_data
        ]

        date_now = datetime.now()
        hour_start = None
        default_format_input = "%Y-%m-%d"
        default_format_output = "%d/%m/%Y"
        request_reading_date = self.request.GET.get("reading_date", None)
        slice_string_date = 10
        frequency = (self.request.GET.get("frequency", DAILY)).upper()

        if request_reading_date:
            slice_string_date = 10

            if len(request_reading_date) > 10:
                dt, hour = str(request_reading_date[:16]).split("T")
                hour_start = hour[:2]
                request_reading_date = dt

            try:
                reading_date = datetime.strptime(
                    request_reading_date[:slice_string_date], default_format_input
                )

                if reading_date.date() == date_now.date():
                    reading_date = reading_date - timedelta(days=1)

                if reading_date.date() > date_now.date():
                    raise serializers.ValidationError(
                        "kartado.error.shi_monitoring_point_map.date_future"
                    )

                start_date = reading_date.strftime(default_format_output)

                if frequency == HOURLY:
                    if not hour_start:
                        hour_start = str(date_now.time())[0:2]
                    end_date = (reading_date + timedelta(days=1)).strftime(
                        default_format_output
                    )
                elif frequency == DAILY:
                    end_date = (reading_date + timedelta(days=1)).strftime(
                        default_format_output
                    )
                elif frequency == MONTHLY:
                    end_date = (reading_date + relativedelta(months=1)).strftime(
                        default_format_output
                    )
            except Exception:
                pass
        else:
            start_date = (date_now - timedelta(days=1)).strftime(default_format_output)
            end_date = date_now.strftime(default_format_output)

        resp = fetch_sih_data(
            postos, items, frequency, start_date, end_date, hour_start
        )

        if frequency == DAILY:
            context[VLR_DAILY] = resp

        elif frequency == HOURLY:
            context[VLR_HOURLY] = resp

        elif frequency == MONTHLY:
            context[VLR_MONTHLY] = resp

        return context

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return OccurrenceRecord.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="OccurrenceRecord",
                )

            company = Company.objects.get(pk=user_company)
            try:
                if "monitoring_point_occurrence_type" in company.metadata:
                    monitoring_point_occurrence_type = company.metadata[
                        "monitoring_point_occurrence_type"
                    ]
                else:
                    monitoring_point_occurrence_type = company.metadata[
                        "monitoringPointOccurrenceType"
                    ]
            except Exception:
                raise serializers.ValidationError(
                    "kartado.error.monitoring_point_occurrence_type.not_found"
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, OccurrenceRecord.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    OccurrenceRecord.objects.filter(
                        Q(company_id=user_company)
                        & (
                            Q(occurrence_record_dashboards__isnull=False)
                            | Q(occurrence_record_data_series__isnull=False)
                            | Q(occurrence_type=monitoring_point_occurrence_type)
                        )
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = OccurrenceRecord.objects.filter(
                Q(company__in=user_companies)
                & (
                    Q(occurrence_record_dashboards__isnull=False)
                    | Q(occurrence_record_data_series__isnull=False)
                    | Q(occurrence_type=monitoring_point_occurrence_type)
                )
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ReportOccurrenceRecordWrittenNotificationPDFView(APIView):
    def post(self, request, occurrence_record_pk):
        occurrence_record = OccurrenceRecord.objects.get(pk=occurrence_record_pk)
        template_name = "occurrence_records/pdf/template_writtenNotification.html"

        pdf = PDFGeneratorWrittenNotification(
            request,
            occurrence_record,
            template_name,
        )
        context = pdf.get_context()

        response = HttpResponse(
            pdf.build_pdf(),
            content_type="application/pdf",
        )

        number = context.get("number", "")
        response["Content-Disposition"] = f'filename="Kartado - Registro {number}.pdf"'

        return response
