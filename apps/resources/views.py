import copy
import json
import os
import uuid
from collections import defaultdict
from datetime import datetime

from arrow import Arrow
from dateutil import parser
from dateutil.relativedelta import relativedelta
from django.core.files.base import ContentFile
from django.db.models import F, OuterRef, Q, Subquery, signals
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_json_api import serializers

from apps.companies.models import Company, Firm
from apps.daily_reports.filters import DailyReportContractUsageFilter
from apps.daily_reports.models import (
    DailyReportContractUsage,
    DailyReportEquipment,
    DailyReportVehicle,
    DailyReportWorker,
)
from apps.daily_reports.signals import (
    auto_create_contract_usage_and_fill_contract_prices_for_equipment,
    auto_create_contract_usage_and_fill_contract_prices_for_vehicle,
    auto_create_contract_usage_and_fill_contract_prices_for_worker,
)
from apps.files.models import GenericFile
from apps.resources.filters import (
    ContractAdditiveFilter,
    ContractFilter,
    ContractItemAdministrationFilter,
    ContractItemPerformanceFilter,
    ContractItemUnitPriceFilter,
    ContractPeriodFilter,
    ContractServiceFilter,
    FieldSurveyExportFilter,
    FieldSurveyFilter,
    FieldSurveyRoadFilter,
    FieldSurveySignatureFilter,
    MeasurementBulletinExportFilter,
    ResourceFilter,
)
from apps.resources.helpers.contract_history_download import (
    ContractHistoryDownload,
    contract_history_download_async,
)
from apps.resources.models import (
    Contract,
    ContractAdditive,
    ContractItemAdministration,
    ContractItemPerformance,
    ContractItemPerformanceBulletin,
    ContractItemUnitPrice,
    ContractPeriod,
    ContractService,
    FieldSurvey,
    FieldSurveyExport,
    FieldSurveyRoad,
    FieldSurveySignature,
    MeasurementBulletinExport,
    Resource,
)
from apps.resources.permissions import (
    ContractAdditivePermissions,
    ContractItemAdministrationPermissions,
    ContractItemPerformancePermissions,
    ContractItemUnitPricePermissions,
    ContractPeriodPermissions,
    ContractPermissions,
    ContractServicePermissions,
    FieldSurveyExportPermissions,
    FieldSurveyPermissions,
    FieldSurveyRoadPermissions,
    FieldSurveySignaturePermissions,
    HumanResourceItemPermissions,
    HumanResourcePermissions,
    HumanResourceUsagePermissions,
    MeasurementBulletinExportPermissions,
    ResourcePermissions,
)
from apps.resources.serializers import (
    ContractAdditiveSerializer,
    ContractItemAdministrationSerializer,
    ContractItemPerformanceSerializer,
    ContractItemUnitPriceSerializer,
    ContractPeriodSerializer,
    ContractSerializer,
    ContractServiceSerializer,
    ContractWithoutMoneySerializer,
    CustomResourceSerializer,
    FieldSurveyExportSerializer,
    FieldSurveyRoadSerializer,
    FieldSurveySerializer,
    FieldSurveySignatureSerializer,
    HumanResourceItemSerializer,
    HumanResourceSerializer,
    HumanResourceUsageSerializer,
    MeasurementBulletinExportSerializer,
    ResourceSerializer,
)
from apps.resources.signals import calculate_contract_prices_after_survey_change
from apps.service_orders.const import resource_approval_status
from apps.service_orders.filters import ProcedureResourceFilter
from apps.service_orders.models import ProcedureResource, ServiceOrderResource
from apps.service_orders.signals import generate_contract_resource_todos
from apps.service_orders.views import ProcedureResourceView, ServiceOrderResourceView
from helpers.apps.contract_service_resource_summary import ResourceSummaryEndpoint
from helpers.apps.model_history import History
from helpers.apps.pdfs import PDFEndpoint
from helpers.apps.preview_download_export import (
    PreviewDownloadExport,
    preview_download_export_async,
)
from helpers.error_messages import error_message
from helpers.extra_hours_download import ExtraHoursExport, extra_hours_export_async
from helpers.histories import bulk_update_with_history
from helpers.json_parser import JSONParserWithUnformattedKeys
from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset
from helpers.strings import minutes_to_hour_str


class ResourceViewSet(viewsets.ModelViewSet):
    serializer_class = ResourceSerializer
    permission_classes = [IsAuthenticated, ResourcePermissions]
    filterset_class = ResourceFilter
    permissions = None
    ordering = "uuid"
    ordering_fields = ["name", "contract_service_description", "order"]

    def has_necessary_query_params(self, query_params: list):
        # check necessary params
        return any(
            [
                self.request.query_params.get(query_param) != "false"
                for query_param in query_params
            ]
        )

    def get_serializer_class(self):
        if self.has_necessary_query_params(
            ["only_unit_price_contracts", "show_unit_price_contracts", "uuid"]
        ):
            return CustomResourceSerializer
        else:
            return self.serializer_class

    def get_queryset(self):
        queryset = Resource.objects.none()

        user_companies = self.request.user.companies.all()
        queryset = Resource.objects.filter(company__in=user_companies)
        queryset = queryset.prefetch_related("resource_service_orders__contract")
        # avoid unecessary queries
        if self.has_sort_param(
            "contract_service_description"
        ) or self.has_necessary_query_params(
            [
                "contract_service_description",
                "only_unit_price_contracts",
                "show_unit_price_contracts",
            ]
        ):
            unit_price_sub = ContractItemUnitPrice.objects.filter(
                resource__resource=OuterRef("pk")
            )
            contract_service_sub = ContractService.objects.filter(
                contract_item_unit_prices__resource__resource=OuterRef("pk")
            )
            queryset = queryset.annotate(
                contract_service_description=Subquery(
                    contract_service_sub.values("description")[:1]
                ),
                order=Subquery(unit_price_sub.values("order")[:1]),
                sort_string=Subquery(unit_price_sub.values("sort_string")[:1]),
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="History", detail=True)
    def history(self, request, pk=None):
        resource_obj = self.get_object()
        obj_relations = {resource_obj: ["all"]}
        obj = History(resource_obj, obj_relations)
        return obj.generate_response_data()

    def has_sort_param(self, sort_name: str):
        return sort_name in self.request.query_params.get("sort", [])


def get_contract_queryset(action, request, permissions):
    queryset = None

    # On list action: limit queryset
    if action == "list":
        if "company" not in request.query_params:
            return Contract.objects.none()

        user_company = uuid.UUID(request.query_params["company"])

        if not permissions:
            permissions = PermissionManager(
                user=request.user, company_ids=user_company, model="contract"
            )

        allowed_queryset = permissions.get_allowed_queryset()

        if "none" in allowed_queryset:
            queryset = join_queryset(queryset, Contract.objects.none())
        if "entity" in allowed_queryset:
            user_entities = (
                Firm.objects.filter(users=request.user, company=user_company)
                .values_list("entity", flat=True)
                .distinct()
            )
            queryset = join_queryset(
                queryset,
                Contract.objects.filter(
                    Q(firm__entity__in=user_entities)
                    | Q(subcompany__subcompany_firms__entity__in=user_entities)
                    | Q(responsibles_hirer=request.user)
                ),
            )
        if "self" in allowed_queryset:
            user_firms = request.user.user_firms.all()
            queryset = join_queryset(
                queryset,
                Contract.objects.filter(
                    (Q(firm__in=user_firms) & Q(firm__company_id=user_company))
                    | (
                        Q(subcompany__company_id=user_company)
                        & Q(subcompany__subcompany_firms__in=user_firms)
                    )
                ),
            )
        if "all" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                Contract.objects.filter(
                    Q(firm__company=user_company) | Q(subcompany__company=user_company)
                ),
            )

    # If queryset isn't set by any means above
    if queryset is None:
        user_companies = request.user.companies.all()
        queryset = Contract.objects.filter(
            Q(firm__company__in=user_companies)
            | Q(subcompany__company__in=user_companies)
        )

    return queryset.distinct()


class FieldSurveyRoadView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = FieldSurveyRoadSerializer
    permission_classes = [IsAuthenticated, FieldSurveyRoadPermissions]
    filterset_class = FieldSurveyRoadFilter
    permissions = None
    ordering_fields = ["uuid", "contract", "end_km", "start_km", "road"]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return FieldSurveyRoad.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="FieldSurveyRoad",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, FieldSurveyRoad.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    FieldSurveyRoad.objects.filter(
                        contract__subcompany__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = FieldSurveyRoad.objects.filter(
                contract__subcompany__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class FieldSurveyView(viewsets.ModelViewSet):
    serializer_class = FieldSurveySerializer
    permission_classes = [IsAuthenticated, FieldSurveyPermissions]
    parser_classes = [JSONParserWithUnformattedKeys]
    parser_keys_to_keep = ["grades"]
    filterset_class = FieldSurveyFilter
    permissions = None
    ordering_fields = ["uuid", "contract"]

    def get_queryset(self):
        queryset = None
        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return FieldSurvey.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="FieldSurvey",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, FieldSurvey.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    FieldSurvey.objects.filter(
                        contract__subcompany__company_id=user_company
                    ),
                )
        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = FieldSurvey.objects.filter(
                contract__subcompany__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["post"], url_path="Approval", detail=True)
    def approval(self, request, pk=None):
        obj = self.get_object()

        if "approve" in request.data.keys():
            approval_flag = request.data.get("approve", False)
            if obj.measurement_bulletin:
                return Response(
                    data=[
                        {
                            "detail": "Não é possível alterar o status de um recurso que já faz parte de um boletim de medição.",
                            "source": {"pointer": "/data"},
                            "status": status.HTTP_400_BAD_REQUEST,
                        }
                    ],
                    status=status.HTTP_400_BAD_REQUEST,
                )

            obj.approval_date = datetime.now()
            obj.approved_by = request.user

            obj.approval_status = (
                resource_approval_status.APPROVED_APPROVAL
                if approval_flag
                else resource_approval_status.DENIED_APPROVAL
            )
            # call save because FieldSurvey has signals to be called
            obj.save()

            return Response({"data": {"status": "OK"}})

        return Response(
            data=[
                {
                    "detail": "O parâmetro approve (bool) não foi localizado.",
                    "source": {"pointer": "/data"},
                    "status": status.HTTP_400_BAD_REQUEST,
                }
            ],
            status=status.HTTP_400_BAD_REQUEST,
        )


class ContractView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ContractPermissions]
    parser_classes = [JSONParserWithUnformattedKeys]
    parser_keys_to_keep = ["survey_default"]
    filterset_class = ContractFilter
    permissions = None
    resource_name = "Contract"
    ordering_fields = [
        "uuid",
        "name",
        "created_at",
        "contract_start",
        "contract_end",
        "roads",
        "survey_responsibles_hirer__first_name",
        "survey_responsibles_hirer__last_name",
        "survey_responsibles_hired__first_name",
        "survey_responsibles_hired__last_name",
        "responsible_hirer__first_name",
        "responsible_hirer__last_name",
        "responsible_hired__first_name",
        "responsible_hired__last_name",
        "extra_info__r_c_number",
        "firm__name",
        "status__name",
        "total_price",
        "spent_price",
    ]
    ordering = "uuid"
    queryset = Contract.objects.none()

    def get_serializer_class(self):
        if self.permissions and self.permissions.has_permission("can_view_money"):
            return ContractSerializer
        return ContractWithoutMoneySerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = get_contract_queryset(self.action, self.request, self.permissions)

        self.queryset = self.get_serializer_class().setup_eager_loading(
            queryset.filter(
                Q(firm__is_company_team=False) | Q(subcompany__subcompany_type="HIRED")
            ).distinct()
        )
        return self.queryset

    @action(methods=["get"], url_path="PDF", detail=True)
    def pdf_contract(self, request, pk=None):
        obj = self.get_object()
        endpoint = PDFEndpoint(obj, pk, request, "Contract")
        return endpoint.get_response()

    @action(methods=["post"], url_path="BulkApproval", detail=False)
    def bulk_approval(self, request, pk=None):
        querysets_for_approval = []

        def append_queryset(field_name, model_class, fields_to_prefetch=[]):
            """
            Retrieves the provided field and queries the resulting IDs according
            to the model_class provided.
            If any results are found, the queryset is added to querysets_for_approval.
            """
            if field_name in request.data:
                query_ids = [
                    field_content["id"] for field_content in request.data[field_name]
                ]
                result_queryset = model_class.objects.filter(
                    pk__in=query_ids
                ).prefetch_related(*fields_to_prefetch)

                if result_queryset:
                    querysets_for_approval.append(result_queryset)

        common_daily_report_prefetchs = [
            "contract_item_administration",
            "contract_item_administration__resource__contract",
            "contract_item_administration__resource__contract__bulletins",
            "contract_item_administration__resource__contract__resources",
            "contract_item_administration__resource__contract__resources__serviceorderresource_procedures",
            "contract_item_administration__resource__contract__performance_services",
        ]

        # Process the different fields
        append_queryset("procedure_resources", ProcedureResource)
        append_queryset(
            "daily_report_workers",
            DailyReportWorker,
            fields_to_prefetch=["worker_contract_usage"]
            + common_daily_report_prefetchs,
        )
        append_queryset(
            "daily_report_vehicles",
            DailyReportVehicle,
            fields_to_prefetch=["vehicle_contract_usage"]
            + common_daily_report_prefetchs,
        )
        append_queryset(
            "daily_report_equipment",
            DailyReportEquipment,
            fields_to_prefetch=["equipment_contract_usage"]
            + common_daily_report_prefetchs,
        )
        append_queryset(
            "field_survey",
            FieldSurvey,
            fields_to_prefetch=["contract__subcompany__company"],
        )

        if "approve" in request.data.keys():
            approval_flag = request.data.get("approve", False)

            # We're going to disable these signals to apply the logic without doing too many queries (remember to reconnect)
            # NOTE: The disabled signals should never affect the necessary logic for the bulk approval (we're disabling mostly unecessary recalcs)
            signals.post_save.disconnect(
                generate_contract_resource_todos, sender=ServiceOrderResource
            )
            signals.post_save.disconnect(
                auto_create_contract_usage_and_fill_contract_prices_for_worker,
                sender=DailyReportWorker,
            )
            signals.post_save.disconnect(
                auto_create_contract_usage_and_fill_contract_prices_for_vehicle,
                sender=DailyReportVehicle,
            )
            signals.post_save.disconnect(
                auto_create_contract_usage_and_fill_contract_prices_for_equipment,
                sender=DailyReportEquipment,
            )
            signals.post_save.disconnect(
                calculate_contract_prices_after_survey_change,
                sender=FieldSurvey,
            )

            for queryset in querysets_for_approval:
                # If ProcedureResource and part of a MeasurementBulletin, raise error
                is_procedure_resource = queryset.model.__name__ == "ProcedureResource"
                is_field_survey = queryset.model.__name__ == "FieldSurvey"
                any_in_measurement_bulletin = (
                    queryset.filter(measurement_bulletin__isnull=False).exists()
                    if is_procedure_resource or is_field_survey
                    else None
                )
                if any_in_measurement_bulletin:
                    return Response(
                        data=[
                            {
                                "detail": "Não é possível alterar o status de um recurso que já faz parte de um boletim de medição.",
                                "source": {"pointer": "/data"},
                                "status": status.HTTP_400_BAD_REQUEST,
                            }
                        ],
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Process approvals
                for instance in queryset:
                    self.check_object_permissions(request, instance)
                    instance.approval_date = timezone.now()
                    instance.approved_by = request.user

                    instance.approval_status = (
                        resource_approval_status.APPROVED_APPROVAL
                        if approval_flag
                        else resource_approval_status.DENIED_APPROVAL
                    )
                    # Call save to trigger signals
                    instance.save()

            # Reconnect signals
            signals.post_save.connect(
                generate_contract_resource_todos, sender=ServiceOrderResource
            )
            signals.post_save.connect(
                auto_create_contract_usage_and_fill_contract_prices_for_worker,
                sender=DailyReportWorker,
            )
            signals.post_save.connect(
                auto_create_contract_usage_and_fill_contract_prices_for_vehicle,
                sender=DailyReportVehicle,
            )
            signals.post_save.connect(
                auto_create_contract_usage_and_fill_contract_prices_for_equipment,
                sender=DailyReportEquipment,
            )
            signals.post_save.connect(
                calculate_contract_prices_after_survey_change,
                sender=FieldSurvey,
            )

            return Response({"data": {"status": "OK"}})
        else:
            return Response(
                data=[
                    {
                        "detail": "O parâmetro approve (bool) não foi localizado.",
                        "source": {"pointer": "/data"},
                        "status": status.HTTP_400_BAD_REQUEST,
                    }
                ],
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(methods=["GET"], url_path="PreviewDownload", detail=True)
    def preview_download(self, request, pk=None):

        query_params = copy.deepcopy(request.query_params)

        try:
            company = query_params["company"]
            company_name = Company.objects.get(pk=company).name
        except Exception:
            return error_message(
                400,
                'Parâmetro "Unidade" é obrigatório',
            )

        work_days = query_params.pop("work_days", None)
        query_params["contract"] = str(pk)
        if work_days in [None, [""]]:
            return error_message(
                400,
                'Parâmetro "Dias úteis" é obrigatório',
            )
        else:
            try:
                work_days = int(work_days[0])
            except Exception:
                return error_message(
                    400,
                    'Parâmetro "Dias úteis" deve ser um número inteiro',
                )

        # ProcedureResource queryset and filter
        procedure_resource_qs = ProcedureResource.objects.filter(
            service_order_resource__resource__company__uuid=company
        )
        procedure_resources = ProcedureResourceFilter(
            query_params, procedure_resource_qs
        ).qs.values_list("uuid", flat=True)

        base_contract_usages = DailyReportContractUsage.objects.filter(
            company_id=company
        )

        daily_report_qs = base_contract_usages.filter(
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
                    & Q(equipment__multiple_daily_reports__day_without_work=False)
                    & Q(equipment__equipment_relations__active=True)
                )
            ),
            contract_item_administration__isnull=False,
        )
        daily_reports = DailyReportContractUsageFilter(
            query_params, daily_report_qs
        ).qs.values_list("uuid", flat=True)
        procedure_resources_uuids = [str(uuid) for uuid in procedure_resources]
        daily_reports_uuids = [str(uuid) for uuid in daily_reports]

        if len(procedure_resources_uuids) + len(daily_reports_uuids) > 50000:
            raise serializers.ValidationError(
                "Você está tentando gerar uma exportação com mais de 50.000 itens. Por favor, aplique filtros."
            )

        uuid_list = [procedure_resources_uuids, daily_reports_uuids]

        # Create and upload uuid list to prevent errors if there are too many items
        file_uuid = uuid.uuid4()
        generic_file = GenericFile.objects.create(pk=file_uuid)
        temp_path = "/tmp/preview_download_uuid/"
        os.makedirs(temp_path, exist_ok=True)
        json_name = "{}.json".format(str(file_uuid))
        json_file_path = temp_path + json_name
        with open(json_file_path, "w") as outfile:
            json.dump(uuid_list, outfile)

        json_file = open(json_file_path, "rb")
        generic_file.file.save(json_name, ContentFile(json_file.read()))

        # Delete files
        for file_name in os.listdir(temp_path):
            os.remove(temp_path + file_name)

        # Delete temporary folder
        os.rmdir(temp_path)

        preview_download = PreviewDownloadExport(company_name=company_name)

        # Generate URL and trigger async process
        filename = preview_download.filename
        object_name = preview_download.object_name
        url = preview_download.get_s3_url()
        preview_download_export_async(
            str(file_uuid), filename, object_name, company_name, str(pk), work_days
        )

        return Response(
            {
                "type": "Export",
                "attributes": {"url": url, "name": filename},
            }
        )

    @action(methods=["GET"], url_path="HistoryDownload", detail=True)
    def history_download(self, request, pk=None):

        try:
            company = request.query_params["company"]
        except Exception:
            return error_message(
                400,
                'Parâmetro "Unidade" é obrigatório',
            )

        contract_id = str(pk)

        contract_history = ContractHistoryDownload()

        # Generate URL and trigger async process
        filename = contract_history.filename
        object_name = contract_history.object_name
        url = contract_history.get_s3_url()

        contract_history_download_async(company, contract_id, filename, object_name)

        return Response(
            {
                "type": "Export",
                "attributes": {"url": url, "name": filename},
            }
        )

    @action(methods=["GET"], url_path="ExtraHoursDownload", detail=True)
    def extra_hours_download(self, request, pk=None):
        query_params = copy.deepcopy(request.query_params)

        try:
            company = query_params["company"]
        except Exception:
            return error_message(
                400,
                'Parâmetro "Unidade" é obrigatório',
            )

        required_fields = ["creation_date_after", "creation_date_before"]

        if not set(required_fields).issubset(query_params.keys()):
            return error_message(400, "Faltam parâmetros obrigatórios")

        creation_date_after = query_params.get("creation_date_after")
        creation_date_before = query_params.get("creation_date_before")

        query_params["contract"] = str(pk)

        # DailyReportContractUsage queryset and filter
        base_contract_usages = DailyReportContractUsage.objects.filter(
            company_id=company
        )

        daily_report_qs = base_contract_usages.filter(
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
                    & Q(equipment__multiple_daily_reports__day_without_work=False)
                    & Q(equipment__equipment_relations__active=True)
                )
            ),
            contract_item_administration__isnull=False,
        )
        daily_reports = DailyReportContractUsageFilter(
            query_params, daily_report_qs
        ).qs.values_list("uuid", flat=True)
        uuid_list = [str(uuid) for uuid in daily_reports]

        # Create and upload uuid list to prevent errors if there are too many items
        file_uuid = uuid.uuid4()
        generic_file = GenericFile.objects.create(pk=file_uuid)
        temp_path = "/tmp/extra_hours_download_uuid/"
        os.makedirs(temp_path, exist_ok=True)
        json_name = "{}.json".format(str(file_uuid))
        json_file_path = temp_path + json_name
        with open(json_file_path, "w") as outfile:
            json.dump(uuid_list, outfile)

        json_file = open(json_file_path, "rb")
        generic_file.file.save(json_name, ContentFile(json_file.read()))

        # Delete files
        for file_name in os.listdir(temp_path):
            os.remove(temp_path + file_name)

        # Delete temporary folder
        os.rmdir(temp_path)

        extra_hours_download = ExtraHoursExport()

        # Generate URL and trigger async process
        filename = extra_hours_download.filename
        object_name = extra_hours_download.object_name
        url = extra_hours_download.get_s3_url()
        extra_hours_export_async(
            str(file_uuid),
            filename,
            object_name,
            str(pk),
            company,
            creation_date_after,
            creation_date_before,
        )

        return Response(
            {
                "type": "Export",
                "attributes": {"url": url, "name": filename},
            }
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        firms_context = None
        if context["view"].permissions:
            user_company = context["view"].permissions.company_id
            firms_context = Firm.objects.filter(company_id=user_company).values(
                "uuid",
                "firm_contract_services__unit_price_service_contracts",
                "firm_contract_services__administration_service_contracts",
                "firm_contract_services__performance_service_contracts",
            )
        context.update({"firms": firms_context})
        return context


class ContractServiceView(viewsets.ModelViewSet):
    serializer_class = ContractServiceSerializer
    permission_classes = [IsAuthenticated, ContractServicePermissions]
    filterset_class = ContractServiceFilter
    permissions = None
    resource_name = "ContractService"

    ordering_fields = [
        "uuid",
        "description",
        "firms",
        "contract_item_unit_prices",
        "contract_item_administration",
        "created_at",
    ]
    ordering = "created_at"

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return ContractService.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ContractService",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ContractService.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ContractService.objects.filter(firms__company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ContractService.objects.filter(firms__company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_destroy(self, instance):
        if (
            instance.contract_item_unit_prices.exists()
            or instance.contract_item_administration.exists()
            or instance.contract_item_performance.exists()
        ):
            raise serializers.ValidationError(
                "kartado.error.contract_service.cannot_be_deleted_because_it_has_items"
            )
        instance.delete()

    @action(methods=["get"], url_path="ResourceSummary", detail=True)
    def resource_summary(self, request, pk=None):
        contract_service_id = self.kwargs.get("pk", False)
        contract_service = get_object_or_404(ContractService, pk=contract_service_id)
        obj = ResourceSummaryEndpoint(contract_service, request)
        obj.set_params()
        obj.set_response_items()
        return obj.get_response()

    @action(methods=["POST"], url_path="ContractItemsOrdering", detail=False)
    def contract_items_ordering(self, request, pk=None):
        if "company" not in request.query_params:
            return error_message(400, 'Parâmetro "Unidade" é obrigatório')
        input_data = json.loads(request.body).get("data", None)
        if input_data is None:
            raise serializers.ValidationError(
                "kartado.error.contract_service.data_key_not_found_on_body"
            )
        item_type = input_data.pop("item_type", None)
        if item_type is None:
            raise serializers.ValidationError(
                "kartado.error.contract_service.item_type_is_missing"
            )
        updated_items = []
        for contract_service_uuid, contract_item_list in input_data.items():
            contract_service = ContractService.objects.get(uuid=contract_service_uuid)
            if item_type == "ContractItemUnitPrice":
                item_queryset = contract_service.contract_item_unit_prices.all()
            elif item_type == "ContractItemAdministration":
                item_queryset = contract_service.contract_item_administration.all()
            elif item_type == "ContractItemPerformance":
                item_queryset = contract_service.contract_item_performance.all()
            else:
                raise serializers.ValidationError(
                    "kartado.error.contract_service.item_type_is_not_mapped"
                )
            queryset_count = item_queryset.count()
            order_list = list(contract_item_list.values())
            if queryset_count != len(
                set(contract_item_list.keys())
            ) or queryset_count != len(set(order_list)):
                raise serializers.ValidationError(
                    "kartado.error.contract_service.there_are_missing_or_duplicated_values_in_contract_item_list"
                )
            if min(order_list) != 1 or max(order_list) != queryset_count:
                raise serializers.ValidationError(
                    "kartado.error.contract_service.order_values_are_not_correct"
                )

            for item_uuid, order in contract_item_list.items():
                updated_item = item_queryset.get(uuid=item_uuid)
                updated_item.order = order
                updated_items.append(updated_item)
        bulk_update_with_history(
            updated_items, eval(item_type), use_django_bulk=True, user=self.request.user
        )

        return Response({"result": "OK"})


class ContractItemUnitPriceView(viewsets.ModelViewSet):
    serializer_class = ContractItemUnitPriceSerializer
    permission_classes = [IsAuthenticated, ContractItemUnitPricePermissions]
    filterset_class = ContractItemUnitPriceFilter
    permissions = None
    resource_name = "ContractItemUnitPrice"

    ordering_fields = ["uuid", "description", "firms", "sort_string", "order"]
    ordering = "uuid"

    def get_queryset(self):
        queryset = None
        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return ContractItemUnitPrice.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ContractItemUnitPrice",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ContractItemUnitPrice.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ContractItemUnitPrice.objects.filter(
                        Q(entity__company_id=user_company)
                        | Q(resource__contract__subcompany__company_id=user_company)
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ContractItemUnitPrice.objects.filter(
                Q(entity__company__in=user_companies)
                | Q(resource__contract__subcompany__company__in=user_companies)
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="History", detail=True)
    def history(self, request, pk=None):
        contr_i_u_p = self.get_object()
        obj_relations = {
            contr_i_u_p: ["sort_string"],
            contr_i_u_p.resource: [
                "used_price",
                "entity",
                "amount",
                "unit_price",
            ],
            contr_i_u_p.resource.resource: ["name", "unit"],
        }
        obj = History(contr_i_u_p, obj_relations)
        return obj.generate_response_data()


class ContractItemAdministrationView(viewsets.ModelViewSet):
    serializer_class = ContractItemAdministrationSerializer
    permission_classes = [
        IsAuthenticated,
        ContractItemAdministrationPermissions,
    ]
    filterset_class = ContractItemAdministrationFilter
    permissions = None
    resource_name = "ContractItemAdministration"

    ordering_fields = [
        "uuid",
        "description",
        "firms",
        "content_type__model",
        "resource_name",
        "descriptions",
        "sort_string",
        "order",
    ]
    ordering = "uuid"

    def get_queryset(self):
        queryset = None
        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return ContractItemAdministration.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ContractItemAdministration",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(
                    queryset, ContractItemAdministration.objects.none()
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ContractItemAdministration.objects.filter(
                        Q(entity__company_id=user_company)
                        | Q(resource__contract__subcompany__company_id=user_company)
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ContractItemAdministration.objects.filter(
                Q(entity__company__in=user_companies)
                | Q(resource__contract__subcompany__company__in=user_companies)
            )

        # avoid unecessary queries
        if self.has_sort_param("resource_name"):
            queryset = queryset.prefetch_related("resource__resource").annotate(
                resource_name=F("resource__resource__name")
            )
        if self.has_sort_param("descriptions"):
            queryset = queryset.prefetch_related(
                "contract_item_administration_services"
            ).annotate(
                descriptions=F("contract_item_administration_services__description")
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def has_sort_param(self, sort_name):
        return sort_name in self.request.query_params.get("sort", [])

    def perform_destroy(self, instance):
        cant_be_deleted = (
            DailyReportWorker.objects.filter(
                contract_item_administration=instance
            ).exists()
            or DailyReportEquipment.objects.filter(
                contract_item_administration=instance
            ).exists()
            or DailyReportVehicle.objects.filter(
                contract_item_administration=instance
            ).exists()
        )
        if cant_be_deleted:
            raise serializers.ValidationError(
                "kartado.error.contract_item_in_use_cannot_be_deleted"
            )
        instance.delete()

    def partial_update(self, request, *args, **kwargs):
        """
        Override partial_update to block content_type attribute edition
        when the incoming content_type is different from the current one.
        """
        # Get the current instance
        instance = self.get_object()
        current_content_type_id = (
            instance.content_type.id if instance.content_type else None
        )

        if hasattr(request, "data") and request.data:
            incoming_content_type_id = None

            if isinstance(request.data, dict):
                if "content_type" in request.data:
                    incoming_content_type_id = request.data["content_type"]

                    if isinstance(incoming_content_type_id, dict):
                        incoming_content_type_id = incoming_content_type_id.get("id")
                    if isinstance(incoming_content_type_id, str):
                        try:
                            incoming_content_type_id = int(incoming_content_type_id)
                        except ValueError:
                            pass

            if incoming_content_type_id is not None:
                if incoming_content_type_id != current_content_type_id:
                    return Response(
                        data=[
                            {
                                "detail": "Não é permitido editar o atributo content_type.",
                                "source": {"pointer": "/data/attributes/content_type"},
                                "status": status.HTTP_403_FORBIDDEN,
                            }
                        ],
                        status=status.HTTP_403_FORBIDDEN,
                    )

        return super().partial_update(request, *args, **kwargs)


class ContractItemPerformanceView(viewsets.ModelViewSet):
    serializer_class = ContractItemPerformanceSerializer
    permission_classes = [IsAuthenticated, ContractItemPerformancePermissions]
    filterset_class = ContractItemPerformanceFilter
    permissions = None
    resource_name = "ContractItemPerformance"

    ordering_fields = ["uuid", "firms", "sort_string", "order"]
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return ContractItemPerformance.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ContractItemPerformance",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(
                    queryset, ContractItemPerformance.objects.none()
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ContractItemPerformance.objects.filter(
                        Q(entity__company_id=user_company)
                        | Q(resource__contract__subcompany__company_id=user_company)
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ContractItemPerformance.objects.filter(
                Q(entity__company__in=user_companies)
                | Q(resource__contract__subcompany__company__in=user_companies)
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_destroy(self, instance):
        usage_exists = ContractItemPerformanceBulletin.objects.filter(
            parent_uuid=instance.pk
        ).exists()
        if usage_exists:
            raise serializers.ValidationError(
                "kartado.error.contract_item_in_use_cannot_be_deleted"
            )
        instance.delete()


class HumanResourceView(ContractView):
    permission_classes = [IsAuthenticated, HumanResourcePermissions]
    resource_name = "HumanResource"

    # Use this because we're extending a View that has this method
    def get_serializer_class(self):
        return HumanResourceSerializer

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return Contract.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="HumanResource",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, Contract.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    Contract.objects.filter(
                        firm__in=self.request.user.user_firms.all()
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    Contract.objects.filter(firm__company=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = Contract.objects.filter(firm__company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(
            queryset.filter(
                Q(firm__is_company_team=True) | Q(subcompany__subcompany_type="HIRING")
            ).distinct()
        )

    @action(methods=["get"], url_path="Summary", detail=True)
    def summary(self, request, pk=None):
        human_resource = self.get_object()
        service_orders = human_resource.service_orders.all().prefetch_related(
            "resources_service_order", "resources_service_order__resource"
        )

        fields = ["start_date", "end_date"]

        if set(fields).issubset(self.request.query_params.keys()):
            start_date = parser.parse(self.request.query_params["start_date"])
            end_date = parser.parse(self.request.query_params["end_date"])
            month_steps = list(Arrow.range("month", start_date, end_date))
        else:
            first_day_of_year = datetime.now().replace(
                month=1, day=1, hour=0, minute=0, second=0
            )
            month_steps = list(Arrow.range("month", first_day_of_year, datetime.now()))

        all_items = [
            {
                "service_id": str(service.uuid),
                "service_number": service.number,
                "service_desc": service.description,
                "resource_id": str(procedure_resource.resource.uuid),
                "resource_name": procedure_resource.resource.name,
                "procedure_date": procedure_resource.creation_date,
                "procedure_amount": procedure_resource.amount,
            }
            for service in service_orders
            for procedure_resource in service.resources_service_order.filter(
                service_order_resource__contract=human_resource,
                creation_date__gte=month_steps[0].datetime,
                creation_date__lte=(
                    month_steps[-1].datetime + relativedelta(months=1)
                ).replace(hour=0, minute=0, second=0),
            )
        ]

        all_services = defaultdict(list)
        for i in all_items:
            all_services[i["service_id"]].append(i)

        services_dict = defaultdict()
        for key, value in all_services.items():
            if value:
                resources = defaultdict(list)
                for i in value:
                    resources[i["resource_id"]].append(i)

                resources_dict = defaultdict()
                total_hours = 0
                for key1, value1 in resources.items():
                    if value1:
                        values_list = {}
                        total = 0
                        for step_date in month_steps:
                            amount_value = 0
                            key_str = str(step_date.month) + "-" + str(step_date.year)
                            for item in value1:
                                if item["procedure_date"]:
                                    creation_date = item["procedure_date"]
                                    if (creation_date.year == step_date.year) and (
                                        creation_date.month == step_date.month
                                    ):
                                        amount_value += item["procedure_amount"]
                            total += amount_value
                            values_list[key_str] = minutes_to_hour_str(amount_value)

                        resources_dict[key1] = {
                            "id": value1[0]["resource_id"],
                            "name": value1[0]["resource_name"],
                            "values": values_list,
                            "total": minutes_to_hour_str(total),
                        }
                        total_hours += total

                services_dict[key] = {
                    "id": value[0]["service_id"],
                    "number": value[0]["service_number"],
                    "description": value[0]["service_desc"],
                    "spentHours": minutes_to_hour_str(total_hours),
                    "resources": resources_dict,
                }

        services_list = []
        for key, value in services_dict.items():
            service_dict = copy.deepcopy(value)
            resources_list = []
            for key1, value1 in value["resources"].items():
                resources_list.append(value1)
            service_dict["resources"] = resources_list
            services_list.append(service_dict)

        return Response({"type": "Summary", "attributes": services_list})


class HumanResourceItemView(ServiceOrderResourceView):
    permission_classes = [IsAuthenticated, HumanResourceItemPermissions]
    resource_name = "HumanResourceItem"

    def get_serializer_class(self):
        return HumanResourceItemSerializer

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ServiceOrderResource.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="HumanResourceItem",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ServiceOrderResource.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ServiceOrderResource.objects.filter(
                        Q(contract__firm__in=self.request.user.user_firms.all())
                        & (
                            Q(created_by=self.request.user)
                            | Q(
                                contract__service_orders__actions__created_by=self.request.user
                            )
                            | Q(
                                contract__service_orders__actions__procedures__created_by=self.request.user
                            )
                            | Q(
                                contract__service_orders__actions__procedures__responsible=self.request.user
                            )
                            | Q(
                                contract__service_orders__responsibles=self.request.user
                            )
                            | Q(contract__service_orders__managers=self.request.user)
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ServiceOrderResource.objects.filter(
                        contract__firm__company=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ServiceOrderResource.objects.filter(
                contract__firm__company__in=user_companies
            ).prefetch_related("serviceorderresource_procedures")

        return self.get_serializer_class().setup_eager_loading(
            queryset.filter(
                Q(contract__firm__is_company_team=True)
                | Q(contract__subcompany__subcompany_type="HIRING")
            ).distinct()
        )


class HumanResourceUsageView(ProcedureResourceView):
    permission_classes = [IsAuthenticated, HumanResourceUsagePermissions]
    resource_name = "HumanResourceUsage"

    def get_serializer_class(self):
        return HumanResourceUsageSerializer

    def get_queryset(self):
        queryset = None
        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ProcedureResource.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="HumanResourceUsage",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ProcedureResource.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ProcedureResource.objects.filter(created_by=self.request.user),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ProcedureResource.objects.filter(
                        service_order__company=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ProcedureResource.objects.filter(
                service_order__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(
            queryset.filter(
                Q(service_order_resource__contract__firm__is_company_team=True)
                | Q(
                    service_order_resource__contract__subcompany__subcompany_type="HIRING"
                )
            ).distinct()
        )


class MeasurementBulletinExportViewSet(viewsets.ModelViewSet):
    serializer_class = MeasurementBulletinExportSerializer
    filterset_class = MeasurementBulletinExportFilter
    permissions = None
    permission_classes = [IsAuthenticated, MeasurementBulletinExportPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "created_at",
        "created_by",
        "measurement_bulletin",
        "done",
        "error",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return MeasurementBulletinExport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MeasurementBulletinExport",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(
                    queryset, MeasurementBulletinExport.objects.none()
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MeasurementBulletinExport.objects.filter(
                        Q(measurement_bulletin__contract__firm__company_id=user_company)
                        | Q(
                            measurement_bulletin__contract__subcompany__company_id=user_company
                        )
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MeasurementBulletinExport.objects.filter(
                Q(measurement_bulletin__contract__firm__company__in=user_companies)
                | Q(
                    measurement_bulletin__contract__subcompany__company__in=user_companies
                )
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class FieldSurveySignatureView(viewsets.ModelViewSet):
    serializer_class = FieldSurveySignatureSerializer
    permission_classes = [IsAuthenticated, FieldSurveySignaturePermissions]
    filterset_class = FieldSurveySignatureFilter
    permissions = None
    ordering_fields = ["uuid", "signed_at"]

    def get_queryset(self):
        queryset = None
        # Limit the querysetf if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return FieldSurveySignature.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="FieldSurveySignature",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, FieldSurveySignature.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    FieldSurveySignature.objects.filter(
                        field_survey__contract__subcompany__company_id=user_company
                    ),
                )
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    FieldSurveySignature.objects.filter(
                        Q(field_survey__responsibles_hired__uuid=self.request.user.pk)
                        | Q(field_survey__responsibles_hirer__uuid=self.request.user.pk)
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = FieldSurveySignature.objects.filter(
                Q(field_survey__contract__subcompany__company__in=user_companies)
                | Q(field_survey__contract__firm__company__in=user_companies)
            )
        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class FieldSurveyExportView(viewsets.ModelViewSet):
    serializer_class = FieldSurveyExportSerializer
    filterset_class = FieldSurveyExportFilter
    permissions = None
    permission_classes = [IsAuthenticated, FieldSurveyExportPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "created_at",
        "created_by",
        "field_survey",
        "done",
        "error",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return FieldSurveyExport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="FieldSurveyExport",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, FieldSurveyExport.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    FieldSurveyExport.objects.filter(
                        Q(field_survey__contract__firm__company_id=user_company)
                        | Q(field_survey__contract__subcompany__company_id=user_company)
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = FieldSurveyExport.objects.filter(
                Q(field_survey__contract__firm__company__in=user_companies)
                | Q(field_survey__contract__subcompany__company__in=user_companies)
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ContractAdditiveViewSet(viewsets.ModelViewSet):
    serializer_class = ContractAdditiveSerializer
    filterset_class = ContractAdditiveFilter
    permissions = None
    permission_classes = [IsAuthenticated, ContractAdditivePermissions]
    http_method_names = ["head", "options", "get", "post"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return ContractAdditive.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ContractAdditive",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ContractAdditive.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ContractAdditive.objects.filter(created_by=self.request.user),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ContractAdditive.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ContractAdditive.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ContractPeriodViewSet(viewsets.ModelViewSet):
    serializer_class = ContractPeriodSerializer
    filterset_class = ContractPeriodFilter
    permissions = None
    permission_classes = [IsAuthenticated, ContractPeriodPermissions]

    ordering = "uuid"
    ordering_fields = ["created_at", "created_by__first_name", "firms__name"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        if self.action == "list":
            if "company" not in self.request.query_params:
                return ContractPeriod.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ContractPeriod",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ContractPeriod.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ContractPeriod.objects.filter(created_by=self.request.user),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ContractPeriod.objects.filter(company_id=user_company),
                )

        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ContractPeriod.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())
