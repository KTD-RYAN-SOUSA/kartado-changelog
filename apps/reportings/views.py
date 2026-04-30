import functools
import json
import logging
import operator
import uuid
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from functools import reduce
from operator import __or__ as OR
from typing import Dict, Set, Tuple

import boto3
import pytz
import requests
import sentry_sdk
from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.core.exceptions import ValidationError as FieldValidationError
from django.db.models import (
    BooleanField,
    Case,
    Count,
    Exists,
    F,
    Func,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    TextField,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Concat
from django.db.models.signals import post_delete, post_init, pre_init
from django.http import HttpResponseRedirect
from django.utils import timezone
from django_filters import rest_framework as filters
from django_filters.filters import (
    BooleanFilter,
    CharFilter,
    ChoiceFilter,
    DateFilter,
    NumberFilter,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer as DRFJSONRenderer
from rest_framework.response import Response
from rest_framework_gis.pagination import GeoJsonPagination
from rest_framework_json_api import serializers
from storages.utils import clean_name

from apps.approval_flows.models import ApprovalStep, ApprovalTransition
from apps.companies.models import Company, Firm, SubCompany
from apps.constructions.models import ConstructionProgress
from apps.occurrence_records.models import (
    OccurrenceType,
    RecordPanel,
    RecordPanelShowList,
)
from apps.quality_control.models import QualitySample
from apps.reportings.const import record_menu_choices
from apps.reportings.helpers.default_menus import rebalance_visible_menus_orders
from apps.reportings.helpers.gen.pdf_reporting import PDFGenericGenerator
from apps.reportings.signals import update_created_recuperations_with_relation_on_delete
from apps.service_orders.const import file_choices
from apps.service_orders.helpers.report_config_map_default import (
    get_default_config_map_to_report,
)
from apps.service_orders.models import ProcedureResource
from apps.templates.models import ExportRequest
from apps.templates.notifications import send_email_export_request
from apps.users.models import User
from apps.work_plans.models import Job
from apps.work_plans.signals import update_calculated_fields_after_reporting_deletion
from helpers.apps.antt_attachment_excel_report import AnttAttachmentExcelReport
from helpers.apps.artesp_excel import (
    get_excel_name,
    get_url,
    run_async_artesp_excel_export,
)
from helpers.apps.artesp_excel_compact import (
    get_url_compact,
    run_async_artesp_excel_export_compact,
)
from helpers.apps.ccr_embankments_annex_five_post_protocol import (
    CCREmbankmentsAnnexFivePostProtocol,
    ccr_embankments_annex_five_post_protocol_async_handler,
)
from helpers.apps.ccr_embankments_annex_three import (
    CCREmbankmentsAnnexThree,
    ccr_embankments_annex_three_async_handler,
)
from helpers.apps.ccr_embankments_retaining_structures import (
    CCREmbankmentsRetainingStructures,
    ccr_embankments_retaining_structures_async_handler,
)
from helpers.apps.ccr_embankments_retaining_structures_annex_five import (
    CCREmbankmentsAnnexFive,
    ccr_embankments_annex_five_async_handler,
)
from helpers.apps.ccr_report_access import CCRAccess, ccr_report_access_async_handler
from helpers.apps.ccr_report_action_diagnosis import (
    XlsxHandlerReportActionDiagnosisAnnex6,
    ccr_report_action_diagnosis_annex_6_async_handler,
)
from helpers.apps.ccr_report_antiglare_screens import (
    CCRAntiGlareScreens,
    ccr_report_antiglare_screen_async_handler,
)
from helpers.apps.ccr_report_artesp_oac import (
    CCRArtespOAC,
    ccr_report_artesp_oac_async_handler,
)
from helpers.apps.ccr_report_artesp_surface_drainage_sheets import (
    XlsxHandlerReportSurfaceDrainageSheets,
    ccr_report_surface_drainage_async_handler,
)
from helpers.apps.ccr_report_artesp_surface_drainage_sheets_v2025 import (
    XlsxHandlerReportSurfaceDrainageSheetsv2025,
    ccr_report_surface_drainage_async_handler_v2025,
)
from helpers.apps.ccr_report_building_diagnostics import (
    CCrBuildingDiagnostics,
    ccr_report_building_diagnostics_async_handler,
)
from helpers.apps.ccr_report_building_diagnostics_2025 import (
    CCrBuildingDiagnostics2025,
    ccr_report_building_diagnostics_2025_async_handler,
)
from helpers.apps.ccr_report_building_instalation import (
    CCrBuildingInstalation,
    ccr_report_building_instalation_async_handler,
)
from helpers.apps.ccr_report_buildings import CCRBuilds, ccr_report_builds_async_handler
from helpers.apps.ccr_report_comparative_building import (
    CCrBuildingComparative,
    ccr_report_building_comparative_async_handler,
)
from helpers.apps.ccr_report_comparative_building_2025 import (
    CCrBuildingComparative2025,
    ccr_report_building_comparative_2025_async_handler,
)
from helpers.apps.ccr_report_defenses_oac_anexo_one import (
    CrrSurfaceDrainageAnnexOne,
    ccr_report_oac_annex_one_async_handler,
)
from helpers.apps.ccr_report_defenses_oac_annex_five import (
    CrrSurfaceDrainageAnnexFive,
    ccr_report_oac_annex_five_async_handler,
)
from helpers.apps.ccr_report_defenses_oac_annex_four import (
    CrrSurfaceDrainageAnnexFour,
    ccr_report_oac_annex_four_async_handler,
)
from helpers.apps.ccr_report_defenses_oac_annex_three import (
    CrrSurfaceDrainageAnnexThree,
    ccr_report_oac_annex_three_async_handler,
)
from helpers.apps.ccr_report_defenses_oac_annex_two import (
    CrrDeepDrainageAnnexTwo,
    ccr_report_oac_annex_two_async_handler,
)
from helpers.apps.ccr_report_device_horizontal_signage import (
    CCRReportDeviceHorizontalSignage,
    ccr_report_device_horizontal_signage_async_handler,
)
from helpers.apps.ccr_report_electrical import (
    CCRElectrical,
    ccr_report_electrical_async_handler,
)
from helpers.apps.ccr_report_embankments_retaining_structures_annex_two import (
    CCREmbankmentsRetainingStructuresAnnexTwo,
    ccr_report_embankments_retaining_structures_annex_two_async_handler,
)
from helpers.apps.ccr_report_initial_footbridge import (
    InitialFootbridge,
    ccr_report_initial_footbridge_async_handler,
)
from helpers.apps.ccr_report_initial_oae import (
    InitialOAE,
    ccr_report_initial_oae_async_handler,
)
from helpers.apps.ccr_report_initial_oae_new_version import (
    XlsxHandlerMonitoringOAENewVersion,
    ccr_report_monitoring_oae_new_version_async_handler,
)
from helpers.apps.ccr_report_initial_tunnel import (
    InitialTunnel,
    ccr_report_initial_tunnel_async_handler,
)
from helpers.apps.ccr_report_lighting import (
    CCRLighting,
    ccr_report_lighting_async_handler,
)
from helpers.apps.ccr_report_longitudinal_horizontal_signage import (
    CCRLongitudinalHorizontalSignage,
    ccr_report_longitudinal_horizontal_signage_async_handler,
)
from helpers.apps.ccr_report_metal_defenses import (
    CCRMetalDefenses,
    ccr_report_metal_defenses_async_handler,
)
from helpers.apps.ccr_report_metal_defenses_oae import (
    CCRMetalDefensesOAE,
    ccr_report_metal_defenses_oae_async_handler,
)
from helpers.apps.ccr_report_monitoring_oae import (
    CCRReportMonitoringOAE,
    ccr_report_monitoring_oae_async_handler,
)
from helpers.apps.ccr_report_oac_vii_precarious import (
    OACVIIPrecarious,
    ccr_report_oac_vii_precarious_async_handler,
)
from helpers.apps.ccr_report_oac_vii_regular import (
    OACVIIRegular,
    ccr_report_oac_vii_regular_async_handler,
)
from helpers.apps.ccr_report_oae_i import OAEI, ccr_report_oae_i_async_handler
from helpers.apps.ccr_report_oae_iv import OAEIV, ccr_report_oae_iv_async_handler
from helpers.apps.ccr_report_oae_management import (
    CCRReportOAEManagement,
    ccr_report_oae_management_async_handler,
)
from helpers.apps.ccr_report_ocupations import (
    CCROcupation,
    ccr_report_occupation_async_handler,
)
from helpers.apps.ccr_report_rigid_barrier import (
    CCRRigidBarrier,
    ccr_report_rigid_barrier_async_handler,
)
from helpers.apps.ccr_report_road_markings_horizontal_signage import (
    CCRRoadMarkingsHorizontalSignage,
    ccr_report_road_markings_horizontal_signage_async_handler,
)
from helpers.apps.ccr_report_road_stud_horizontal_signage import (
    CCRReportRoadStudHorizontalSignage,
    ccr_report_road_stud_horizontal_signage_async_handler,
)
from helpers.apps.ccr_report_routine_footbridge import (
    RoutineFootbridge,
    ccr_report_routine_footbridge_async_handler,
)
from helpers.apps.ccr_report_routine_oae import (
    RoutineOAE,
    ccr_report_routine_oae_async_handler,
)
from helpers.apps.ccr_report_routine_tunnel import (
    RoutineTunnel,
    ccr_report_routine_tunnel_async_handler,
)
from helpers.apps.ccr_report_utils.export_utils import (
    get_random_string,
    get_s3,
    get_s3_url,
)
from helpers.apps.ccr_report_utils.image import ReportFormat
from helpers.apps.ccr_report_vertical_signage import (
    CCRVerticalSignage,
    ccr_report_vertical_signage_async_handler,
)
from helpers.apps.ccr_report_zebra_horizontal_signage import (
    CCRReportZebraHorizontalSignage,
    ccr_report_zebra_horizontal_signage_async_handler,
)
from helpers.apps.ccr_services_performed_DS_precarious_annex_7 import (
    ServicesPerformedDSPrecariousAnnex7,
    ccr_services_performed_ds_precarious_annex7_async_handler,
)
from helpers.apps.ccr_services_performed_DS_regular_annex_7 import (
    ServicesPerformedDSRegularAnnex7,
    ccr_services_performed_ds_regular_annex7_async_handler,
)
from helpers.apps.csp import get_csp_class, get_csp_graph_class
from helpers.apps.daily_reports import (
    get_uuids_jobs_user_firms,
    get_uuids_rdos_user_firms,
)
from helpers.apps.excel_elo_report import ExcelEloEndpoint
from helpers.apps.excel_photo_report import ExcelPhotoEndpoint
from helpers.apps.inventory import (
    create_recuperation_from_inspections,
    create_recuperation_items,
    get_mapped_occ_type_uuids,
    return_inventory_fields,
    separate_reportings_by_therapy,
)
from helpers.apps.inventory_schedule import InventoryScheduleEndpoint
from helpers.apps.json_logic import apply_json_logic
from helpers.apps.occurrence_records import apply_conditions_to_query
from helpers.apps.record_filter import normalize_text
from helpers.apps.record_panel import handle_field_name
from helpers.apps.reportings import (
    bulk_edit,
    create_recuperation_reportings_jobs,
    get_bond_occurrence_types,
    get_inspections,
    update_created_recuperations_with_relation,
)
from helpers.apps.spreadsheet import (
    InventorySpreadsheeetEndpoint,
    SpreadsheetEndpoint,
    SpreadsheetResourceEndpoint,
)
from helpers.auth_views import is_mobile
from helpers.dates import date_tz
from helpers.edit_export.edit_export import create_edit_export
from helpers.error_messages import error_message
from helpers.fields import get_nested_fields
from helpers.files import check_endpoint
from helpers.filters import (
    DateFromToRangeCustomFilter,
    DateTzFilter,
    JSONFieldOrderingFilter,
    KeyFilter,
    ListFilter,
    ListRangeFilter,
    UUIDListFilter,
    filter_history,
    queryset_with_timezone,
    reporting_expired_filter,
)
from helpers.histories import bulk_update_with_history
from helpers.images import build_text_dict
from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset
from helpers.serializers import get_obj_serialized
from helpers.signals import DisableSignals
from helpers.strings import (
    COMMON_IMAGE_TYPE,
    check_image_file,
    clean_latin_string,
    dict_to_casing,
    get_obj_from_path,
    keys_to_snake_case,
    resolve_duplicate_name,
    strtobool,
    to_snake_case,
)
from helpers.testing.auth_testing import get_user_token
from helpers.views import format_item_payload
from RoadLabsAPI.settings import credentials

from .models import (
    HistoricalReporting,
    RecordMenu,
    RecordMenuRelation,
    Reporting,
    ReportingBulkEdit,
    ReportingFile,
    ReportingInReporting,
    ReportingMessage,
    ReportingMessageReadReceipt,
    ReportingRelation,
)
from .permissions import (
    InventoryPermissions,
    RecordMenuPermissions,
    ReportingFilePermissions,
    ReportingInReportingPermissions,
    ReportingMessagePermissions,
    ReportingMessageReadReceiptPermissions,
    ReportingPermissions,
    ReportingRelationPermissions,
)
from .serializers import (
    DashboardReportingSerializer,
    InventoryGisIntegrationSerializer,
    LightReportingSerializer,
    RecordMenuSerializer,
    ReportingFileObjectSerializer,
    ReportingFileSerializer,
    ReportingGeoSerializer,
    ReportingGisIntegrationSerializer,
    ReportingInReportingSerializer,
    ReportingMessageReadReceiptSerializer,
    ReportingMessageSerializer,
    ReportingObjectSerializer,
    ReportingRelationSerializer,
    ReportingSerializer,
    ReportingWithInventoryCandidates,
)


class ReportingOrderingFilter(JSONFieldOrderingFilter):
    def get_order_by_fields(self, request, queryset, view):
        ordering = super().get_order_by_fields(request, queryset, view)

        record_panel_order_present = "record_panel" in ordering
        record_panel_filter_present = "record_panel" in request.query_params

        if record_panel_order_present and record_panel_filter_present:
            record_panel = RecordPanel.objects.get(
                uuid=request.query_params["record_panel"]
            )

            # Extract record_panel list_order_by fields
            order_by_fields = [
                (
                    "{}{}".format(
                        "-" if a["order"] == "DESC" else "",
                        handle_field_name(a["field"]),
                    )
                    if "order" in a
                    else handle_field_name(a["field"])
                )
                for a in record_panel.list_order_by
            ]

            return order_by_fields
        elif record_panel_order_present:
            raise serializers.ValidationError(
                "kartado.error.occurrence_record.ordering_by_record_panel_requires_record_panel_filter"
            )
        else:
            return ordering


def get_reporting_queryset(
    action,
    request,
    permissions,
    view=None,
    override_allowed_queryset=None,
):
    queryset = None

    if action in ["list", "spreadsheet_reporting_list"]:
        if "company" not in request.query_params:
            return Reporting.objects.none()

        user_company = uuid.UUID(request.query_params["company"])

        if not permissions:
            permissions = PermissionManager(
                user=request.user, company_ids=user_company, model="Reporting"
            )

        allowed_queryset = (
            override_allowed_queryset or permissions.get_allowed_queryset()
        )

        if "none" in allowed_queryset:
            queryset = join_queryset(queryset, Reporting.objects.none())
        if (
            "self" in allowed_queryset
            or "firm" in allowed_queryset
            or "self_and_created_by_firm" in allowed_queryset
        ):
            user_firms = list(
                (request.user.user_firms.filter(company_id=user_company)).union(
                    request.user.user_firms_manager.filter(company_id=user_company)
                )
            )
            jobs = (
                Job.objects.filter(
                    Q(company_id=user_company)
                    & (
                        Q(worker=request.user)
                        | Q(created_by=request.user)
                        | Q(watcher_users=request.user)
                        | Q(firm__in=user_firms)
                        | Q(watcher_firms__in=user_firms)
                        | Q(watcher_subcompanies__subcompany_firms__in=user_firms)
                    )
                )
                .distinct()
                .values_list("uuid", flat=True)
            )
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    Reporting.objects.filter(
                        Q(created_by=request.user) | Q(job__in=jobs)
                    ),
                )
            if (
                "firm" in allowed_queryset
                or "self_and_created_by_firm" in allowed_queryset
            ):
                # Get users related to the request user's firms
                related_users = User.objects.filter(
                    user_firms__in=user_firms
                ).distinct()

                if "firm" in allowed_queryset:
                    created_by_sub = (
                        User.objects.filter(reportings=OuterRef("uuid"))
                        .order_by()
                        .annotate(
                            user_firm_count=Func(F("user_userinfirm"), function="Count")
                        )
                        .values("user_firm_count")
                    )
                    queryset = join_queryset(
                        queryset,
                        (
                            Reporting.objects.annotate(
                                user_firms_count=Subquery(
                                    created_by_sub, output_field=IntegerField()
                                )
                            )
                            .filter(
                                Q(company_id=user_company)
                                & (
                                    Q(firm__in=user_firms)
                                    | (
                                        Q(created_by__in=related_users)
                                        # & Q(user_firms_count__lte=1)
                                    )
                                    | Q(job__in=jobs)
                                )
                            )
                            .exclude(
                                ~Q(firm__in=user_firms)
                                & ~Q(job__in=jobs)
                                & Q(created_by__in=related_users)
                                & Q(user_firms_count__gt=1)
                            )
                        ),
                    )

                if "self_and_created_by_firm" in allowed_queryset:
                    # Expand user_firms to include firms created by related users
                    related_firms = Firm.objects.filter(
                        created_by__in=related_users
                    ).distinct()
                    user_firms.extend(related_firms)
                    user_firms = list(set(user_firms))

                    # Get users of new related firms and add them to related_users
                    related_firm_users = User.objects.filter(
                        user_firms__in=related_firms
                    ).distinct()
                    related_users = (related_users | related_firm_users).distinct()

                    queryset = join_queryset(
                        queryset,
                        (
                            Reporting.objects.filter(
                                Q(company_id=user_company)
                                & (
                                    Q(firm__in=user_firms)
                                    | Q(created_by__in=related_users)
                                    | Q(job__in=jobs)
                                )
                            )
                        ),
                    )
        if "subcompany" in allowed_queryset:
            subcompany_user_firms = list(
                (request.user.user_firms.filter(company_id=user_company)).union(
                    request.user.user_firms_manager.filter(company_id=user_company)
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
                Reporting.objects.filter(
                    company_id=user_company,
                    firm__in=all_subcompany_firms,
                ),
            )
        if "artesp" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                Reporting.objects.filter(
                    company_id=user_company,
                    form_data__artesp_code__isnull=False,
                ).exclude(form_data__artesp_code__exact=""),
            )
        if "artesp_entrevias" in allowed_queryset:
            try:
                company = Company.objects.get(pk=user_company)
            except Exception:
                queryset = join_queryset(queryset, Reporting.objects.none())
            else:
                queryset_company = Reporting.objects.filter(
                    company_id=user_company
                ).distinct()

                possible_path_kinds = "artesp_exclude__occurrence_kind"
                kinds = get_obj_from_path(company.metadata, possible_path_kinds)

                possible_path_firms = "artesp_exclude__historical_firm"
                firms = get_obj_from_path(company.metadata, possible_path_firms)

                if (
                    kinds
                    and isinstance(kinds, list)
                    and firms
                    and isinstance(firms, list)
                ):
                    histories = HistoricalReporting.objects.filter(
                        history_type="+", firm__in=firms
                    )
                    queryset = join_queryset(
                        queryset,
                        queryset_company.filter(found_at__gte="2020-01-01").exclude(
                            (
                                Q(occurrence_type__occurrence_kind__in=kinds)
                                | Q(historicalreporting__in=histories)
                            )
                            & (
                                Q(form_data__artesp_code__isnull=True)
                                | Q(form_data__artesp_code__exact="")
                            )
                        ),
                    )
                else:
                    queryset = join_queryset(queryset, Reporting.objects.none())

        if "antt_supervisor_agency" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                Reporting.objects.filter(company=user_company, shared_with_agency=True),
            )
        if "supervisor_agency" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                Reporting.objects.filter(
                    Q(company_id=user_company)
                    & (
                        Q(
                            reporting_construction_progresses__construction__origin="AGENCY"
                        )
                        | (
                            Q(form_data__artesp_code__isnull=False)
                            & ~Q(form_data__artesp_code__exact="")
                        )
                    )
                ),
            )
        if "all" in allowed_queryset:
            queryset = join_queryset(
                queryset, Reporting.objects.filter(company_id=user_company)
            )

    # If queryset isn't set by any means above
    if queryset is None:
        user_companies = request.user.companies.all()
        queryset = Reporting.objects.filter(company__in=user_companies)

    return queryset


def needs_distinct_for_reporting(permissions, request) -> bool:
    """
    Check if distinct() needs to be applied to the reporting queryset.
    Only skip distinct() when permission is "all" alone without additional filters.
    """
    if not permissions:
        return True

    allowed_queryset = permissions.get_allowed_queryset()
    query_params_keys = set(request.query_params.keys())
    has_filters = bool(
        query_params_keys
        - {
            "company",
            "page",
            "page_size",
            "sort",
            "record_menu",
            "km",
            "km_reference",
            "updated_at_after",
            "updated_at_before",
        }
    )

    return (allowed_queryset != ["all"]) or has_filters


class ReportingFilter(filters.FilterSet):
    km = ListRangeFilter()
    km_reference = ListRangeFilter()
    any_km_exact = NumberFilter(method="get_any_km_exact")
    uuid = UUIDListFilter()
    exclude_uuid = UUIDListFilter(field_name="uuid", exclude=True)
    created_by = UUIDListFilter()
    occurrence_type = ListFilter(method="get_occurrence_type")
    number_list = ListFilter(method="get_number_list")
    artesp_code = ListFilter(method="get_artesp_code")
    occurrence_kind = ListFilter(field_name="occurrence_type__occurrence_kind")
    exclude_occurrence_kind = ListFilter(
        field_name="occurrence_type__occurrence_kind", exclude=True
    )
    num_jobs = CharFilter(method="get_num_jobs", label="num_jobs")
    job__start_date = DateFromToRangeCustomFilter()
    job__end_date = DateFromToRangeCustomFilter()

    approval_step_changed_date = CharFilter(
        method="get_step_changed_date", label="approval_step_changed_date"
    )
    only_related_to = ListFilter(method="get_only_related_to")
    created_at = DateFromToRangeCustomFilter()
    found_at = DateFromToRangeCustomFilter()
    found_at_within_last_days = filters.NumberFilter(
        method="get_found_at_within_last_days"
    )
    found_at_within_current_month = filters.BooleanFilter(
        method="get_found_at_within_current_month"
    )
    updated_at = DateFromToRangeCustomFilter()
    updated_at_date = DateFilter(field_name="updated_at__date")
    executed_at = DateFromToRangeCustomFilter()
    due_at = DateFromToRangeCustomFilter()

    is_executed = filters.BooleanFilter(
        field_name="executed_at", lookup_expr="isnull", exclude=True
    )
    expired = ListFilter(method="get_expired", label="expired")

    direction = ListFilter()
    lane = ListFilter()
    uf_code = ListFilter(field_name="road__uf")
    firm = UUIDListFilter()
    subcompany = UUIDListFilter(field_name="firm__subcompany")
    equipment = UUIDListFilter(field_name="equipments")
    status = UUIDListFilter()
    job = UUIDListFilter(allow_null=True)
    updated_by_firm = ListFilter(method="get_updated_by_firm")
    measurement = ListFilter(method="get_measurement")
    mobile_sync = ListFilter(method="get_mobile_sync")
    range_kms = ListFilter(method="get_range_kms")
    geom = CharFilter(method="get_geom", label="geom")
    road = UUIDListFilter()
    road_name = ListFilter()
    approval_step = UUIDListFilter()
    search = CharFilter(label="search", method="get_search")
    lot = ListFilter()
    has_artesp_code = filters.BooleanFilter(
        method="get_has_artesp_code", label="has_artesp_code"
    )
    has_image = filters.BooleanFilter(method="get_has_image", label="has_image")
    form_data = KeyFilter(allow_null=True)
    csp = ListFilter(method="get_csp")
    measurement_bulletin = ListFilter(
        field_name="reporting_resources__measurement_bulletin"
    )
    resource = UUIDListFilter(field_name="reporting_resources__resource")

    track = ListFilter()
    branch = ListFilter()
    excel_import = UUIDListFilter(field_name="excel_imports")
    pdf_import = UUIDListFilter()
    parent = UUIDListFilter()
    children = UUIDListFilter()
    active_inspection = UUIDListFilter()
    active_inspection_of_inventory = UUIDListFilter()
    multiple_daily_reports = ListFilter(field_name="reporting_multiple_daily_reports")

    construction = UUIDListFilter(allow_null=True)
    no_construction_progress = filters.BooleanFilter(
        method="get_no_construction_progress", label="no_construction_progress"
    )
    no_construction_progress_include_uuid = ListFilter(
        method="get_no_construction_progress_include_uuid"
    )
    reporting_hole_classification = ListFilter(
        method="filter_according_to_mapped_occ_types", allow_null=True
    )
    reporting_sheet_classification = ListFilter(
        method="filter_according_to_mapped_occ_types", allow_null=True
    )

    # Inventory filters
    functional_classification = ListFilter(
        field_name="active_inspection__form_data__functional_classification"
    )
    structural_classification = ListFilter(
        field_name="active_inspection__form_data__structural_classification"
    )
    wear_classification = ListFilter(
        field_name="active_inspection__form_data__wear_classification"
    )
    hole_classification = ListFilter(
        method="filter_according_to_mapped_occ_types", allow_null=True
    )
    sheet_classification = ListFilter(
        method="filter_according_to_mapped_occ_types", allow_null=True
    )

    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")
    record_panel = CharFilter(method="apply_record_panel_conditions")
    record_menu = UUIDListFilter(field_name="menu")
    created_recuperations = filters.BooleanFilter(method="get_created_recuperations")

    shared_with_agency = filters.BooleanFilter(method="get_shared_with_agency")
    has_multiple_daily_report = filters.BooleanFilter(
        field_name="reporting_multiple_daily_reports",
        lookup_expr="isnull",
        exclude=True,
        distinct=True,
    )

    has_resource = filters.BooleanFilter(method="get_has_resource")

    inventory_jobs_start_date = DateFromToRangeCustomFilter(
        method="get_inventory_jobs_start_date"
    )

    inventory_jobs_end_date = DateFromToRangeCustomFilter(
        method="get_inventory_jobs_end_date"
    )

    inventory_jobs_progress = filters.RangeFilter(method="get_inventory_jobs_progress")

    class Meta:
        model = Reporting
        fields = {"company": ["exact"], "number": ["exact"]}

    def get_occurrence_type(self, queryset, name, value):
        ids = value.split(",")
        if self.request:
            company_id = uuid.UUID(self.request.query_params["company"])

            occ_types = OccurrenceType.objects.filter(company=company_id).values_list(
                "uuid", "previous_version_id"
            )
        else:
            occ_types = OccurrenceType.objects.filter(
                reporting_occurrence__in=queryset
            ).values_list("uuid", "previous_version_id")

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

        return queryset.filter(occurrence_type_id__in=list_ids).distinct()

    def get_number_list(self, queryset, name, value):
        number_list = [item for item in value.replace(" ", "").split(",") if item]

        return queryset.filter(
            functools.reduce(
                lambda acc, x: acc | Q(number__icontains=x), number_list, Q()
            )
        ).distinct()

    def get_artesp_code(self, queryset, name, value):
        codes = [item.strip() for item in value.split(",") if item.strip()]

        return queryset.filter(
            functools.reduce(
                lambda acc, x: acc | Q(form_data__artesp_code__icontains=x), codes, Q()
            )
        ).distinct()

    def get_has_image(self, queryset, name, value):
        q_params = Q()
        # Add params for known image files
        for image_type in COMMON_IMAGE_TYPE:
            q_params |= Q(upload__iendswith=image_type)
        image_reporting_files_subquery = ReportingFile.objects.filter(
            q_params, reporting=OuterRef("pk")
        )

        if value is True or value is False:
            return (
                queryset.annotate(
                    has_image_reporting_files=Exists(image_reporting_files_subquery)
                )
                .filter(has_image_reporting_files=value)
                .distinct()
            )
        else:
            return queryset

    def get_has_artesp_code(self, queryset, name, value):
        if value is True:
            return queryset.filter(form_data__artesp_code__isnull=False).exclude(
                form_data__artesp_code__exact=""
            )
        elif value is False:
            return queryset.filter(form_data__artesp_code__isnull=True)
        else:
            return queryset

    def get_step_changed_date(self, queryset, name, value):
        if not value:
            return queryset

        value = date_tz(value).replace(hour=7, minute=30)
        old_value = value - timedelta(days=7)

        return filter_history(
            old_value, value, "approval_step_id", HistoricalReporting, queryset
        )

    def get_only_related_to(self, queryset, name, value):
        """
        Reportings if the user is the created_by or
        he has changed the reporting in the past
        """
        values = value.split(",")

        histories = HistoricalReporting.objects.filter(
            uuid__in=queryset, history_user_id__in=values
        ).values_list("uuid", flat=True)

        return queryset.filter(
            Q(uuid__in=histories) | Q(created_by_id__in=values)
        ).distinct()

    def get_found_at_within_last_days(self, queryset, name, value):
        try:
            int_value = int(value)
        except Exception:
            raise ValidationError("kartado.error.filter.needs_to_be_integer")

        return queryset.filter(
            found_at__gte=timezone.now() - timedelta(days=int_value),
            found_at__lte=timezone.now(),
        )

    def get_found_at_within_current_month(self, queryset, name, value):
        current_date = timezone.now()
        conditions = {
            "found_at__month": current_date.month,
            "found_at__year": current_date.year,
        }

        if value:
            return queryset.filter(**conditions)
        return queryset.exclude(**conditions)

    def get_csp(self, queryset, name, value):
        csp = value.split(",")
        or_conditions = reduce(
            operator.or_,
            (
                (
                    Q(
                        occurrence_type__form_fields__fields__contains=[
                            {"apiName": "csp"},
                            {"logic": item},
                        ]
                    )
                    | Q(
                        occurrence_type__form_fields__fields__contains=[
                            {"apiName": "csp"},
                            {"logic": float(item)},
                        ]
                    )
                    | Q(
                        occurrence_type__form_fields__fields__contains=[
                            {"api_name": "csp"},
                            {"logic": item},
                        ]
                    )
                    | Q(
                        occurrence_type__form_fields__fields__contains=[
                            {"api_name": "csp"},
                            {"logic": float(item)},
                        ]
                    )
                )
                for item in csp
            ),
        )
        return queryset.filter(or_conditions)

    def get_search(self, queryset, name, value):
        """
        Optimized search filter using the pre-normalized keywords field with trigram indexing.

        This implementation uses the pre-computed keywords field which now includes
        all searchable data (form_data translations, number, occurrence_type, road, km, etc.)
        already normalized (no accents, lowercase) for efficient index usage.
        """

        # Clean and split search terms
        search_terms = [term.strip() for term in value.strip().split() if term.strip()]

        if not search_terms:
            return queryset

        # Build search condition: all terms must be found in keywords field
        # Normalize search terms to match the normalized keywords in the database
        q_keywords = Q()
        for term in search_terms:
            if len(term) >= 2:  # Avoid very short terms
                normalized_term = normalize_text(term)
                q_keywords &= Q(keywords__contains=normalized_term)

        return queryset.filter(q_keywords)

    def get_geom(self, queryset, name, value):
        if value:
            try:
                # xmin, ymin, xmax, ymax (like Point which is x,y)
                bbox = [float(item) for item in value.split(",")]
                geom = Polygon.from_bbox(bbox)
                return queryset.filter(point__within=geom)
            except Exception:
                return queryset

    def get_num_jobs(self, queryset, name, value):
        company_id = uuid.UUID(self.request.query_params["company"])

        firms = Firm.objects.filter(company_id=company_id).prefetch_related("firm_jobs")
        jobs = (
            Job.objects.filter(firm__in=firms)
            .order_by("-start_date")[0 : int(value)]
            .prefetch_related("reportings")
        )

        return queryset.filter(job__in=jobs).distinct()

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        jobs_section, rdos_section = value.split("|")

        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        jobs_uuids = get_uuids_jobs_user_firms(jobs_section, company, self.request.user)
        rdos_uuids = get_uuids_rdos_user_firms(rdos_section, company, self.request.user)

        return queryset.filter(
            Q(job_id__in=jobs_uuids)
            | Q(reporting_multiple_daily_reports__in=rdos_uuids)
        ).distinct()

    def get_num_jobs_only_user_firms(self, queryset, name, value):
        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        jobs_values = value.split(",")
        num_jobs = jobs_values.pop(0)
        user_firms = self.request.user.user_firms.all()
        if "num_jobs" in company.metadata:
            num_jobs = int(company.metadata["num_jobs"])

        max_reportings_by_job = int(company.metadata.get("max_reportings_by_job", 250))

        jobs_by_count = (
            Job.objects.filter(
                firm__in=user_firms,
                archived=False,
                reporting_count__lte=max_reportings_by_job,
            )
            .order_by("-start_date")[0 : int(num_jobs)]
            .values_list("uuid", flat=True)
        )
        jobs_by_ids = Job.objects.filter(
            uuid__in=jobs_values,
            archived=False,
            reporting_count__lte=max_reportings_by_job,
        ).values_list("uuid", flat=True)

        return queryset.filter(
            Q(job_id__in=jobs_by_count) | Q(job_id__in=jobs_by_ids)
        ).distinct()

    def get_num_user_firms(self, queryset, name, value):
        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        firms_values = value.split(",")
        num_firms = firms_values.pop(0)
        if "num_firms" in company.metadata:
            num_firms = int(company.metadata["num_firms"])

        firms_by_count = (
            Firm.objects.filter(company=company, users__in=[self.request.user])
            .order_by("name")[: int(num_firms)]
            .values_list("uuid", flat=True)
        )

        firms_by_ids = Firm.objects.filter(
            uuid__in=firms_values, company=company
        ).values_list("uuid", flat=True)

        return queryset.filter(
            Q(reporting_multiple_daily_reports__firm__in=firms_by_count)
            | Q(reporting_multiple_daily_reports__firm__in=firms_by_ids)
        ).distinct()

    def get_mobile_sync(self, queryset, name, value):
        values = value.split(",")
        return queryset.filter(
            historicalreporting__mobile_sync_id__in=values
        ).distinct()

    def get_updated_by_firm(self, queryset, name, value):
        values = value.split(",")
        histories = HistoricalReporting.objects.filter(firm__in=values).exclude(
            history_type="-"
        )
        reporting_ids = histories.values_list("uuid", flat=True)
        return queryset.filter(uuid__in=reporting_ids)

    def get_measurement(self, queryset, name, value):
        values = value.split(",")
        return queryset.filter(reporting_usage__measurement__in=values).distinct()

    def get_range_kms(self, queryset, name, value):
        if not value:
            return queryset

        values = value.split(",")

        if len(values) % 2 != 0:
            raise ValidationError("O Filtro deve ter um tamanho total par.")

        isdigit = [item.replace(".", "").isdigit() for item in values]
        if all(isdigit):
            values_list = [float(item) for item in values]
        else:
            raise ValidationError("Dados inválidos.")

        conditions = []

        for i in range(len(values_list) - 1):
            if i % 2 == 0:
                min_km = values_list[i]
                max_km = values_list[i + 1]
                conditions.append(
                    (
                        Q(km__gte=min_km)
                        & Q(km__lte=max_km)
                        & Q(end_km__gte=min_km)
                        & Q(end_km__lte=max_km)
                    )
                )

        return queryset.filter(reduce(OR, conditions)).distinct()

    def get_expired(self, queryset, name, value):
        return reporting_expired_filter(queryset, value)

    def get_no_construction_progress(self, queryset, name, value):
        annotated_queryset = queryset.annotate(
            progresses=Count("reporting_construction_progresses", distinct=True)
        )
        if value is True:
            return annotated_queryset.filter(progresses=0)
        elif value is False:
            return annotated_queryset.filter(progresses__gt=0)
        else:
            return queryset

    def get_no_construction_progress_include_uuid(self, queryset, name, value):
        annotated_queryset = queryset.annotate(
            progresses=Count("reporting_construction_progresses", distinct=True)
        )

        return annotated_queryset.filter(
            Q(progresses=0) | Q(uuid__in=value.split(","))
        ).distinct()

    def apply_record_panel_conditions(self, queryset, name, value):
        try:
            record_panel_id = uuid.UUID(value)
            record_panel = RecordPanel.objects.get(uuid=record_panel_id)
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.reporting.reporting_filter_requires_a_valid_existing_uuid"
            )

        return apply_conditions_to_query(
            record_panel.conditions,
            queryset,
            menu=record_panel.menu,
            default_to_empty=False,
        )

    def get_shared_with_agency(self, queryset, name, value):
        criteria = (
            Q(shared_with_agency=True)
            | Q(form_data__artesp_code__isnull=False)
            | Q(reporting_construction_progresses__construction__origin="AGENCY")
        )

        if value is True:
            return queryset.filter(criteria)
        elif value is False:
            return queryset.exclude(criteria)
        else:
            return queryset

    def filter_according_to_mapped_occ_types(self, queryset, name, value):
        if self.request:
            company_id = self.request.query_params["company"]
            company = Company.objects.get(uuid=company_id)
        elif queryset:
            company = queryset.first().company
        else:
            return queryset
        _, targets = get_mapped_occ_type_uuids(company)
        actual_name = name.replace("reporting_", "")  # For /Reporting filters
        values = value.split(",")
        criteria = Q()  # Init value to allow operations
        has_null = "null" in values
        if has_null:
            values.remove("null")

        # /Reporting
        if name == "reporting_hole_classification":
            direct_targets = Q(occurrence_type__in=targets)
            nested_targets = Q(
                reporting_relation_parent__child__occurrence_type__in=targets
            )
            direct_path = f"form_data__{actual_name}"
            nested_path = f"reporting_relation_parent__child__form_data__{actual_name}"

            if values:
                criteria = (direct_targets & Q(**{f"{direct_path}__in": values})) | (
                    nested_targets & Q(**{f"{nested_path}__in": values})
                )
            if has_null:
                criteria = (
                    criteria
                    | (direct_targets & Q(**{f"{direct_path}__isnull": True}))
                    | (nested_targets & Q(**{f"{nested_path}__isnull": True}))
                )
        elif name == "reporting_sheet_classification":
            path = f"form_data__{actual_name}"
            base_q = Q(occurrence_type__in=targets) & Q(
                occurrence_type__form_fields__fields__contains=[
                    {"apiName": "sheetClassification"}
                ]
            )

            if values:
                criteria = base_q & Q(**{f"{path}__in": values})
            if has_null:
                criteria = criteria | (base_q & Q(**{f"{path}__isnull": True}))

        # /Inventory
        elif name == "hole_classification":
            direct_targets = Q(children__occurrence_type__in=targets)
            nested_targets = Q(
                children__reporting_relation_parent__child__occurrence_type__in=targets
            )
            direct_path = f"children__form_data__{name}"
            nested_path = (
                f"children__reporting_relation_parent__child__form_data__{name}"
            )

            if values:
                criteria = (direct_targets & Q(**{f"{direct_path}__in": values})) | (
                    nested_targets & Q(**{f"{nested_path}__in": values})
                )
            if has_null:
                criteria = (
                    criteria
                    | (direct_targets & Q(**{f"{direct_path}__isnull": True}))
                    | (nested_targets & Q(**{f"{nested_path}__isnull": True}))
                )
        elif name == "sheet_classification":
            path = f"children__form_data__{name}"
            base_q = Q(children__occurrence_type__in=targets) & Q(
                children__occurrence_type__form_fields__fields__contains=[
                    {"apiName": "sheetClassification"}
                ]
            )

            if values:
                criteria = base_q & Q(**{f"{path}__in": values})
            if has_null:
                criteria = criteria | (base_q & Q(**{f"{path}__isnull": True}))
        else:
            raise ValueError("The provided filter name is not supported by this method")

        return queryset.filter(criteria) if criteria else queryset

    def get_created_recuperations(self, queryset, name, value):
        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])
        inspection_occurrence_kind = get_obj_from_path(
            company.metadata, "inspection_occurrence_kind"
        )
        if inspection_occurrence_kind:
            if isinstance(inspection_occurrence_kind, str):
                inspection_occurrence_kind = [inspection_occurrence_kind]
            if value is True:
                empty_list = [[], [{}]]
                return queryset.filter(
                    occurrence_type__occurrence_kind__in=inspection_occurrence_kind,
                    created_recuperations_with_relation=None,
                    form_data__has_key="therapy",
                ).exclude(form_data__therapy__in=empty_list)
            elif value is False:
                return queryset.filter(
                    Q(created_recuperations_with_relation=True)
                    | Q(created_recuperations_with_relation=False),
                    occurrence_type__occurrence_kind__in=inspection_occurrence_kind,
                ).distinct()
        else:
            return queryset.none()

    def get_has_resource(self, queryset, name, value):
        ann_queryset = queryset.annotate(
            has_resource=Case(
                When(reporting_resources__isnull=False, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )
        if value is True:
            return ann_queryset.filter(has_resource=True).distinct()
        elif value is False:
            return ann_queryset.filter(has_resource=False).distinct()
        else:
            return queryset

    def get_any_km_exact(self, queryset, name, value):
        if not value:
            return queryset

        try:
            value = float(value)
        except ValueError:
            raise ValidationError("kartado.error.reporting.value_is_not_a_float_number")

        return queryset.filter(Q(km=value) | Q(end_km=value)).distinct()

    def get_filtered_jobs(self, queryset, filters=None):
        if not filters:
            return set()

        qs = Job.objects.filter(parent_inventory__in=queryset).distinct()
        filtered_job_sets = []

        for field in ["start_date", "end_date", "progress"]:
            if field in filters:
                filtered_job_sets.append(
                    self._filter_by_range(qs, filters[field], field)
                )

        return set.intersection(*filtered_job_sets) if filtered_job_sets else set()

    def _filter_by_range(self, qs, value, field):
        filter_kwargs = Q()

        if field.endswith("_date"):
            qs = queryset_with_timezone(qs, field, f"new_{field}")
            field = f"new_{field}"

            if value.start and isinstance(value.start, datetime):
                filter_kwargs &= Q(
                    **{f"{field}__gte": value.start.replace(tzinfo=pytz.UTC)}
                )
            if value.stop and isinstance(value.stop, datetime):
                filter_kwargs &= Q(
                    **{f"{field}__lte": value.stop.replace(tzinfo=pytz.UTC)}
                )

        elif field == "progress":
            if value.start is not None:
                filter_kwargs &= Q(progress__gte=value.start)
            if value.stop is not None:
                filter_kwargs &= Q(progress__lte=value.stop)

        return set(qs.filter(filter_kwargs).values_list("uuid", flat=True))

    def _update_request_filters(self, field, value):
        if not hasattr(self.request, "_inventory_job_filters"):
            self.request._inventory_job_filters = {}
        self.request._inventory_job_filters[field] = value

    def get_inventory_jobs(self, queryset, field, value):
        self._update_request_filters(field, value)
        filters = self.request._inventory_job_filters

        if len(filters) > 1:
            matching_jobs = self.get_filtered_jobs(queryset, filters)
            return queryset.filter(inventory_jobs__uuid__in=matching_jobs).distinct()

        return queryset.filter(
            inventory_jobs__in=self._filter_by_range(
                Job.objects.filter(parent_inventory__in=queryset).distinct(),
                value,
                field,
            )
        ).distinct()

    def get_inventory_jobs_start_date(self, queryset, name, value):
        return self.get_inventory_jobs(queryset, "start_date", value)

    def get_inventory_jobs_end_date(self, queryset, name, value):
        return self.get_inventory_jobs(queryset, "end_date", value)

    def get_inventory_jobs_progress(self, queryset, name, value):
        return self.get_inventory_jobs(queryset, "progress", value)


class ReportingView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ReportingPermissions]
    filter_backends = [
        filters.DjangoFilterBackend,
        ReportingOrderingFilter,
    ]
    filterset_class = ReportingFilter
    permissions = None
    authentication_types = ["spreadsheetOnly", "all"]
    # Manually setting resource_name because we use the JSON API renderer manually
    # in services_functions
    resource_name = "Reporting"

    ordering_fields = [
        "uuid",
        "firm__name",
        "number",
        "road_name",
        "km",
        "project_km",
        "direction",
        "lane",
        "status__name",
        "occurrence_type__name",
        "executed_at",
        "due_at",
        "found_at",
        "created_at",
        "updated_at",
        "road__name",
        "created_by__first_name",
        "approval_step__name",
        "job__number",
        "job__start_date",
        "job__end_date",
        "construction",
        "record_panel",
        "firm__subcompany__name",
        "menu__name",
        "parent__number",
    ]
    ordering = "uuid"

    def get_serializer_context(self):
        context = super(ReportingView, self).get_serializer_context()
        user = context["request"].user
        permissions = context["view"].permissions

        # The current user is not anonymous and the action is list or retrieve
        if not user.is_anonymous and self.action in ["list", "retrieve"]:
            try:
                if permissions:
                    context.update(
                        {
                            "user_firms": user.user_firms.filter(
                                company_id=permissions.company_id
                            )
                        }
                    )
            except AttributeError as err:
                # Send the exception to Sentry
                sentry_sdk.capture_exception(err)

            # Inform the serializer that we're dealing with antt queryset
            antt_qs_name = "antt_supervisor_agency"
            context[antt_qs_name] = (
                antt_qs_name in permissions.get_allowed_queryset()
                if permissions
                else False
            )

        return context

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update"]:
            return ReportingObjectSerializer
        elif self.action in [
            "spreadsheet_reporting_list",
            "spreadsheeet_inventory_list",
        ]:
            return LightReportingSerializer
        return ReportingSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = get_reporting_queryset(
            self.action,
            self.request,
            self.permissions,
            self,
        ).exclude(occurrence_type__occurrence_kind="2")

        if needs_distinct_for_reporting(self.permissions, self.request):
            queryset = queryset.distinct()
        return self.get_serializer_class().setup_eager_loading(queryset)

    def get_queryset_zip(self):
        queryset = get_reporting_queryset(
            self.action,
            self.request,
            self.permissions,
            self,
        )

        if needs_distinct_for_reporting(self.permissions, self.request):
            queryset = queryset.distinct()
        return self.get_serializer_class().setup_eager_loading(queryset)

    @action(methods=["get"], url_path="Hidden", detail=False)
    def get_hidden(self, request, pk=None):
        if "company" not in request.query_params:
            return Response({"type": "ReportingHidden", "attributes": {"count": None}})

        try:
            queryset = self.get_queryset().filter(
                company=request.query_params["company"],
                due_at__lte=datetime.now(),
            )

            data = request.query_params.copy()
            to_pop = []
            for key in data.keys():
                if key in ["due_at_before", "due_at_after", "is_expired"]:
                    to_pop.append(key)
            for key in to_pop:
                data.pop(key)

            filters = self.filterset_class(data=data, request=request)
            if filters.is_valid():
                filtered_queryset = filters.filter_queryset(queryset)
                return Response(
                    {
                        "type": "ReportingHidden",
                        "attributes": {
                            "count": queryset.count() - filtered_queryset.count()
                        },
                    }
                )
            else:
                raise Exception()
        except Exception:
            return Response({"type": "ReportingHidden", "attributes": {"count": None}})

    @action(methods=["delete", "post"], url_path="Bulk", detail=False)
    def bulk(self, request, pk=None):
        # get reportings
        reporting_ids_list = [
            reporting["id"] for reporting in request.data.pop("reportings", [])
        ]
        reportings = Reporting.objects.filter(
            pk__in=reporting_ids_list
        ).prefetch_related(*ReportingSerializer._PREFETCH_RELATED_FIELDS)

        # check if all reportings are editable
        if not all(reportings.values_list("editable", flat=True)):
            raise ValidationError("kartado.error.reporting_bulk.not_editable")

        if request.method.lower() == "post" and reportings:

            instance = ReportingBulkEdit.objects.create(
                edit_data=request.data, updated_by=request.user
            )
            instance.reportings.add(*reportings)
            bulk_edit(str(instance.pk))

        if request.method.lower() == "delete" and reportings:
            # Job instances to update after deleting the reportings to avoid signal explosion
            # NOTE: Job was prefetched beforehand
            jobs_to_update = list(
                set(reporting.job for reporting in reportings if reporting.job)
            )

            post_delete.disconnect(
                update_calculated_fields_after_reporting_deletion, sender=Reporting
            )
            post_delete.disconnect(
                update_created_recuperations_with_relation_on_delete, sender=Reporting
            )

            company = reportings[0].company
            inspections = set(get_inspections(reportings, company))
            reportings.delete()
            update_created_recuperations_with_relation(inspections, company)

            post_delete.connect(
                update_created_recuperations_with_relation_on_delete, sender=Reporting
            )
            post_delete.connect(
                update_calculated_fields_after_reporting_deletion, sender=Reporting
            )
            with DisableSignals(disabled_signals=[pre_init, post_init]):
                # Update the unique Job instances' calculated fields
                for job in jobs_to_update:
                    job.save()

        return error_message(200, "OK")

    @action(methods=["GET"], url_path="ZipPicture", detail=False)
    def zip_pictures(self, request, pk=None):
        # Get fields
        watermark_fields = request.query_params.get("fields", None)

        try:
            use_file_location = strtobool(
                request.query_params.get("use_file_location", "False")
            )
        except Exception:
            use_file_location = False

        if watermark_fields:
            possible_fields = [
                "notes",
                "coordinates_dms",
                "coordinates_dec",
                "coordinates_xyz",
                "direction",
                "date",
                "date_and_hour",
                "road",
                "number",
                "status",
                "classe",
                "executed_at",
                "executed_at_with_hour",
            ]
            fields = watermark_fields.split(",")
            watermark_fields = [x.lower().strip() for x in fields]
            if not set(watermark_fields).issubset(possible_fields):
                raise ValidationError("Filtro não disponível.")

        font_size = request.query_params.get("font_size", "medium")

        # Validate group_by parameter
        group_by = request.query_params.get("group_by", "serial")
        VALID_GROUP_BY_OPTIONS = ["serial", "classe", "road", "none"]
        if group_by not in VALID_GROUP_BY_OPTIONS:
            group_by = "serial"

        filtered_qs = self.filter_queryset(self.get_queryset_zip())
        company = filtered_qs.first().company
        company_name = company.name.replace("/", "_")
        has_roads = company.company_roads.exists()
        nomenclature = request.query_params.get("nomenclature", "")

        if nomenclature:
            nomenclature_parts = [
                part.strip().lower() for part in nomenclature.split(",")
            ]
            if not has_roads and "road" in nomenclature_parts:
                nomenclature_parts = [
                    part for part in nomenclature_parts if part != "road"
                ]
            if "road" in nomenclature_parts and "km" not in nomenclature_parts:
                road_index = nomenclature_parts.index("road")
                nomenclature_parts.insert(road_index + 1, "km")
            nomenclature_fields = nomenclature_parts
        else:
            if has_roads:
                nomenclature_fields = ["classe", "road", "km"]
            else:
                nomenclature_fields = ["classe", "km"]

        files = (
            ReportingFile.objects.filter(reporting__in=filtered_qs)
            .prefetch_related(
                "reporting",
                "reporting__occurrence_type",
                "reporting__company",
                "reporting__road",
            )
            .distinct()
        )

        json_list = []
        used_names_by_serial = {}

        file_count = 0
        for file_obj in files:
            file_count += 1
            if file_obj.upload:
                file_path = file_obj.upload.url.split("?")[0].split(".com/")[1]
                bucket_name = file_obj.upload.url.split(".s3")[0].split("/")[-1]

                if not check_image_file(file_path):
                    continue

                image_name_parts = []

                for field in nomenclature_fields:
                    field_value = ""
                    if field == "number":
                        field_value = (
                            file_obj.reporting.number
                            or str(file_obj.reporting.uuid)[:8]
                        )
                    elif field == "classe":
                        field_value = file_obj.reporting.occurrence_type.name
                    elif field == "road":
                        if file_obj.reporting.road:
                            field_value = file_obj.reporting.road.name or ""
                        else:
                            field_value = file_obj.reporting.road_name or ""
                    elif field == "km":
                        if use_file_location and file_obj.km:
                            field_value = format(
                                round(float(file_obj.km), 3), ".3f"
                            ).replace(".", "+")
                        else:
                            field_value = format(
                                round(float(file_obj.reporting.km), 3), ".3f"
                            ).replace(".", "+")
                    elif field == "date":
                        if file_obj.reporting.found_at:
                            field_value = file_obj.reporting.found_at.strftime(
                                "%Y-%m-%d"
                            )
                        else:
                            field_value = ""
                    elif field == "kind":
                        field_value = file_obj.kind if file_obj.kind else ""
                    elif field == "artespregister":
                        artesp_register_field = get_obj_from_path(
                            company.metadata, "artesp_register_zip", default_return=""
                        )
                        field_value = ""

                        if isinstance(artesp_register_field, str):
                            artesp_register_field_value = get_obj_from_path(
                                file_obj.reporting.form_data, artesp_register_field
                            )
                            if artesp_register_field_value is not None:
                                field_value = str(artesp_register_field_value)

                        field_value = field_value or ""

                    if field_value:
                        field_value = clean_latin_string(field_value).replace("/", "_")
                        image_name_parts.append(field_value)

                base_name = "-".join(image_name_parts) if image_name_parts else "image"
                if len(base_name) > 120:
                    base_name = base_name[:119] + "_"

                reporting_serial = (
                    file_obj.reporting.number or str(file_obj.reporting.uuid)[:8]
                )
                if reporting_serial not in used_names_by_serial:
                    used_names_by_serial[reporting_serial] = {}

                final_name = resolve_duplicate_name(
                    base_name, used_names_by_serial[reporting_serial]
                )

                # Calculate group_key based on group_by parameter
                group_key = None
                skip_image = False
                error_message = None

                if group_by == "classe":
                    occurrence_type = file_obj.reporting.occurrence_type
                    if occurrence_type:
                        group_key = str(occurrence_type.name)
                    else:
                        skip_image = True
                        error_message = "Classe (occurrence_type) não definida"

                elif group_by == "road":
                    road = file_obj.reporting.road
                    if road:
                        group_key = str(road.name)
                    elif file_obj.reporting.road_name:
                        group_key = str(file_obj.reporting.road_name)
                    else:
                        skip_image = True
                        error_message = "Rodovia (road) não definida"

                elif group_by == "serial":
                    reporting_number = file_obj.reporting.number
                    if reporting_number:
                        group_key = str(reporting_number)
                    else:
                        skip_image = True
                        error_message = "Serial (number) não definido, usando UUID"

                elif group_by == "none":
                    group_key = None

                text_dict = {}
                if watermark_fields:
                    text_dict = build_text_dict(
                        file_obj, watermark_fields, use_file_location, company
                    )

                json_temp = {
                    "bucket_name": bucket_name,
                    "file_path": file_path,
                    "original_file_name": file_obj.upload.name,
                    "text_dict": text_dict,
                    "font_size": font_size,
                    "image_name": final_name,
                    "group_key": group_key,
                }

                # Add optional fields only if necessary
                if skip_image:
                    json_temp["skip_image"] = skip_image
                if error_message:
                    json_temp["error"] = error_message

                json_list.append(json_temp)

        if file_count == 0:
            raise ValidationError(
                "kartado.error.reporting.no_files_in_zip_picture_export"
            )

        json_final = {
            "data": json_list,
            "nomenclature_fields": nomenclature_fields,
            "group_by": group_by,
        }
        obj = ExportRequest.objects.create(
            company=company, created_by=request.user, json_zip=json_final
        )

        expires = timedelta(days=1)
        json_final["uuid"] = str(obj.pk)
        json_final["company_name"] = company_name
        json_final["backend_url"] = settings.BACKEND_URL
        json_final["tk"] = get_user_token(request.user, expires)
        json_final["company_id"] = str(company.uuid)
        url = settings.ZIP_DOWNLOAD_URL
        headers = {"Content-Type": "application/json"}
        post = requests.post(url, data=json.dumps(json_final), headers=headers)

        if post.status_code == 200:
            return Response({"attributes": {"status": "OK"}})
        else:
            obj.error = True
            obj.save()
            send_email_export_request(obj)
            raise ValidationError("Dados não compatíveis.")

    @action(methods=["post"], url_path="ApprovalStatus", detail=False)
    def approval_status(self, request, pk=None):
        if "company" not in request.query_params:
            return Response(
                {"attributes": {"status": "ERROR", "message": "Company is required"}}
            )
        filters = request.data.get("filters", {})
        filters["company"] = request.query_params["company"]
        filtered_reporting_qs = ReportingFilter(filters).qs
        filtered_reporting_qs.prefetch_related("approval_step").only(
            "uuid", "approval_step"
        )
        first_reporting = filtered_reporting_qs[0]
        first_step_uuid = (
            first_reporting.approval_step.uuid
            if first_reporting.approval_step
            else None
        )
        same_step = True
        for reporting in filtered_reporting_qs:
            step_uuid = (
                reporting.approval_step.uuid if reporting.approval_step else None
            )
            if step_uuid != first_step_uuid:
                same_step = False
                break

        has_next_steps = False
        if same_step and first_step_uuid:
            first_reporting = filtered_reporting_qs[0]
            has_next_steps = first_reporting.approval_step.next_steps.exists()
        return Response(
            {
                "attributes": {
                    "sameStep": same_step,
                    "hasNextSteps": has_next_steps,
                    "firstItemId": str(first_reporting.uuid),
                }
            }
        )

    @action(methods=["post"], url_path="BulkApproval", detail=False)
    def bulk_approval(self, request, pk=None):
        prefetch_related_fields = [
            "approval_step",
            "approval_step__origin_transitions",
            "approval_step__origin_transitions__destination",
            "created_by",
        ]

        # Get all the ApprovalTransitions reportings
        reportings = []
        if "reportings" not in request.data or len(request.data["reportings"]) == 0:
            filters = request.data["filters"]
            if "company" not in filters:
                return Response(
                    data=[
                        {
                            "detail": "Company is required",
                            "source": {"pointer": "/data"},
                            "status": status.HTTP_400_BAD_REQUEST,
                        }
                    ],
                    status=status.HTTP_400_BAD_REQUEST,
                )
            reportings = ReportingFilter(filters).qs.prefetch_related(
                *prefetch_related_fields
            )
        else:
            reporting_ids_list = [
                reporting["id"] for reporting in request.data["reportings"]
            ]
            reportings = Reporting.objects.filter(
                pk__in=reporting_ids_list
            ).prefetch_related(*prefetch_related_fields)

        # Pre-fetch all transitions for all approval steps
        approval_step_ids = list(
            reportings.values_list("approval_step_id", flat=True).distinct()
        )
        all_transitions = ApprovalTransition.objects.filter(
            origin_id__in=approval_step_ids
        ).prefetch_related("origin", "destination")

        transitions_by_origin = defaultdict(list)
        for transition in all_transitions:
            transitions_by_origin[transition.origin_id].append(transition)

        dict_to_approve = {}
        # Check all transitions
        for reporting in reportings:
            transitions = transitions_by_origin.get(reporting.approval_step_id, [])

            source = get_obj_serialized(reporting, is_reporting=True)

            data = {"request": request.data, "source": source}

            # save reporting
            dict_to_approve[reporting] = {}

            transitions_accepted = False
            for transition in transitions:
                if apply_json_logic(transition.condition, data):
                    # save transition that match conditions
                    dict_to_approve[reporting]["transition"] = transition
                    transitions_accepted = True
                    break

            if not transitions_accepted:
                return Response(
                    data=[
                        {
                            "detail": "Nenhuma condição do Apontamento {} foi aceita.".format(
                                reporting.number
                            ),
                            "source": {"pointer": "/data"},
                            "status": status.HTTP_400_BAD_REQUEST,
                        }
                    ],
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # After checking all transitions, now it is time to apply them
        reportings_to_update = []
        for reporting, data_dict in dict_to_approve.items():
            transition = data_dict["transition"]
            reporting.approval_step = transition.destination

            for key, callback in transition.callback.items():
                if key == "change_fields":
                    for field in callback:
                        try:
                            value = get_nested_fields(field["value"], reporting)
                            setattr(reporting, field["name"], value)
                        except Exception as e:
                            print("Exception setting model fields", e)

            reportings_to_update.append(reporting)

        # Bulk update all reportings at once with history
        if reportings_to_update:
            bulk_update_with_history(
                reportings_to_update,
                Reporting,
                use_django_bulk=True,
                user=request.user,
                batch_size=250,
            )

        # Handle to_do messages and history change reasons in bulk
        if "to_do" in request.data and reportings_to_update:
            to_do = request.data["to_do"]
            user_firm = request.user.user_firms.first()

            # Bulk create ReportingMessages
            messages_to_create = [
                ReportingMessage(
                    message=to_do,
                    reporting=reporting,
                    created_by=request.user,
                    created_by_firm=user_firm,
                )
                for reporting in reportings_to_update
            ]
            ReportingMessage.objects.bulk_create(messages_to_create)

            reporting_pks = [r.pk for r in reportings_to_update]
            HistoricalReporting = Reporting.history.model
            latest_history_subquery = (
                HistoricalReporting.objects.filter(uuid=OuterRef("uuid"))
                .order_by("-history_date", "-history_id")
                .values("history_id")[:1]
            )

            HistoricalReporting.objects.filter(
                uuid__in=reporting_pks,
                history_id=Subquery(latest_history_subquery),
            ).update(history_change_reason=to_do)

        return Response({"data": {"status": "OK"}})

    @action(methods=["post"], url_path="Approval", detail=True)
    def approval(self, request, pk=None):
        # Get all the ApprovalTransitions related to the current ApprovalStep
        reporting = self.get_object()
        transitions = ApprovalTransition.objects.filter(origin=reporting.approval_step)

        # Check if the condition from any ApprovalTransition was met
        # If the condition was met, execute the ApprovalStep change

        source = get_obj_serialized(reporting, is_reporting=True)

        data = {"request": request.data, "source": source}

        for transition in transitions:
            if apply_json_logic(transition.condition, data):
                for key, callback in transition.callback.items():
                    if (
                        key == "save_item_before_action"
                        and isinstance(callback, bool)
                        and callback is True
                        and reporting.editable
                    ):
                        item_payload = request.data.get("item_payload", None)
                        if item_payload:
                            item_payload = format_item_payload(request)
                            serializer = ReportingSerializer(
                                instance=reporting, data=item_payload, partial=True
                            )
                            valid = serializer.is_valid()
                            if valid:
                                serializer.save()
                            else:
                                raise serializers.ValidationError(
                                    "kartado.error.reporting.invalid_format"
                                )

                reporting.approval_step = transition.destination

                for key, callback in transition.callback.items():
                    if key == "change_fields":
                        for field in callback:
                            try:
                                value = get_nested_fields(field["value"], reporting)
                                setattr(reporting, field["name"], value)
                            except Exception as e:
                                print("Exception setting model fields", e)

                reporting.save()

                if "to_do" in request.data:
                    to_do = request.data["to_do"]

                    ReportingMessage.objects.create(
                        message=to_do,
                        reporting=reporting,
                        created_by=self.request.user,
                        created_by_firm=self.request.user.user_firms.first(),
                    )

                    hist = reporting.history.first()
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

    @action(methods=["get"], url_path="Spreadsheet", detail=False)
    def spreadsheet_reporting_list(self, request, pk=None):
        with DisableSignals(
            disabled_signals=[
                pre_init,
                post_init,
            ]
        ):
            queryset = self.filter_queryset(self.get_queryset())
            if self.permissions.company_id:
                company = Company.objects.get(uuid=self.permissions.company_id)
            else:
                company = queryset.first().company

            page = self.paginate_queryset(queryset)
            if page is not None:
                data = SpreadsheetEndpoint(page, company).get_data()
                return self.get_paginated_response(data)

            data = SpreadsheetEndpoint(queryset, company).get_data()
            return Response(data)

    @action(methods=["get"], url_path="SpreadsheetResource", detail=False)
    def spreadsheet_resource_list(self, request, pk=None):
        # Get a Reporting queryset filtered
        queryset = self.filter_queryset(self.get_queryset())
        procedure_queryset = ProcedureResource.objects.filter(
            reporting__in=queryset
        ).select_related("reporting", "resource")
        page = self.paginate_queryset(procedure_queryset)
        if page is not None:
            data = SpreadsheetResourceEndpoint(page).get_data()
            return self.get_paginated_response(data)

        data = SpreadsheetResourceEndpoint(procedure_queryset).get_data()
        return Response(data)

    def deny_if_not_allowed_to_view_csp(self, csp_type, company_id, user):
        """
        Checks if the user has permission to view the intended csp_type.
        If not, the method raises a PermissionDenied exception.
        """
        permissions = PermissionManager(company_id, user, model="Dashboard2")
        csp_type_permissions = permissions.get_permission("allowed_csp_types")
        if csp_type_permissions:  # If there are results
            # Remove from nested list
            csp_type_permissions = csp_type_permissions[0]

        if csp_type not in csp_type_permissions:
            raise PermissionDenied()

    @action(methods=["get"], url_path="CSP", detail=False)
    def csp_results(self, request, pk=None):
        results = {}
        csp_type = request.query_params.get("csp_type", "")
        csp_number = request.query_params.get("csp_number", "")
        company_id = request.query_params.get("company", "")

        self.deny_if_not_allowed_to_view_csp(csp_type, company_id, request.user)

        csp_class = get_csp_class(csp_number)
        if csp_class:
            results = csp_class(request.query_params).get_data()
        return Response({"type": "CSP", "attributes": results})

    @action(methods=["get"], url_path="CSPGraph", detail=False)
    def csp_graph_results(self, request, pk=None):
        csp_type = request.query_params.get("csp_type", "")
        csp_number = request.query_params.get("csp_number", "")
        company_id = request.query_params.get("company", "")

        self.deny_if_not_allowed_to_view_csp(csp_type, company_id, request.user)

        csp_graph_class = get_csp_graph_class(csp_number)
        if csp_graph_class:
            return csp_graph_class(request.query_params).get_response()
        return Response({"type": "ReportingCountRoad", "attributes": {}})

    @action(methods=["get"], url_path="SingleExcelPhotoExport", detail=False)
    def single_excel_photo_export(self, request, pk=None):
        fields = ["reportings", "company"]

        if not set(fields).issubset(request.query_params.keys()):
            return error_message(400, "Faltam Parâmetros.")

        results = ExcelPhotoEndpoint(
            reportings=request.query_params["reportings"]
        ).get_data()
        return Response({"type": "SingleExcelPhotoExport", "attributes": results})

    @action(methods=["get"], url_path="EloExport", detail=False)
    def elo_export(self, request, pk=None):
        # Get a Reporting queryset filtered
        queryset = self.filter_queryset(self.get_queryset())

        results = ExcelEloEndpoint(reportings=queryset).get_data()
        return Response({"type": "ExcelEloExport", "attributes": results})

    @action(methods=["get"], url_path="InitialResponsibles", detail=False)
    def initial_responsibles(self, request):
        """
        Retorna os responsáveis do passo inicial que seria atribuído a um novo apontamento.

        Query Parameters:
        - company (obrigatório): UUID da empresa/unidade
        - target_model (opcional): Modelo alvo (padrão: "reportings.Reporting")
        - firm (opcional): UUID da firm que será usada no apontamento
        - created_by (opcional): UUID do usuário que criará o apontamento.
          Se não fornecido, usa o usuário da requisição (request.user) como padrão.
        - form_data (opcional): JSON string com dados do formulário
        """
        company_id = request.query_params.get("company")
        if not company_id:
            return Response(
                {"error": "company parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_model = request.query_params.get("target_model", "reportings.Reporting")
        firm_id = request.query_params.get("firm")
        created_by_id = request.query_params.get("created_by")
        form_data_str = request.query_params.get("form_data")

        # Parse form_data se fornecido
        form_data = None
        if form_data_str:
            try:
                form_data = json.loads(form_data_str)
            except (json.JSONDecodeError, TypeError):
                return Response(
                    {"error": "form_data must be a valid JSON string"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Buscar passo inicial
        try:
            approval_step = (
                ApprovalStep.objects.filter(
                    approval_flow__company_id=company_id,
                    approval_flow__target_model=target_model,
                    previous_steps__isnull=True,
                )
                .prefetch_related(
                    "responsible_firms",
                    "responsible_firms__users",
                    "responsible_firms__manager",
                    "responsible_users",
                )
                .first()
            )
        except Exception as e:
            return Response(
                {"error": f"Error fetching approval step: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not approval_step:
            # Retornar estrutura vazia se não houver passo inicial
            return Response(
                {
                    "data": {
                        "type": "InitialResponsibles",
                        "attributes": {
                            "has_initial_step": False,
                            "is_currently_responsible": False,
                        },
                        "relationships": {
                            "responsibleFirms": {"data": []},
                            "responsibleUsers": {"data": []},
                        },
                    }
                }
            )

        # Obter objetos opcionais
        firm = None
        if firm_id:
            try:
                firm = Firm.objects.get(uuid=firm_id, company_id=company_id)
            except Firm.DoesNotExist:
                pass

        created_by = None
        if created_by_id:
            try:
                created_by = User.objects.get(uuid=created_by_id)
            except User.DoesNotExist:
                pass
        else:
            # Se não fornecido, usar o usuário da requisição como padrão
            if request.user and request.user.is_authenticated:
                created_by = request.user

        # Calcular isCurrentlyResponsible
        is_currently_responsible = self._calculate_is_currently_responsible(
            approval_step, request.user, company_id, firm, created_by, form_data
        )

        # Preparar resposta
        response_data = {
            "data": {
                "type": "InitialResponsibles",
                "attributes": {
                    "has_initial_step": True,
                    "is_currently_responsible": is_currently_responsible,
                    "approval_step": {
                        "id": str(approval_step.uuid),
                        "name": approval_step.name,
                    },
                },
                "relationships": {
                    "responsibleFirms": {
                        "data": [
                            {"type": "Firm", "id": str(firm_obj.uuid)}
                            for firm_obj in approval_step.responsible_firms.all()
                        ]
                    },
                    "responsibleUsers": {
                        "data": [
                            {"type": "User", "id": str(user.uuid)}
                            for user in approval_step.responsible_users.all()
                        ]
                    },
                },
            }
        }

        return Response(response_data)

    def _calculate_is_currently_responsible(
        self,
        approval_step,
        user,
        company_id,
        firm=None,
        created_by=None,
        form_data=None,
    ):
        """
        Verifica se um usuário é responsável pelo passo inicial.

        Args:
            approval_step: ApprovalStep inicial
            user: User a verificar
            company_id: UUID da empresa
            firm: Firm opcional (para calcular responsible_firm_entity)
            created_by: User opcional (para calcular responsible_created_by)
            form_data: dict opcional com dados do formulário (para calcular responsible_json_logic)

        Returns:
            bool: True se o usuário é responsável
        """
        if not user or not user.is_authenticated:
            return False

        try:
            user_firms = user.user_firms.filter(company_id=company_id)

            # Verificar responsible_users
            if user in approval_step.responsible_users.all():
                return True

            # Verificar responsible_firms
            for firm_obj in approval_step.responsible_firms.all():
                if firm_obj in user_firms:
                    return True

            # Verificar responsible_created_by
            if approval_step.responsible_created_by and created_by == user:
                return True

            # Verificar responsible_supervisor
            if (
                approval_step.responsible_supervisor
                and created_by
                and hasattr(created_by, "supervisor")
                and created_by.supervisor == user
            ):
                return True

            # Verificar responsible_firm_manager
            if (
                approval_step.responsible_firm_manager
                and firm
                and hasattr(firm, "manager")
                and firm.manager
                and firm.manager == user
            ):
                return True

            # Verificar responsible_firm_entity
            if (
                approval_step.responsible_firm_entity
                and firm
                and hasattr(firm, "entity")
                and firm.entity
                and hasattr(firm.entity, "approver_firm")
                and firm.entity.approver_firm
                and firm.entity.approver_firm in user_firms
            ):
                return True

            # Verificar responsible_json_logic (se form_data for fornecido)

            if approval_step.responsible_json_logic and form_data is not None:
                # Criar objeto mock com os dados fornecidos
                mock_obj_dict = {
                    "firm_id": firm.uuid if firm else None,
                    "created_by_id": created_by.uuid if created_by else None,
                    "form_data": form_data,
                }

                # Obter permissões do usuário
                permission_manager = PermissionManager(
                    user=user, company_ids=company_id, model="Reporting"
                )

                data = {
                    "reporting": mock_obj_dict,
                    "user": user.__dict__,
                    "user_permission": permission_manager.all_permissions,
                    "user_firms": list(user_firms.values_list("uuid", flat=True)),
                }

                if apply_json_logic(approval_step.responsible_json_logic, data):
                    return True

        except Exception:
            return False

        return False

    @action(methods=["get"], url_path="AnttAttachmentExcelReport", detail=False)
    def export_antt_attachment_excel(self, request, pk=None):
        try:
            company = request.query_params.get("company")
            uuid = request.query_params.get("uuid", None)
            occurrence_type_uuids = request.query_params.getlist("occurrence_type")

            if not company:
                return Response(
                    {"error": "company parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not uuid:
                filters = request.query_params.copy()
                filters["company"] = company
                filtered_reporting_qs = ReportingFilter(filters).qs
                filtered_reporting_qs = filtered_reporting_qs.values_list(
                    "uuid", flat=True
                )
                uuid = ",".join([str(u) for u in filtered_reporting_qs])

            uuid_list = [u.strip() for u in uuid.split(",") if u.strip()]
            if len(uuid_list) > 600:
                raise serializers.ValidationError(
                    "kartado.error.reportings.antt_attachment_excel_report.too_many_reportings"
                )

            results = AnttAttachmentExcelReport(
                company_uuid=company,
                reporting_uuids=uuid,
                occurrence_type_uuids=occurrence_type_uuids,
            ).get_url_and_name()
            return Response(
                {"type": "AnttAttachmentExcelReport", "attributes": results}
            )
        except serializers.ValidationError:
            raise
        except Exception as e:
            sentry_sdk.capture_exception(e)
            return Response(
                {"error": "Erro ao processar a solicitação"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(methods=["get"], url_path="Geocoding", detail=False)
    def geocoding(self, request):
        params = {
            "key": credentials.GMAPS_API_KEY,
            "language": request.query_params.get("language", "pt-BR"),
        }
        if request.query_params.get("latlng"):
            params.update(
                {
                    "latlng": request.query_params.get("latlng"),
                    "location_type": request.query_params.get(
                        "location_type", "ROOFTOP"
                    ),
                    "result_type": request.query_params.get(
                        "result_type", "street_address"
                    ),
                }
            )
        if request.query_params.get("place_id"):
            params.update({"place_id": request.query_params.get("place_id")})
        else:
            params.update(
                {
                    "region": request.query_params.get("region", "br"),
                    "address": request.query_params.get("address"),
                    "bounds": request.query_params.get("bounds"),
                    "components": request.query_params.get("components"),
                }
            )

        response_google_maps = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json", params=params
        )

        return Response(
            response_google_maps.json(), status=response_google_maps.status_code
        )

    @action(
        methods=["get"],
        url_path="IsSharedWithAgency",
        detail=True,
        permission_classes=[IsAuthenticated],
    )
    def is_shared_with_agency(self, request, pk=None):
        obj: Reporting = self.get_object()
        is_shared = (
            obj.shared_with_agency
            or obj.form_data.get("artesp_code", False)
            or ConstructionProgress.objects.filter(
                reportings=obj, construction__origin="AGENCY"
            ).exists()
        )

        data = {"is_shared_with_agency": is_shared}

        return Response(dict_to_casing(data))

    @action(methods=["post"], url_path="EditExport", detail=False)
    def edit_export(self, request, pk=None):
        random_string = get_random_string()
        object_name = "media/private/{}_{}.{}".format(
            "edit_export", random_string, "xlsx"
        )

        reporting_uuids = [r["id"] for r in request.data["reportings"]]
        create_edit_export(
            object_name,
            reporting_uuids,
            str(request.user.uuid),
            request.headers["Authorization"],
        )

        s3 = get_s3()
        url = get_s3_url(s3, object_name)
        file_name = "edit_export_name.xlsx"
        return Response(
            {
                "type": "EditExport",
                "attributes": {"url": url, "name": file_name},
                "object_name": object_name,
            }
        )

    @action(methods=["post"], url_path="AnttExport", detail=False)
    def antt_export(self, request, pk=None):
        # Get a Reporting queryset filtered
        err = None
        object_name: str = None
        file_name: str = None
        url = None

        s3 = get_s3()

        reportings = [reporting["id"] for reporting in request.data["reportings"]]

        report_type: str = request.data["report_type"]
        ccr_report = None
        format = ReportFormat.XLSX
        if report_type.endswith("PDF"):
            format = ReportFormat.PDF
            report_type = report_type[:-3]

        if report_type == "anttEletrica":
            ccr_report = CCRElectrical(reportings, format)
            ccr_report_electrical_async_handler(ccr_report.dict())

        elif report_type == "anttIluminacao":
            ccr_report = CCRLighting(reportings, format)
            ccr_report_lighting_async_handler(ccr_report.dict())

        elif report_type == "anttMonitoracaoVertical":
            ccr_report = CCRVerticalSignage(reportings, format)
            ccr_report_vertical_signage_async_handler(ccr_report.dict())

        elif report_type == "artespMonitoracaoVertical":
            ccr_report = CCRVerticalSignage(
                reportings, format, only_shared=False, is_artesp=True
            )
            ccr_report_vertical_signage_async_handler(ccr_report.dict())

        elif report_type == "anttBarreiraRigida":
            ccr_report = CCRRigidBarrier(reportings, format)
            ccr_report_rigid_barrier_async_handler(ccr_report.dict())

        elif report_type == "anttDefesasOae":
            ccr_report = CCRMetalDefensesOAE(reportings, format)
            ccr_report_metal_defenses_oae_async_handler(ccr_report.dict())

        elif report_type == "anttDefesasMetalicas":
            ccr_report = CCRMetalDefenses(reportings, format)
            ccr_report_metal_defenses_async_handler(ccr_report.dict())

        elif report_type == "anttTelasAntiOfuscante":
            ccr_report = CCRAntiGlareScreens(reportings, format)
            ccr_report_antiglare_screen_async_handler(ccr_report.dict())

        elif report_type == "anttTerraplenos":
            ccr_report = CCREmbankmentsRetainingStructures(reportings, format)
            ccr_embankments_retaining_structures_async_handler(ccr_report.dict())

        elif report_type == "anttSHLongitudinal":
            ccr_report = CCRLongitudinalHorizontalSignage(reportings, format)
            ccr_report_longitudinal_horizontal_signage_async_handler(ccr_report.dict())

        elif report_type == "anttAcessos":
            ccr_report = CCRAccess(reportings, format)
            ccr_report_access_async_handler(ccr_report.dict())

        elif report_type == "anttOcupacoes":
            ccr_report = CCROcupation(reportings, format)
            ccr_report_occupation_async_handler(ccr_report.dict())

        elif report_type == "anttFichaEdicacoes":
            ccr_report = CCRBuilds(reportings, format)
            ccr_report_builds_async_handler(ccr_report.dict())

        elif report_type == "anttTerraplenosAnexoTres":
            found_at_filter = request.data.get("found_at", None)
            panel_uuid = request.data.get("panel_id", None)
            ccr_report = CCREmbankmentsAnnexThree(
                found_at_filter, panel_uuid, reportings, format
            )
            ccr_embankments_annex_three_async_handler(ccr_report.dict())

        elif report_type == "anttTerraplenosAnexoCincoPosProtocolo":
            found_at_filter = request.data.get("found_at", None)
            panel_uuid = request.data.get("panel_id", None)
            ccr_report = CCREmbankmentsAnnexFivePostProtocol(
                found_at_filter, panel_uuid, reportings, format
            )
            ccr_embankments_annex_five_post_protocol_async_handler(ccr_report.dict())

        elif report_type == "anttTerraplenosAnexoCinco":
            ccr_report = CCREmbankmentsAnnexFive(reportings, format)
            ccr_embankments_annex_five_async_handler(ccr_report.dict())

        elif report_type == "anttTerraplenosAnexoDois":
            ccr_report = CCREmbankmentsRetainingStructuresAnnexTwo(reportings, format)
            ccr_report_embankments_retaining_structures_annex_two_async_handler(
                ccr_report.dict()
            )

        elif report_type == "anttMonitoringOAE":
            if not reportings:
                raise serializers.ValidationError(
                    "kartado.anttMonitoringOAE.error.reporting.not_found"
                )
            ccr_report = CCRReportMonitoringOAE(reportings, format)
            ccr_report_monitoring_oae_async_handler(ccr_report.dict())

        elif report_type == "anttDrenagemSuperficialAnexoUm":
            ccr_report = CrrSurfaceDrainageAnnexOne(reportings, format)
            ccr_report_oac_annex_one_async_handler(ccr_report.dict())

        elif report_type == "anttDrenagemProfundaAnexoDois":
            ccr_report = CrrDeepDrainageAnnexTwo(reportings, format)
            ccr_report_oac_annex_two_async_handler(ccr_report.dict())

        elif report_type == "anttDrenagemSuperficialAnexoTres":
            ccr_report = CrrSurfaceDrainageAnnexThree(reportings, format)
            ccr_report_oac_annex_three_async_handler(ccr_report.dict())

        elif report_type == "anttDrenagemSuperficialAnexoTresRioSP":
            ccr_report = CrrSurfaceDrainageAnnexThree(reportings, format, True)
            ccr_report_oac_annex_three_async_handler(ccr_report.dict())

        elif report_type == "anttDrenagemProfundaAnexoQuatro":
            ccr_report = CrrSurfaceDrainageAnnexFour(reportings, format)
            ccr_report_oac_annex_four_async_handler(ccr_report.dict())

        elif report_type == "anttDrenagemSuperficialAnexoCinco":
            ccr_report = CrrSurfaceDrainageAnnexFive(reportings, format)
            ccr_report_oac_annex_five_async_handler(ccr_report.dict())

        elif report_type == "anttSHMarcasViarias":
            ccr_report = CCRRoadMarkingsHorizontalSignage(reportings, format)
            ccr_report_road_markings_horizontal_signage_async_handler(ccr_report.dict())

        elif report_type == "anttSHTachas":
            ccr_report = CCRReportRoadStudHorizontalSignage(reportings, format)
            ccr_report_road_stud_horizontal_signage_async_handler(ccr_report.dict())

        elif report_type == "anttSHDispositivos":
            ccr_report = CCRReportDeviceHorizontalSignage(reportings, format)
            ccr_report_device_horizontal_signage_async_handler(ccr_report.dict())

        elif report_type == "anttSHZebrados":
            ccr_report = CCRReportZebraHorizontalSignage(reportings, format)
            ccr_report_zebra_horizontal_signage_async_handler(ccr_report.dict())

        elif report_type == "anttActionDiagnosis":
            ccr_report = XlsxHandlerReportActionDiagnosisAnnex6(reportings, format)
            ccr_report_action_diagnosis_annex_6_async_handler(ccr_report.dict())

        elif report_type == "arteSpSurfaceDrainage":
            ccr_report = XlsxHandlerReportSurfaceDrainageSheets(reportings, format)
            ccr_report_surface_drainage_async_handler(ccr_report.dict())

        elif report_type == "arteSpSurfaceDrainagev2025":
            ccr_report = XlsxHandlerReportSurfaceDrainageSheetsv2025(reportings, format)
            ccr_report_surface_drainage_async_handler_v2025(ccr_report.dict())

        elif report_type == "anttDiagnosticoEdificacao":
            ccr_report = CCrBuildingDiagnostics(reportings, format)
            ccr_report_building_diagnostics_async_handler(ccr_report.dict())

        elif report_type == "anttDiagnosticoEdificacao2025":
            # Filter reportings with only "Ruim" value
            if format == ReportFormat.PDF:
                raise ValidationError("Este relatório não suporta download em PDF")
            reps_exists = Reporting.objects.filter(
                uuid__in=reportings, form_data__general_conservation_state="3"
            ).exists()
            if not reps_exists:
                raise ValidationError(
                    'Filtro não contem apontamentos com Estado Geral de Conservação de valor "Ruim"'
                )
            ccr_report = CCrBuildingDiagnostics2025(reportings, format)
            ccr_report_building_diagnostics_2025_async_handler(ccr_report.dict())

        elif report_type == "anttEdificacaoInstalacao":
            if format == ReportFormat.PDF:
                raise ValidationError("Este relatório não suporta download em PDF")
            ccr_report = CCrBuildingInstalation(reportings, format)
            ccr_report_building_instalation_async_handler(ccr_report.dict())

        elif report_type == "anttComparativoEdificacao":
            ccr_report = CCrBuildingComparative(reportings, format)
            ccr_report_building_comparative_async_handler(ccr_report.dict())

        elif report_type == "anttComparativoEdificacao2025":
            if format == ReportFormat.PDF:
                raise ValidationError("Este relatório não suporta download em PDF")
            ccr_report = CCrBuildingComparative2025(reportings, format)
            ccr_report_building_comparative_2025_async_handler(ccr_report.dict())

        elif report_type == "servicesPerformedDSPrecariousAnnex7":
            executed_at_filter = request.data.get("executed_at", None)
            panel_id = request.data.get("panel_id", "")
            ccr_report = ServicesPerformedDSPrecariousAnnex7(
                uuids=reportings,
                report_format=format,
                executed_at=executed_at_filter,
                panel_id=panel_id,
            )
            ccr_services_performed_ds_precarious_annex7_async_handler(ccr_report.dict())
        elif report_type == "servicesPerformedDSRegularAnnex7":
            executed_at_filter = request.data.get("executed_at", None)
            panel_id = request.data.get("panel_id", "")
            ccr_report = ServicesPerformedDSRegularAnnex7(
                uuids=reportings,
                report_format=format,
                executed_at=executed_at_filter,
                panel_id=panel_id,
            )
            ccr_services_performed_ds_regular_annex7_async_handler(ccr_report.dict())

        elif report_type == "artespOAC":
            ccr_report = CCRArtespOAC(reportings, format)
            ccr_report_artesp_oac_async_handler(ccr_report.dict())

        elif report_type == "oacVIIPrecarious":
            ccr_report = OACVIIPrecarious(report_type, reportings, format)
            ccr_report_oac_vii_precarious_async_handler(ccr_report.dict())

        elif report_type == "oacVIIRegular":
            ccr_report = OACVIIRegular(report_type, reportings, format)
            ccr_report_oac_vii_regular_async_handler(ccr_report.dict())

        elif report_type == "oaeIV":
            ccr_report = OAEIV(report_type, reportings, format)
            ccr_report_oae_iv_async_handler(ccr_report.dict())

        elif report_type == "oaeI":
            ccr_report = OAEI(reportings, format)
            ccr_report_oae_i_async_handler(ccr_report.dict())

        elif report_type == "oaeManagement":
            ccr_report = CCRReportOAEManagement(reportings, format)
            ccr_report_oae_management_async_handler(ccr_report.dict())

        elif report_type == "routineOAE":
            ccr_report = RoutineOAE(reportings, format)
            ccr_report_routine_oae_async_handler(ccr_report.dict())

        elif report_type == "routineFootbridge":
            ccr_report = RoutineFootbridge(reportings, format)
            ccr_report_routine_footbridge_async_handler(ccr_report.dict())

        elif report_type == "routineTunnel":
            ccr_report = RoutineTunnel(reportings, format)
            ccr_report_routine_tunnel_async_handler(ccr_report.dict())

        elif report_type == "initialOAE":
            ccr_report = InitialOAE(reportings, format)
            ccr_report_initial_oae_async_handler(ccr_report.dict())

        elif report_type == "initialFootbridge":
            ccr_report = InitialFootbridge(reportings, format)
            ccr_report_initial_footbridge_async_handler(ccr_report.dict())

        elif report_type == "initialTunnel":
            ccr_report = InitialTunnel(reportings, format)
            ccr_report_initial_tunnel_async_handler(ccr_report.dict())

        elif report_type == "anttMonitoringOAENewVersion":
            ccr_report = XlsxHandlerMonitoringOAENewVersion(reportings, format)
            ccr_report_monitoring_oae_new_version_async_handler(ccr_report.dict())

        else:
            raise ValidationError("Tipo inválido de relatório")

        file_name = file_name or ccr_report.file_name
        object_name = object_name or ccr_report.object_name
        url = get_s3_url(s3, object_name)

        return Response(
            {
                "type": "AnttExport",
                "attributes": {"url": url, "name": file_name},
                "err": err,
                "object_name": object_name,
                "file_name": file_name,
            }
        )

    @action(methods=["POST"], url_path="CreateRecuperations", detail=False)
    def create_recuperations(self, request):
        try:
            inspection_uuid_list = request.data["inspection"]
            rep_list = Reporting.objects.filter(uuid__in=inspection_uuid_list)
            assert rep_list.count() == len(inspection_uuid_list)
        except KeyError:
            raise serializers.ValidationError(
                "kartado.error.reportings.inspection_field_is_required"
            )
        except AssertionError:
            raise serializers.ValidationError(
                "kartado.error.reportings.at_least_one_provided_inspection_does_not_exist"
            )

        try:
            menu_uuid = request.data["menu"]
            menu = RecordMenu.objects.get(pk=menu_uuid)
        except KeyError:
            raise serializers.ValidationError(
                "kartado.error.reportings.menu_field_is_required"
            )
        except (RecordMenu.DoesNotExist, FieldValidationError):
            raise serializers.ValidationError(
                "kartado.error.reportings.provided_menu_does_not_exist"
            )

        if "company" not in request.query_params:
            return error_message(400, 'Parâmetro "Unidade" é obrigatório')
        company = Company.objects.get(uuid=request.query_params["company"])
        user = request.user

        (
            reportings_with_therapy,
            reportings_without_therapy,
        ) = separate_reportings_by_therapy(rep_list)

        if reportings_with_therapy:
            create_recuperation_from_inspections(
                reportings_with_therapy, company, user, menu
            )

        if reportings_without_therapy:
            recuperation_occurrence_types_ids = request.data.get(
                "recuperations_to_create_occurrence_types", []
            )
            if not recuperation_occurrence_types_ids:
                raise serializers.ValidationError(
                    "kartado.error.reportings.recuperations_to_create_occurrence_types_is_required"
                )
            recuperation_occurrence_types = OccurrenceType.objects.filter(
                uuid__in=recuperation_occurrence_types_ids
            )

            reporting_relation_metadata = get_obj_from_path(
                company.metadata, "recuperation_reporting_relation"
            )
            if not reporting_relation_metadata:
                raise serializers.ValidationError(
                    "kartado.error.reporting.recuperation_reporting_relation_not_configured"
                )
            create_recuperation_items(
                reportings_without_therapy,
                recuperation_occurrence_types,
                company,
                user,
                reporting_relation_metadata,
                menu,
                None,
            )

        return Response({"data": {"status": "OK"}})

    @action(methods=["post"], url_path="pdf-reporting", detail=True)
    def pdf_report_occurrence_record(self, request, pk=None):
        if pk is None:
            obj = self.get_object()
        if pk is not None:
            obj = Reporting.objects.filter(pk=pk).first()
        if obj is None:
            raise serializers.ValidationError(
                "kartado.error.pdf_report_occurrence_record.occurrence_record_not_found"
            )

        template_name = "reportings/pdf/template_reporting.html"
        data = keys_to_snake_case(request.data)
        config_map = data.get("map_settings", "")

        if not config_map:
            data.update(get_default_config_map_to_report(obj))

        company_id = obj.company_id if obj and hasattr(obj, "company_id") else None
        permissions_manager = PermissionManager(
            user=self.request.user,
            company_ids=company_id,
            model="Road",
        )
        request.permissions_manager = permissions_manager

        pdf_config = data
        pdf = PDFGenericGenerator(
            request,
            obj,
            template_name,
            pdf_config,
        )

        pdf.get_context()
        presigned_url = pdf.build_pdf()
        return Response({"url": presigned_url})

    @action(methods=["POST"], url_path="CreateJobsFromInspections", detail=False)
    def create_jobs_from_inspections(self, request):

        if "company" not in request.query_params:
            return error_message(400, 'Parâmetro "Unidade" é obrigatório')

        input_data = json.loads(request.body).get("data", None)
        if input_data is None:
            raise serializers.ValidationError(
                "kartado.error.reporting.data_key_not_found_on_body"
            )
        try:
            menu_uuid = input_data["menu"]
            menu = RecordMenu.objects.get(pk=menu_uuid)
        except KeyError:
            raise serializers.ValidationError(
                "kartado.error.reportings.menu_field_is_required"
            )
        except (RecordMenu.DoesNotExist, FieldValidationError):
            raise serializers.ValidationError(
                "kartado.error.reportings.provided_menu_does_not_exist"
            )

        try:
            inspection_data = input_data["inspection_data"]
            job_data = input_data["job_data"]
        except KeyError:
            raise serializers.ValidationError(
                "kartado.error.reportings.required_information_is_missing"
            )

        company = Company.objects.get(uuid=request.query_params["company"])
        user = request.user

        create_recuperation_reportings_jobs(
            company, user, menu, inspection_data, job_data
        )

        return error_message(200, "Programações criadas com sucesso!")

    def clean_form_data_images(self, reporting) -> Tuple[Dict, Set[str]]:
        fields = reporting.occurrence_type.form_fields.get("fields", []) or []
        form_data = deepcopy(reporting.form_data) or {}
        removed_uuids = set()

        for field in fields:
            api_name = field.get("apiName")
            data_type = field.get("dataType")
            if not api_name or not data_type:
                continue

            key = to_snake_case(api_name)

            if data_type == "innerImagesArray":
                values = form_data.pop(key, None)
                if isinstance(values, list):
                    removed_uuids.update(values)

            elif data_type == "arrayOfObjects":
                items = form_data.get(key)
                if not isinstance(items, list):
                    continue

                inner_fields = field.get("innerFields", []) or []
                inner_image_keys = [
                    to_snake_case(inner.get("apiName"))
                    for inner in inner_fields
                    if inner
                    and inner.get("dataType") == "innerImagesArray"
                    and inner.get("apiName")
                ]

                if not inner_image_keys:
                    continue

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    for inner_key in inner_image_keys:
                        values = item.pop(inner_key, None)
                        if isinstance(values, list):
                            removed_uuids.update(values)

                form_data[key] = items

        return form_data, removed_uuids

    def reply_reporiting_files(
        self, request, original_reporting, new_reporting, excluded_uuids: Set[str]
    ):
        rfs = list(original_reporting.reporting_files.all())
        if not rfs:
            return

        to_create = []
        for rf in rfs:
            if str(rf.uuid) in excluded_uuids:
                continue

            to_create.append(
                ReportingFile(
                    reporting=new_reporting,
                    description=rf.description,
                    md5=rf.md5,
                    upload=rf.upload.name,
                    created_by=request.user,
                    include_dnit=True,
                    include_rdo=rf.include_rdo,
                    km=rf.km,
                    point=rf.point,
                    kind=rf.kind,
                    is_shared=False,
                )
            )

        try:
            ReportingFile.objects.bulk_create(to_create, batch_size=500)
        except Exception as e:
            sentry_sdk.capture_message(
                f"Error bulk copying ReportingFiles for reporting {original_reporting.uuid}: {e}",
                "warning",
            )
            logging.warning(
                f"Error bulk copying ReportingFiles for reporting {original_reporting.uuid}: {e}"
            )

    @action(methods=["POST"], url_path="CopyReportings", detail=False)
    def copy_reportings(self, request):
        """
        Creates copies of reports based on a list of UUIDs
        """
        if "company" not in request.query_params:
            return error_message(400, 'Parâmetro "Unidade" é obrigatório')

        input_data = json.loads(request.body).get("data", None)
        if input_data is None:
            raise serializers.ValidationError(
                "kartado.error.reporting.data_key_not_found_on_body"
            )

        uuids = input_data.get("uuids", None)

        if uuids is None:
            raise serializers.ValidationError("kartado.error.reporting.uuids_required")

        if not isinstance(uuids, list):
            raise serializers.ValidationError(
                "kartado.error.reporting.uuids_must_be_list"
            )

        if len(uuids) > 20:
            raise serializers.ValidationError(
                "kartado.error.reporting.max_reportings_exceeded"
            )

        copy_files_and_images = bool(input_data.get("copyFilesAndImages", False))

        try:
            company_id = uuid.UUID(request.query_params["company"])

            initial_approval_step = ApprovalStep.objects.filter(
                approval_flow__company_id=company_id,
                approval_flow__target_model="reportings.Reporting",
                previous_steps__isnull=True,
            ).first()
            reportings = Reporting.objects.filter(uuid__in=uuids).prefetch_related(
                "reporting_files",
                "occurrence_type",
                "company",
                "firm",
                "status",
                "road",
                "active_tile_layer",
                "job",
                "approval_step",
                "construction",
                "active_inspection",
                "pdf_import",
                "menu",
                "created_by",
                "parent",
                "active_inspection_of_inventory",
            )

            if not reportings.exists():
                raise serializers.ValidationError(
                    "kartado.error.reporting.no_reportings_found"
                )

            # Prefetch the relations
            all_parent_relations = ReportingInReporting.objects.filter(
                parent__in=reportings
            ).prefetch_related("child", "reporting_relation")
            parent_relations = defaultdict(list)
            for relation in all_parent_relations:
                parent_relations[relation.parent.uuid].append(relation)

            all_child_relations = ReportingInReporting.objects.filter(
                child__in=reportings
            ).prefetch_related("parent", "reporting_relation")
            child_relations = defaultdict(list)
            for relation in all_child_relations:
                child_relations[relation.child.uuid].append(relation)

            # Fetch all QualitySamples
            all_quality_samples = (
                QualitySample.objects.filter(reportings__in=reportings)
                .prefetch_related(
                    Prefetch(
                        "reportings", queryset=reportings, to_attr="filtered_reportings"
                    )
                )
                .distinct()
            )
            quality_samples_by_reporting = defaultdict(list)
            for sample in all_quality_samples:
                for reporting in sample.reportings.all():
                    if str(reporting.uuid) in uuids:
                        quality_samples_by_reporting[reporting.uuid].append(sample)

            new_parent_relations = []
            new_child_relations = []
            reporting_files_to_create = []
            copied_reportings = []

            fields_to_remove = [
                "uuid",
                "number",
                "created_at",
                "updated_at",
                "created_by",
                "found_at",
                "due_at",
                "reporting_files",
                "history_change_reason",
                "job",
                "measurement",
                "approval_step",
                "last_history_user",
                "active_inspection",
                "active_inspection_of_inventory",
                "technical_opinion",
                "editable",
            ]

            for reporting in reportings:
                # Create the new reporting via deepcopy
                try:
                    new_reporting = deepcopy(reporting)
                    new_reporting.pk = None

                    for field in fields_to_remove:
                        if field in (
                            "reporting_files",
                            "active_inspection_of_inventory",
                        ):
                            continue
                        if field == "uuid":
                            continue
                        if hasattr(new_reporting, field):
                            setattr(new_reporting, field, None)

                    if hasattr(new_reporting, "uuid"):
                        new_reporting.uuid = uuid.uuid4()

                    new_reporting.approval_step = initial_approval_step
                    new_reporting.approval_transition = None

                    # Preserve/clean form_data when copying files and images
                    excluded_uuids = set()
                    if copy_files_and_images:
                        try:
                            (
                                cleaned_form_data,
                                excluded_uuids,
                            ) = self.clean_form_data_images(reporting)
                            setattr(new_reporting, "form_data", cleaned_form_data)
                        except Exception as e:
                            sentry_sdk.capture_message(
                                f"Error cleaning form_data for reporting {reporting.uuid}: {e}",
                                "warning",
                            )
                            logging.warning(
                                f"Error cleaning form_data for reporting {reporting.uuid}: {e}"
                            )

                    new_reporting.created_by = request.user
                    new_reporting.editable = True
                    new_reporting.found_at = timezone.now()

                    new_reporting.save()

                    # Clear M2M that should not be kept
                    if hasattr(new_reporting, "reporting_files"):
                        new_reporting.reporting_files.set([])
                    if hasattr(new_reporting, "active_inspection_of_inventory"):
                        new_reporting.active_inspection_of_inventory.set([])

                    # Prepares parent relationships for bulk create
                    for relation in parent_relations.get(reporting.uuid, []):
                        new_parent_relations.append(
                            ReportingInReporting(
                                parent=new_reporting,
                                child=relation.child,
                                reporting_relation=relation.reporting_relation,
                            )
                        )

                    # Prepares child relationships for bulk create
                    for relation in child_relations.get(reporting.uuid, []):
                        new_child_relations.append(
                            ReportingInReporting(
                                parent=relation.parent,
                                child=new_reporting,
                                reporting_relation=relation.reporting_relation,
                            )
                        )

                    for sample in quality_samples_by_reporting.get(reporting.uuid, []):
                        try:
                            new_sample = deepcopy(sample)
                            new_sample.pk = None

                            for field in [
                                "created_by",
                                "created_at",
                                "number",
                                "responsible",
                            ]:
                                if hasattr(new_sample, field):
                                    setattr(new_sample, field, None)

                            # Ensure a fresh UUID for QS primary key when applicable
                            if hasattr(new_sample, "uuid"):
                                new_sample.uuid = uuid.uuid4()

                            new_sample.created_by = request.user
                            new_sample.responsible = request.user
                            new_sample.save()
                            new_sample.reportings.set([new_reporting])
                        except Exception as e:
                            sentry_sdk.capture_message(
                                f"Error copying QualitySample related at {reporting.uuid}: {str(e)}",
                                "warning",
                            )
                            logging.warning(
                                f"Error copying QualitySample related at {reporting.uuid}: {str(e)}",
                            )

                    if copy_files_and_images:
                        rfs = list(reporting.reporting_files.all())
                        for rf in rfs:
                            if str(rf.uuid) in excluded_uuids:
                                continue

                            reporting_files_to_create.append(
                                ReportingFile(
                                    reporting=new_reporting,
                                    description=rf.description,
                                    md5=rf.md5,
                                    upload=rf.upload.name,
                                    created_by=request.user,
                                    include_dnit=True,
                                    include_rdo=rf.include_rdo,
                                    km=rf.km,
                                    point=rf.point,
                                    kind=rf.kind,
                                    is_shared=False,
                                )
                            )

                    copied_reportings.append(str(new_reporting.uuid))
                except Exception:
                    # Keep trying to copy the next reports
                    sentry_sdk.capture_message(
                        f"Error copying reporting {reporting.uuid}",
                        "warning",
                    )
                    logging.error(f"Error copying reporting {reporting.uuid}")

            if reporting_files_to_create:
                try:
                    ReportingFile.objects.bulk_create(
                        reporting_files_to_create, batch_size=500
                    )
                except Exception as e:
                    sentry_sdk.capture_message(
                        f"Error bulk copying ReportingFiles: {e}",
                        "warning",
                    )
                    logging.warning(f"Error bulk copying ReportingFiles: {e}")

            # Create all relationships at once with bulk_create
            if new_parent_relations:
                ReportingInReporting.objects.bulk_create(
                    new_parent_relations, batch_size=100
                )

            if new_child_relations:
                ReportingInReporting.objects.bulk_create(
                    new_child_relations, batch_size=100
                )

            return Response(
                {
                    "type": "CopyReportings",
                    "attributes": {
                        "status": "OK",
                        "copied_reportings": copied_reportings,
                        "copy_count": len(copied_reportings),
                    },
                }
            )

        except Exception as e:
            logging.error(f"Error in CopyReportings: {str(e)}")
            sentry_sdk.capture_exception(e)
            raise serializers.ValidationError(
                f"kartado.error.reporting.copy_failed: {str(e)}"
            )


class ReportingGeoView(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, ReportingPermissions]
    filterset_class = ReportingFilter
    serializer_class = ReportingGeoSerializer
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = get_reporting_queryset(self.action, self.request, self.permissions)

        if needs_distinct_for_reporting(self.permissions, self.request):
            queryset = queryset.distinct()
        return self.get_serializer_class().setup_eager_loading(queryset)

    def list(self, request, *args, **kwargs):
        with DisableSignals(
            disabled_signals=[
                pre_init,
                post_init,
            ]
        ):
            list_response = super().list(request, *args, **kwargs)
            return list_response


class ReportingGisIntegrationView(ReportingGeoView):
    renderer_classes = [DRFJSONRenderer]
    pagination_class = GeoJsonPagination
    serializer_class = ReportingGisIntegrationSerializer


class DashboardReportingView(viewsets.ReadOnlyModelViewSet):
    serializer_class = DashboardReportingSerializer
    permission_classes = [IsAuthenticated, ReportingPermissions]
    filterset_class = ReportingFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = get_reporting_queryset(self.action, self.request, self.permissions)
        queryset = queryset.exclude(occurrence_type__occurrence_kind="2")

        if needs_distinct_for_reporting(self.permissions, self.request):
            queryset = queryset.distinct()
        return self.get_serializer_class().setup_eager_loading(queryset)


class InventoryView(ReportingView):
    permission_classes = [IsAuthenticated, InventoryPermissions]
    resource_name = "Inventory"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return Reporting.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="Inventory",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, Reporting.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    Reporting.objects.filter(created_by=self.request.user),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, Reporting.objects.filter(company_id=user_company)
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = Reporting.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(
            queryset.filter(occurrence_type__occurrence_kind="2").distinct()
        )

    @action(methods=["get"], url_path="Schedule", detail=False)
    def inventory_schedule(self, request, pk=None):
        # Get a Reporting queryset filtered
        queryset = self.filter_queryset(self.get_queryset()).filter(
            occurrence_type__is_oae=True
        )

        company = Company.objects.get(uuid=self.request.query_params["company"])

        results = InventoryScheduleEndpoint(
            inventory=queryset, company=company
        ).get_data()
        return Response({"type": "InventorySchedule", "attributes": results})

    @action(methods=["get"], url_path="ScheduleExcel", detail=False)
    def schedule_excel_export(self, request, pk=None):
        # Get a Reporting queryset filtered
        queryset = self.filter_queryset(self.get_queryset()).filter(
            occurrence_type__is_oae=True
        )

        company = Company.objects.get(uuid=self.request.query_params["company"])

        excel_name = get_excel_name(queryset.first().road_name.replace("/", "_"))

        run_async_artesp_excel_export(
            [str(a) for a in queryset.values_list("uuid", flat=True)],
            str(company.uuid),
            excel_name,
        )

        results = get_url(excel_name)

        return Response({"type": "ArtespExcelExport", "attributes": results})

    @action(methods=["get"], url_path="ScheduleExcelCompact", detail=False)
    def schedule_excel_compact_export(self, request, pk=None):
        # Get a Reporting queryset filtered
        queryset = self.filter_queryset(self.get_queryset()).filter(
            occurrence_type__is_oae=True
        )

        company = Company.objects.get(uuid=self.request.query_params["company"])

        excel_name = get_excel_name(queryset.first().road_name.replace("/", "_"))

        run_async_artesp_excel_export_compact(
            [str(a) for a in queryset.values_list("uuid", flat=True)],
            str(company.uuid),
            excel_name,
        )

        results = get_url_compact(excel_name)

        return Response({"type": "ArtespExcelExport", "attributes": results})

    @action(methods=["GET"], url_path="Choices/ExcelImport", detail=False)
    def return_choices(self, request, pk=None):
        if "company" not in request.query_params:
            return error_message(400, 'Parâmetro "Unidade" é obrigatório')
        company = Company.objects.get(uuid=request.query_params["company"])

        data = return_inventory_fields(company)

        return Response(data, status=status.HTTP_200_OK)

    @action(methods=["GET"], url_path="Spreadsheet", detail=False)
    def spreadsheeet_inventory_list(self, request, pk=None):
        queryset = self.filter_queryset(self.get_queryset())
        company = Company.objects.get(uuid=request.query_params["company"])

        page = self.paginate_queryset(queryset)
        if page is not None:
            data = InventorySpreadsheeetEndpoint(page, company).get_data()
            return self.get_paginated_response(data)

        data = InventorySpreadsheeetEndpoint(queryset, company).get_data()
        return Response(data)


class InventoryGisIntegrationView(ReportingGeoView):
    renderer_classes = [DRFJSONRenderer]
    pagination_class = GeoJsonPagination
    permission_classes = [IsAuthenticated, InventoryPermissions]
    serializer_class = InventoryGisIntegrationSerializer
    get_queryset = InventoryView.get_queryset


class ReportingFileFilter(filters.FilterSet):
    company = CharFilter(field_name="reporting__company__uuid")
    reporting = UUIDListFilter()
    uuid = UUIDListFilter()
    reporting__executed_at = DateTzFilter(lookup_expr="date")
    measurement = ListFilter(method="get_measurement")
    num_jobs = CharFilter(method="get_num_jobs", label="num_jobs")
    datetime = DateFromToRangeCustomFilter()
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")
    file_type = ChoiceFilter(
        choices=file_choices.FILE_CHOICES,
        method="check_image",
        label="file_type",
    )
    shared_with_agency = filters.BooleanFilter(method="get_shared_with_agency")

    class Meta:
        model = ReportingFile
        fields = ["company", "reporting", "include_dnit", "include_rdo"]

    def check_image(self, queryset, name, value):
        ids_and_file_names = queryset.values_list("uuid", "upload")
        if value == "image":
            list_get = [
                item[0] for item in ids_and_file_names if check_image_file(item[1])
            ]
        elif value == "file":
            list_get = [
                item[0] for item in ids_and_file_names if not check_image_file(item[1])
            ]

        return queryset.filter(pk__in=list_get)

    def get_num_jobs(self, queryset, name, value):
        company_id = uuid.UUID(self.request.query_params["company"])

        firms = Firm.objects.filter(company_id=company_id).prefetch_related("firm_jobs")
        jobs = (
            Job.objects.filter(firm__in=firms)
            .order_by("-start_date")[0 : int(value)]
            .prefetch_related("reportings")
        )
        reportings = Reporting.objects.filter(
            job__in=jobs, company_id=company_id
        ).distinct()

        return queryset.filter(reporting__in=reportings).distinct()

    def get_measurement(self, queryset, name, value):
        if value:
            values = value.split(",")
            return queryset.filter(
                reporting__reporting_usage__measurement_id__in=values
            ).distinct()
        else:
            return queryset

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        jobs_section, rdos_section = value.split("|")

        if "company" not in self.data:
            return queryset

        company = Company.objects.get(uuid=self.data["company"])

        jobs_uuids = get_uuids_jobs_user_firms(jobs_section, company, self.request.user)
        rdos_uuids = get_uuids_rdos_user_firms(rdos_section, company, self.request.user)

        if not rdos_uuids and not jobs_uuids:
            return queryset.none()

        # Primeiro coletamos todos os IDs que correspondem aos critérios
        ids_queries = []

        if jobs_uuids:
            jobs_ids = queryset.filter(
                reporting__company_id=company.uuid, reporting__job_id__in=jobs_uuids
            ).values_list("uuid", flat=True)
            ids_queries.append(set(jobs_ids))

        if rdos_uuids:
            files_ids = queryset.filter(
                reporting__company_id=company.uuid,
                reporting_file_multipledailyreports__in=rdos_uuids,
            ).values_list("uuid", flat=True)

            reportings_ids = queryset.filter(
                reporting__company_id=company.uuid,
                reporting__reporting_multiple_daily_reports__in=rdos_uuids,
            ).values_list("uuid", flat=True)

            ids_queries.extend([set(files_ids), set(reportings_ids)])

        # União de todos os IDs encontrados
        all_ids = set().union(*ids_queries)

        # Retorna a queryset final filtrada pelos IDs
        return queryset.filter(uuid__in=all_ids)

    def get_num_jobs_only_user_firms(self, queryset, name, value):
        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        jobs_values = value.split(",")
        num_jobs = jobs_values.pop(0)
        user_firms = self.request.user.user_firms.all()
        if "num_jobs" in company.metadata:
            num_jobs = int(company.metadata["num_jobs"])

        max_reportings_by_job = int(company.metadata.get("max_reportings_by_job", 250))

        jobs_by_count = (
            Job.objects.filter(
                firm__in=user_firms,
                archived=False,
                reporting_count__lte=max_reportings_by_job,
            )
            .order_by("-start_date")[0 : int(num_jobs)]
            .values_list("uuid", flat=True)
        )
        jobs_by_ids = Job.objects.filter(
            uuid__in=jobs_values,
            archived=False,
            reporting_count__lte=max_reportings_by_job,
        ).values_list("uuid", flat=True)

        return queryset.filter(
            Q(reporting__job_id__in=jobs_by_count)
            | Q(reporting__job_id__in=jobs_by_ids)
        ).distinct()

    def get_num_user_firms(self, queryset, name, value):
        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        firms_values = value.split(",")
        num_firms = firms_values.pop(0)
        if "num_firms" in company.metadata:
            num_firms = int(company.metadata["num_firms"])

        firms_by_count = (
            Firm.objects.filter(company=company, users__in=[self.request.user])
            .order_by("name")[: int(num_firms)]
            .values_list("uuid", flat=True)
        )

        firms_by_ids = Firm.objects.filter(
            uuid__in=firms_values, company=company
        ).values_list("uuid", flat=True)

        return queryset.filter(
            Q(reporting__reporting_multiple_daily_reports__firm__in=firms_by_count)
            | Q(reporting__reporting_multiple_daily_reports__firm__in=firms_by_ids)
        ).distinct()

    def get_shared_with_agency(self, queryset, name, value):
        criteria = (
            (Q(reporting__shared_with_agency=True) & Q(is_shared=True))
            | Q(reporting__form_data__artesp_code__isnull=False)
            | Q(
                reporting__reporting_construction_progresses__construction__origin="AGENCY"
            )
        )

        if value is True:
            return queryset.filter(criteria).distinct()
        elif value is False:
            return queryset.exclude(criteria).distinct()
        else:
            return queryset


class ReportingFileView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ReportingFilePermissions]
    filterset_class = ReportingFileFilter
    permissions = None
    ordering_fields = ["uuid", "uploaded_at", "datetime", "description"]
    ordering = "uuid"

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update", "create"]:
            return ReportingFileObjectSerializer
        return ReportingFileSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self, skip_eager_loading=False):
        queryset = None

        # On list or retrieve action: limit queryset
        if self.action in ["list", "retrieve"]:
            if "company" not in self.request.query_params:
                return ReportingFile.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ReportingFile",
                )
            allowed_queryset = self.permissions.get_allowed_queryset()

            if self.action == "list":
                if "none" in allowed_queryset:
                    queryset = join_queryset(queryset, ReportingFile.objects.none())
                if "self" in allowed_queryset:
                    queryset = join_queryset(
                        queryset,
                        ReportingFile.objects.filter(
                            Q(created_by=self.request.user)
                            | Q(reporting__created_by=self.request.user)
                        ),
                    )
                if "antt_supervisor_agency" in allowed_queryset:
                    company = Company.objects.get(pk=user_company)
                    shared_approval_steps = company.metadata.get(
                        "shared_approval_steps", []
                    )

                    queryset = join_queryset(
                        queryset,
                        ReportingFile.objects.filter(
                            Q(reporting__company=company)
                            # Only consider shared approval steps
                            & Q(reporting__approval_step__in=shared_approval_steps)
                            # Check if reporting is being shared
                            & Q(reporting__shared_with_agency=True)
                            # Check if reporting file is being shared
                            & Q(is_shared=True)
                        ),
                    )
                if "supervisor_agency" in allowed_queryset:
                    supervisor_agency_reporting_queryset = get_reporting_queryset(
                        "list",
                        self.request,
                        None,
                        override_allowed_queryset="supervisor_agency",
                    )

                    supervisor_agency_queryset = ReportingFile.objects.filter(
                        reporting__in=supervisor_agency_reporting_queryset
                    )
                    queryset = join_queryset(
                        queryset,
                        supervisor_agency_queryset,
                    )
                if "all" in allowed_queryset:
                    queryset = join_queryset(
                        queryset,
                        ReportingFile.objects.filter(
                            reporting__company__in=[user_company]
                        ),
                    )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ReportingFile.objects.filter(
                reporting__company__in=user_companies
            )

        if skip_eager_loading:
            return queryset.distinct()

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["post"], url_path="Bulk", detail=False)
    def bulk(self, request, pk=None):
        ALLOWED_FIELDS = ["include_dnit", "include_rdo", "is_shared", "kind"]
        ALLOWED_FIELDS_FK = ["reporting_files"]

        request_data = dict_to_casing(request.data, "underscore")
        advanced_mode = request_data.get("advanced_mode", False)
        if advanced_mode:
            input_reporting_files = request_data.get("reporting_files", [])
            reporting_file_to_fields = {
                item["id"]: item for item in input_reporting_files
            }
            reporting_files = ReportingFile.objects.filter(
                pk__in=reporting_file_to_fields.keys()
            )
            upd_reporting_files = []

            if reporting_files:
                for reporting_file in reporting_files:
                    rep_file_id = str(reporting_file.pk)
                    new_field_values: dict = reporting_file_to_fields[rep_file_id]

                    for field_name, field_value in new_field_values.items():
                        if field_name in ALLOWED_FIELDS:
                            try:
                                setattr(reporting_file, field_name, field_value)
                                upd_reporting_files.append(reporting_file)
                            except Exception:
                                raise serializers.ValidationError(
                                    f"kartado.error.reportings.error_while_trying_to_change_field_{field_name}_to_new_value"
                                )

                if upd_reporting_files:
                    bulk_update_with_history(
                        objs=upd_reporting_files,
                        model=ReportingFile,
                        use_django_bulk=True,
                    )

        # Legacy usage
        else:
            reporting_file_ids_list = [
                reporting_file["id"]
                for reporting_file in request.data["reporting_files"]
            ]
            files = ReportingFile.objects.filter(pk__in=reporting_file_ids_list)

            update_query = {}
            for field in request.data.keys():
                if field in ALLOWED_FIELDS:
                    update_query[field] = request.data[field]
                elif field in ALLOWED_FIELDS_FK:
                    if field == "reporting_files":
                        continue
                else:
                    raise ValidationError(
                        "Não pode alterar esse campo: {}".format(field)
                    )
            bulk_update_with_history(
                objs=files, model=ReportingFile, user=request.user, **update_query
            )

        return error_message(200, "OK")

    @action(methods=["get"], url_path="Check", detail=True)
    def check(self, request, pk=None):
        return check_endpoint(self.get_object())

    @action(
        methods=["get"],
        url_path="IsSharedWithAgency",
        detail=True,
        permission_classes=[IsAuthenticated],
    )
    def is_shared_with_agency(self, request, pk=None):
        obj: ReportingFile = self.get_object()
        reporting: Reporting = obj.reporting

        shared_with_agency = (
            (reporting.shared_with_agency and obj.is_shared)
            or reporting.form_data.get("artesp_code", False)
            or reporting.reporting_construction_progresses.filter(
                construction__origin="AGENCY"
            ).exists()
        )

        data = {"is_shared_with_agency": shared_with_agency}
        return Response(dict_to_casing(data))

    @action(
        methods=["get"],
        url_path="RedirectToS3",
        detail=True,
    )
    def redirect_to_s3(self, request, pk=None):
        """
        Redirects to a pre-signed S3 URL for the ReportingFile object.
        Includes authentication and permission checks.
        """

        obj: ReportingFile = self.get_object()

        # Check if file exists and has an upload
        if not obj.upload:
            raise ValidationError("kartado.error.reporting_file.no_file_upload_found")

        try:
            # Get S3 client using credentials (consistent with other code)
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=credentials.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=credentials.AWS_SECRET_ACCESS_KEY,
                aws_session_token=credentials.AWS_SESSION_TOKEN,
            )

            # Get bucket name from settings and object key from upload name
            bucket_name = obj.upload.storage.bucket.name
            object_key = obj.upload.storage._normalize_name(clean_name(obj.upload.name))

            if not bucket_name or not object_key:
                raise ValidationError(
                    "kartado.error.reporting_file.unable_to_determine_s3_location"
                )

            # Generate pre-signed URL (valid for 1 hour)
            presigned_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": object_key},
                ExpiresIn=3600,  # 1 hour
            )

            # Redirect to the pre-signed URL
            return HttpResponseRedirect(presigned_url)

        except FileNotFoundError as e:
            sentry_sdk.capture_exception(e)
            raise ValidationError("kartado.error.reporting_file.s3_access_error")
        except Exception as e:
            sentry_sdk.capture_exception(e)
            raise ValidationError("kartado.error.reporting_file.redirect_failed")


class ReportingMessageFilter(filters.FilterSet):
    company = CharFilter(field_name="reporting__company__uuid")
    reporting = UUIDListFilter()
    uuid = UUIDListFilter()
    created_by = UUIDListFilter()
    created_by_firm = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    read_by = UUIDListFilter(field_name="read_by__user_id")
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")
    num_jobs_only_user_firms = CharFilter(method="get_num_jobs_only_user_firms")
    num_user_firms = CharFilter(method="get_num_user_firms")

    class Meta:
        model = ReportingMessage
        fields = ["company", "reporting", "created_by", "created_by_firm"]

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        jobs_section, rdos_section = value.split("|")

        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        jobs_uuids = get_uuids_jobs_user_firms(jobs_section, company, self.request.user)
        rdos_uuids = get_uuids_rdos_user_firms(rdos_section, company, self.request.user)

        return queryset.filter(
            Q(reporting__job_id__in=jobs_uuids)
            | Q(reporting__reporting_multiple_daily_reports__in=rdos_uuids)
        ).distinct()

    def get_num_jobs_only_user_firms(self, queryset, name, value):
        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        jobs_values = value.split(",")
        num_jobs = jobs_values.pop(0)
        user_firms = self.request.user.user_firms.all()
        if "num_jobs" in company.metadata:
            num_jobs = int(company.metadata["num_jobs"])

        max_reportings_by_job = int(company.metadata.get("max_reportings_by_job", 250))

        jobs_by_count = (
            Job.objects.filter(
                firm__in=user_firms,
                archived=False,
                reporting_count__lte=max_reportings_by_job,
            )
            .order_by("-start_date")[0 : int(num_jobs)]
            .values_list("uuid", flat=True)
        )
        jobs_by_ids = Job.objects.filter(
            uuid__in=jobs_values,
            archived=False,
            reporting_count__lte=max_reportings_by_job,
        ).values_list("uuid", flat=True)

        return queryset.filter(
            Q(reporting__job_id__in=jobs_by_count)
            | Q(reporting__job_id__in=jobs_by_ids)
        ).distinct()

    def get_num_user_firms(self, queryset, name, value):
        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        firms_values = value.split(",")
        num_firms = firms_values.pop(0)
        if "num_firms" in company.metadata:
            num_firms = int(company.metadata["num_firms"])

        firms_by_count = (
            Firm.objects.filter(company=company, users__in=[self.request.user])
            .order_by("name")[: int(num_firms)]
            .values_list("uuid", flat=True)
        )

        firms_by_ids = Firm.objects.filter(
            uuid__in=firms_values, company=company
        ).values_list("uuid", flat=True)

        return queryset.filter(
            Q(reporting__reporting_multiple_daily_reports__firm__in=firms_by_count)
            | Q(reporting__reporting_multiple_daily_reports__firm__in=firms_by_ids)
        ).distinct()


class ReportingMessageView(viewsets.ModelViewSet):
    serializer_class = ReportingMessageSerializer
    permission_classes = [IsAuthenticated, ReportingMessagePermissions]
    filterset_class = ReportingMessageFilter
    permissions = None
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ReportingMessage.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ReportingMessage",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ReportingMessage.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ReportingMessage.objects.filter(
                        Q(created_by=self.request.user)
                        | Q(reporting__created_by=self.request.user)
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ReportingMessage.objects.filter(
                        reporting__company_id__in=[user_company]
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ReportingMessage.objects.filter(
                reporting__company_id__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ReportingMessageReadReceiptFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="reporting_message__reporting__company__uuid")
    reporting_message = UUIDListFilter()
    user = UUIDListFilter()
    read_at = DateFromToRangeCustomFilter()

    class Meta:
        model = ReportingMessageReadReceipt
        fields = ["company", "reporting_message", "user"]


class ReportingMessageReadReceiptView(viewsets.ModelViewSet):
    serializer_class = ReportingMessageReadReceiptSerializer
    permission_classes = [
        IsAuthenticated,
        ReportingMessageReadReceiptPermissions,
    ]
    filterset_class = ReportingMessageReadReceiptFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None
        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ReportingMessageReadReceipt.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ReportingMessageReadReceipt",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(
                    queryset, ReportingMessageReadReceipt.objects.none()
                )
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ReportingMessageReadReceipt.objects.filter(
                        Q(user=self.request.user)
                        | Q(reporting_message__created_by=self.request.user)
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ReportingMessageReadReceipt.objects.filter(
                        reporting_message__reporting__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ReportingMessageReadReceipt.objects.filter(
                reporting_message__reporting__company_id__in=user_companies
            ).distinct()

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class RecordMenuFilter(filters.FilterSet):
    uuid = ListFilter()
    content_type = ChoiceFilter(
        choices=record_menu_choices.RECORD_MENU_CHOICES,
        method="filter_content_type",
        label="content_type",
    )
    hide_menu = BooleanFilter(field_name="user_hidden")
    created_by = ListFilter()
    can_be_used = BooleanFilter(method="filter_can_be_used")
    search = CharFilter(label="search", method="get_search")
    show_as_layer = BooleanFilter()

    class Meta:
        model = RecordMenu
        fields = ["company", "name", "created_by"]

    def filter_content_type(self, queryset, name, value):
        return queryset.filter(content_type__model=value).distinct()

    def get_search(self, queryset, name, value):
        queryset = queryset.annotate(
            search=Concat(
                "name",
                Value(" "),
                "menu_record_panels__panel_type",
                Value(" "),
                "menu_record_panels__name",
                Value(" "),
                output_field=TextField(),
            )
        )

        return queryset.filter(search__unaccent__icontains=value).distinct()

    def filter_can_be_used(self, queryset, name, value):
        return queryset.exclude(system_default=value).distinct()


class RecordMenuView(ListCacheMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, RecordMenuPermissions]
    permissions = None
    filterset_class = RecordMenuFilter
    ordering = "user_order"
    ordering_fields = ["uuid", "name", "user_order"]
    serializer_class = RecordMenuSerializer

    def get_queryset(self):
        queryset = None
        user = self.request.user
        user_agent = getattr(self.request, "META", {}).get("HTTP_USER_AGENT", "")

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return RecordMenu.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])
            if not self.permissions:
                self.permissions = PermissionManager(
                    user=user,
                    company_ids=user_company,
                    model="RecordMenu",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, RecordMenu.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    RecordMenu.objects.filter(
                        Q(company_id=user_company)
                        & (
                            Q(created_by=user)
                            | Q(system_default=True)
                            | Q(name="Apontamentos")
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    RecordMenu.objects.filter(company_id=user_company),
                )

            if not self.permissions.has_permission(permission="can_view"):
                queryset.exclude(content_type__model="reporting")

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = user.companies.all()
            queryset = RecordMenu.objects.filter(company_id__in=user_companies)

        # Subquery to find the correct RecordMenuRelation for the user
        relation_sub = RecordMenuRelation.objects.filter(
            record_menu=OuterRef("pk"),
            user=user,
        )

        # Annotations to optimize some operations, sorting and filtering
        ann_queryset = queryset.annotate(
            user_order=Case(
                When(
                    system_default=True,
                    then=F("order"),
                ),
                default=Subquery(relation_sub.values("order")[:1]),
                output_field=IntegerField(),
            ),
            user_hidden=Case(
                When(
                    system_default=True,
                    then=Value(False),
                ),
                default=Coalesce(
                    Subquery(relation_sub.values("hide_menu")[:1]), Value(True)
                ),
                output_field=BooleanField(),
            ),
            # True if the menu has a panel being shown and the panel is activated as a layer for the platform
            show_as_layer=Exists(
                RecordPanel.objects.filter(
                    Q(menu=OuterRef("pk"))
                    & (
                        Q(panel_show_mobile_maps__user=user)
                        if is_mobile(user_agent)
                        else Q(panel_show_web_maps__user=user)
                    )
                )
            ),
            contains_new_to_user=Exists(
                RecordPanelShowList.objects.filter(
                    panel__menu=OuterRef("pk"), user=self.request.user, new_to_user=True
                ).values("pk")
            ),
        )

        return self.get_serializer_class().setup_eager_loading(ann_queryset.distinct())

    @action(methods=["PATCH"], url_path="MoveUp", detail=True)
    def move_up_menu(self, request, pk=None):
        record_menu: RecordMenu = self.get_object()
        company: Company = record_menu.company
        user: User = self.request.user

        try:
            menu_to_move_up = RecordMenuRelation.objects.get(
                company=company, user=user, record_menu=record_menu
            )
        except RecordMenuRelation.DoesNotExist:
            raise serializers.ValidationError(
                "kartado.error.record_menu.provided_menu_doest_have_a_relation"
            )
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.record_menu.unknown_error_while_getting_menu_relation"
            )

        # Rebalance before movement
        rebalance_visible_menus_orders(str(user.pk), str(company.pk))

        next_menu = (
            RecordMenuRelation.objects.filter(
                hide_menu=False,
                company=company,
                user=user,
                record_menu__system_default=False,
                order__lt=menu_to_move_up.order,
            )
            .order_by("order")
            .exclude(pk=menu_to_move_up.pk)
            .last()
        )
        if not next_menu:
            raise serializers.ValidationError(
                "kartado.error.menu_is_already_at_the_top"
            )

        # Swap the order of the menus
        menu_to_move_up.order, next_menu.order = (
            next_menu.order,
            menu_to_move_up.order,
        )
        try:
            bulk_update_with_history(
                [menu_to_move_up, next_menu],
                RecordMenuRelation,
                use_django_bulk=True,
            )
        except Exception:
            return Response(
                data=[
                    {
                        "status": "kartado.error.record_menu.move_up",
                    }
                ],
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            data=[
                {
                    "status": "ok",
                }
            ],
            status=status.HTTP_200_OK,
        )

    @action(methods=["PATCH"], url_path="MoveDown", detail=True)
    def move_down_menu(self, request, pk=None):
        record_menu: RecordMenu = self.get_object()
        company: Company = record_menu.company
        user: User = self.request.user

        try:
            menu_to_move_down = RecordMenuRelation.objects.get(
                company=company, user=user, record_menu=record_menu
            )
        except RecordMenuRelation.DoesNotExist:
            raise serializers.ValidationError(
                "kartado.error.record_menu.provided_menu_doest_have_a_relation"
            )
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.record_menu.unknown_error_while_getting_menu_relation"
            )

        # Rebalance before movement
        rebalance_visible_menus_orders(str(user.pk), str(company.pk))

        previous_menu = (
            RecordMenuRelation.objects.filter(
                hide_menu=False,
                company=company,
                user=user,
                record_menu__system_default=False,
                order__gt=menu_to_move_down.order,
            )
            .order_by("order")
            .exclude(pk=menu_to_move_down.pk)
            .first()
        )
        if not previous_menu:
            raise serializers.ValidationError(
                "kartado.error.menu_is_already_at_the_bottom"
            )

        # Swap the order of the menus
        menu_to_move_down.order, previous_menu.order = (
            previous_menu.order,
            menu_to_move_down.order,
        )
        try:
            bulk_update_with_history(
                [menu_to_move_down, previous_menu],
                RecordMenuRelation,
                use_django_bulk=True,
            )
        except Exception:
            return Response(
                data=[
                    {
                        "status": "kartado.error.record_menu.move_down",
                    }
                ],
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            data=[
                {
                    "status": "ok",
                }
            ],
            status=status.HTTP_200_OK,
        )

    @action(methods=["GET"], url_path="CanBeDeleted", detail=True)
    def can_be_deleted(self, request, pk=None):
        instance = self.get_object()
        can_be_deleted = not (instance.record_menu_reportings.exists())
        return Response(
            data=[
                {
                    "can_be_deleted": can_be_deleted,
                }
            ],
            status=status.HTTP_200_OK,
        )

    @action(methods=["POST"], url_path="BulkOrder", detail=False)
    def bulk_order(self, request, pk=None):
        try:
            company = Company.objects.get(pk=request.data["company"]["id"])
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.record_menu.request_body_requires_a_valid_company"
            )

        # Ensure a proper structure and sort the IDs according to the provided order
        request_data = dict_to_casing(request.data, "underscore")
        try:
            input_menus = sorted(request_data["menus"], key=lambda m: int(m["order"]))

            sorted_menu_ids = []
            sorted_orders = []
            for input_menu in input_menus:
                sorted_menu_ids.append(input_menu["menu_id"])
                sorted_orders.append(int(input_menu["order"]))
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.record_menu.malformed_request_body"
            )

        # Never accept duplicate IDs to avoid ambiguous ordering (ex: same ID having order 3 and 12)
        if len(sorted_menu_ids) != len(set(sorted_menu_ids)):
            raise serializers.ValidationError(
                "kartado.error.record_menu.duplicate_menu_ids_were_provided"
            )
        # Never accept duplicate order values since it can cause confusion on which menu comes first
        if len(sorted_orders) != len(set(sorted_orders)):
            raise serializers.ValidationError(
                "kartado.error.record_menu.duplicate_order_values_were_provided"
            )

        user = request.user
        relations = (
            RecordMenuRelation.objects.filter(
                company=company,
                user=user,
                hide_menu=False,
                record_menu__system_default=False,
            )
            .prefetch_related("record_menu")
            .only("uuid", "order", "record_menu")
        )
        menu_id_to_relation = {str(rel.record_menu.uuid): rel for rel in relations}

        # Initial check that menus match (more intricate version down there)
        if len(sorted_menu_ids) != relations.count():
            raise serializers.ValidationError(
                "kartado.error.record_menu.all_visible_menus_for_the_user_need_to_be_provided"
            )

        # NOTE: We'll write an equivalent logic to the function rebalance_visible_menus_orders()
        # This way even if we receive a crazy order like -35, we'll be able to apply the needed changes
        updated_relation_instances = []
        try:
            new_order = 0
            for sor_menu_id in sorted_menu_ids:
                menu_instance = menu_id_to_relation[sor_menu_id]
                menu_instance.order = new_order
                updated_relation_instances.append(menu_instance)

                new_order += 1
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.record_menu.provided_menu_is_not_part_of_user_visible_menus"
            )

        bulk_update_with_history(
            objs=updated_relation_instances,
            model=RecordMenuRelation,
            use_django_bulk=True,
        )

        return Response({"data": {"status": "OK"}})


class ReportingRelationFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    name = CharFilter()
    outward = CharFilter()
    inward = CharFilter()

    class Meta:
        model = ReportingRelation
        fields = ["uuid", "company", "name", "outward", "inward"]


class ReportingRelationView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = ReportingRelationSerializer
    permission_classes = [IsAuthenticated, ReportingRelationPermissions]
    filterset_class = ReportingRelationFilter
    permissions = None

    ordering_fields = ["uuid", "company__name", "name", "outward", "inward"]
    ordering = "name"

    def get_queryset(self):
        queryset = None
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ReportingRelation.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ReportingRelation",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ReportingRelation.objects.none())

            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ReportingRelation.objects.filter(company_id=user_company),
                )
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ReportingRelation.objects.filter(company_id__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ReportingInReportingFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    parent = UUIDListFilter()
    child = UUIDListFilter()
    reporting_relation = UUIDListFilter()
    jobs_rdos_user_firms = CharFilter(method="get_jobs_rdos_user_firms")

    class Meta:
        model = ReportingInReporting
        fields = ["uuid", "parent", "child", "reporting_relation"]

    def get_jobs_rdos_user_firms(self, queryset, name, value):
        jobs_section, rdos_section = value.split("|")

        if "company" not in self.data:
            return queryset
        else:
            company = Company.objects.get(uuid=self.data["company"])

        jobs_uuids = get_uuids_jobs_user_firms(jobs_section, company, self.request.user)
        rdos_uuids = get_uuids_rdos_user_firms(rdos_section, company, self.request.user)

        return queryset.filter(
            Q(parent__job_id__in=jobs_uuids)
            | Q(parent__reporting_multiple_daily_reports__in=rdos_uuids)
            | Q(child__job_id__in=jobs_uuids)
            | Q(child__reporting_multiple_daily_reports__in=rdos_uuids)
        ).distinct()


class ReportingInReportingView(viewsets.ModelViewSet):
    serializer_class = ReportingInReportingSerializer
    permission_classes = [IsAuthenticated, ReportingInReportingPermissions]
    filterset_class = ReportingInReportingFilter
    permissions = None

    ordering_fields = [
        "uuid",
        "parent",
        "child",
        "reporting_relation",
        "reporting_relation__company",
        "reporting_relation__company__name",
        "reporting_relation__name",
        "reporting_relation__outward",
        "reporting_relation__inward",
    ]
    ordering = "uuid"

    def get_queryset(self):
        queryset = None
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ReportingInReporting.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ReportingInReporting",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ReportingInReporting.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ReportingInReporting.objects.filter(
                        Q(reporting_relation__company_id=user_company)
                        & (
                            Q(parent__created_by=self.request.user)
                            | Q(child__created_by=self.request.user)
                        )
                    ),
                )
            if "firm" in allowed_queryset:
                user_firms = list(
                    (
                        self.request.user.user_firms.filter(company_id=user_company)
                    ).union(
                        self.request.user.user_firms_manager.filter(
                            company_id=user_company
                        )
                    )
                )
                queryset = join_queryset(
                    queryset,
                    ReportingInReporting.objects.filter(
                        Q(reporting_relation__company_id=user_company)
                        & (
                            Q(parent__firm__in=user_firms)
                            | Q(child__firm__in=user_firms)
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ReportingInReporting.objects.filter(
                        reporting_relation__company_id=user_company
                    ),
                )
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ReportingInReporting.objects.filter(
                reporting_relation__company_id__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ReportingWithInventoryCandidatesView(viewsets.ReadOnlyModelViewSet):
    """
    Read-only view for Reporting with inventory_candidates field.
    Provides paginated list and retrieve endpoints with filtering and ordering.
    """

    permission_classes = [IsAuthenticated, ReportingPermissions]
    serializer_class = ReportingWithInventoryCandidates
    filter_backends = [
        filters.DjangoFilterBackend,
        ReportingOrderingFilter,
    ]
    filterset_class = ReportingFilter
    permissions = None
    authentication_types = ["spreadsheetOnly", "all"]
    resource_name = "Reporting"

    ordering_fields = [
        "uuid",
        "firm__name",
        "number",
        "road_name",
        "km",
        "project_km",
        "direction",
        "lane",
        "status__name",
        "occurrence_type__name",
        "executed_at",
        "due_at",
        "found_at",
        "created_at",
        "updated_at",
        "road__name",
        "created_by__first_name",
        "approval_step__name",
        "job__number",
        "job__start_date",
        "job__end_date",
        "construction",
        "record_panel",
        "firm__subcompany__name",
        "menu__name",
        "parent__number",
    ]
    ordering = "uuid"

    def get_serializer_context(self):
        context = super(
            ReportingWithInventoryCandidatesView, self
        ).get_serializer_context()
        user = context["request"].user
        permissions = context["view"].permissions

        # The current user is not anonymous and the action is list or retrieve
        if not user.is_anonymous and self.action in ["list", "retrieve"]:
            try:
                if permissions:
                    context.update(
                        {
                            "user_firms": user.user_firms.filter(
                                company_id=permissions.company_id
                            )
                        }
                    )
            except AttributeError as err:
                # Send the exception to Sentry
                sentry_sdk.capture_exception(err)

            # Inform the serializer that we're dealing with antt queryset
            antt_qs_name = "antt_supervisor_agency"
            context[antt_qs_name] = (
                antt_qs_name in permissions.get_allowed_queryset()
                if permissions
                else False
            )

        return context

    def get_queryset(self):
        queryset = get_reporting_queryset(
            self.action,
            self.request,
            self.permissions,
            self,
        ).exclude(occurrence_type__occurrence_kind="2")

        # Filter to only include reportings with no parent
        queryset = queryset.filter(parent__isnull=True)

        # Filter to only include reportings with at least one inventory candidate
        queryset = queryset.filter(inventory_candidates__isnull=False)

        # Filter to only include editable reportings
        queryset = queryset.filter(editable=True)

        company_id = self.request.query_params.get("company")
        if company_id:
            company = Company.objects.get(uuid=company_id)
            bond_types = get_bond_occurrence_types(company)
            if bond_types is not None:
                queryset = queryset.filter(occurrence_type_id__in=bond_types)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())
