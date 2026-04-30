import json
import os
import uuid
from datetime import datetime

import sentry_sdk
from django.core.files.base import ContentFile
from django.db.models import OuterRef, Q, Subquery
from django.db.models.signals import post_init, pre_init
from django.http import JsonResponse
from django.shortcuts import render
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_json_api import serializers

from apps.approval_flows.models import ApprovalTransition
from apps.companies.models import Company, Firm
from apps.files.models import GenericFile
from apps.monitorings.models import MonitoringPlan
from apps.occurrence_records.models import OccurrenceRecord
from apps.reportings.models import Reporting
from apps.resources.models import Contract
from apps.service_orders.filters import (
    AdditionalControlFilter,
    AdministrativeInformationFilter,
    MeasurementBulletinFilter,
    PendingProcedureExportFilter,
    ProcedureFileFilter,
    ProcedureFilter,
    ProcedureResourceFilter,
    ServiceOrderActionFilter,
    ServiceOrderActionStatusFilter,
    ServiceOrderActionStatusSpecsFilter,
    ServiceOrderFilter,
    ServiceOrderResourceFilter,
    ServiceOrderWatcherFilter,
)
from apps.service_orders.helpers.email_judiciary.build_data import (
    build_data_check_email_judiciary,
)
from apps.service_orders.helpers.email_judiciary.send_emails import (
    process_judiciary_emails,
)
from helpers.apps.json_logic import apply_json_logic
from helpers.apps.measurement_bulletin_preview import MeasurementBulletinPreview
from helpers.apps.measurement_bulletin_summary import BulletinSummaryEndpoint
from helpers.apps.pdfs import PDFEndpoint
from helpers.apps.procedure_resource_export import (
    ProcedureResourceExport,
    procedure_resource_export_async,
)
from helpers.apps.service_orders import extract_pending_procedures
from helpers.error_messages import error_message
from helpers.fields import get_nested_fields
from helpers.files import check_endpoint
from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset
from helpers.serializers import get_obj_serialized
from helpers.signals import DisableSignals
from helpers.strings import dict_to_casing, keys_to_camel_case

from .const import resource_approval_status
from .models import (
    AdditionalControl,
    AdministrativeInformation,
    MeasurementBulletin,
    PendingProceduresExport,
    Procedure,
    ProcedureFile,
    ProcedureResource,
    ServiceOrder,
    ServiceOrderAction,
    ServiceOrderActionStatus,
    ServiceOrderActionStatusSpecs,
    ServiceOrderResource,
    ServiceOrderWatcher,
)
from .notifications import (
    approved_measurement_bulletin,
    measurement_bulletin_approval_change,
)
from .permissions import (
    AdditionalControlPermissions,
    AdministrativeInformationPermissions,
    MeasurementBulletinPermissions,
    PendingProceduresExportPermissions,
    ProcedureFilePermissions,
    ProcedureFlowPermissions,
    ProcedurePermissions,
    ProcedureResourcePermissions,
    ServiceOrderActionPermissions,
    ServiceOrderActionStatusPermissions,
    ServiceOrderActionStatusSpecsPermissions,
    ServiceOrderPermissions,
    ServiceOrderResourcePermissions,
    ServiceOrderWatcherPermissions,
)
from .serializers import (
    AdditionalControlSerializer,
    AdministrativeInformationSerializer,
    AdministrativeInformationWithoutMoneySerializer,
    MeasurementBulletinObjectSerializer,
    MeasurementBulletinSerializer,
    PendingProceduresExportSerializer,
    ProcedureFileObjectSerializer,
    ProcedureFileSerializer,
    ProcedureResourceSerializer,
    ProcedureResourceWithoutMoneySerializer,
    ProcedureSerializer,
    ServiceOrderActionCreateSerializer,
    ServiceOrderActionSerializer,
    ServiceOrderActionStatusSerializer,
    ServiceOrderActionStatusSpecsSerializer,
    ServiceOrderResourceObjectSerializer,
    ServiceOrderResourceSerializer,
    ServiceOrderResourceWithoutMoneySerializer,
    ServiceOrderSerializer,
    ServiceOrderWatcherSerializer,
    ServiceOrderWithoutMoneySerializer,
)


class ServiceOrderActionStatusView(ListCacheMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ServiceOrderActionStatusPermissions]
    filterset_class = ServiceOrderActionStatusFilter
    permissions = None
    serializer_class = ServiceOrderActionStatusSerializer

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "kind",
        "name",
        "color",
        "order",
        "status_specs__color",
        "status_specs__order",
    ]

    def get_queryset(self):
        queryset = None
        user_company = None

        # Tenta pegar company do query param (usado em list, retrieve, update, delete)
        if self.request and "company" in self.request.query_params:
            user_company = uuid.UUID(self.request.query_params["company"])

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ServiceOrderActionStatus.objects.none()

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ServiceOrderActionStatus",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(
                    queryset, ServiceOrderActionStatus.objects.none()
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ServiceOrderActionStatus.objects.filter(
                        companies__in=[user_company]
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            # Se company foi passada no query param, usa ela
            # Senão, usa todas as companies do usuário
            if user_company:
                queryset = ServiceOrderActionStatus.objects.filter(
                    companies__in=[user_company]
                )
            else:
                user_company = [item.uuid for item in self.request.user.companies.all()]
                queryset = ServiceOrderActionStatus.objects.filter(
                    companies__uuid__in=user_company
                )

        # Garante que user_company é uma lista para o Subquery
        if not isinstance(user_company, list):
            user_company = [user_company]

        # Busca specs da(s) company(ies) apropriada(s)
        specs = ServiceOrderActionStatusSpecs.objects.filter(
            company__uuid__in=user_company, status=OuterRef("pk")
        )

        queryset = queryset.annotate(
            color=Subquery(specs.values("color")[:1]),
            order=Subquery(specs.values("order")[:1]),
        )
        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def destroy(self, request, pk=None):
        obj = self.get_object()

        # Check if status is being used before deleting
        if (
            ServiceOrderAction.objects.filter(service_order_action_status=obj).exists()
            or ServiceOrder.objects.filter(status=obj).exists()
            or MonitoringPlan.objects.filter(status=obj).exists()
            or OccurrenceRecord.objects.filter(status=obj).exists()
            or Reporting.objects.filter(status=obj).exists()
            or Contract.objects.filter(status=obj).exists()
        ):
            return Response(
                data=[
                    {
                        "detail": "Não é possível deletar o status porque ele está sendo utilizado no sistema.",
                        "source": {"pointer": "/data"},
                        "status": status.HTTP_400_BAD_REQUEST,
                    }
                ],
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().destroy(request, pk)


class ServiceOrderActionStatusSpecsView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = ServiceOrderActionStatusSpecsSerializer
    permission_classes = [
        IsAuthenticated,
        ServiceOrderActionStatusSpecsPermissions,
    ]
    filterset_class = ServiceOrderActionStatusSpecsFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None
        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ServiceOrderActionStatusSpecs.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ServiceOrderActionStatusSpecs",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(
                    queryset, ServiceOrderActionStatusSpecs.objects.none()
                )
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ServiceOrderActionStatusSpecs.objects.filter(
                        company_id=user_company
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ServiceOrderActionStatusSpecs.objects.filter(
                        company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ServiceOrderActionStatusSpecs.objects.filter(
                company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


def get_service_order_queryset(
    action, request=None, permissions=None, user_company=None, user=None
):
    queryset = None
    user = request.user if request else user

    # On list action: limit queryset
    if action == "list":
        if request:
            if "company" not in request.query_params:
                return ServiceOrder.objects.none()

            user_company = uuid.UUID(request.query_params["company"])
        elif not user_company or not user:
            raise ValueError(
                "Both user_company and user are required arguments when not providing a request"
            )

        if not permissions:
            permissions = PermissionManager(
                user=user,
                company_ids=user_company,
                model="ServiceOrder",
            )

        allowed_queryset = permissions.get_allowed_queryset()

        if "none" in allowed_queryset:
            queryset = join_queryset(queryset, ServiceOrder.objects.none())
        if "firm" in allowed_queryset:
            user_firms = user.user_firms.all()
            procedures = Procedure.objects.filter(
                Q(created_by__user_firms__in=user_firms)
                | Q(responsible__user_firms__in=user_firms)
                | Q(action__service_order__responsibles=user)
                | Q(action__service_order__managers=user)
            )
            actions = ServiceOrderAction.objects.filter(
                Q(created_by=user) | Q(procedures__in=procedures)
            )
            queryset = join_queryset(
                queryset,
                ServiceOrder.objects.filter(
                    Q(created_by=user)
                    | Q(actions__in=actions)
                    | Q(responsibles=user)
                    | Q(managers=user)
                ),
            )
        if "self" in allowed_queryset:
            actions = ServiceOrderAction.objects.filter(
                Q(created_by=user)
                | Q(procedures__created_by=user)
                | Q(procedures__responsible=user)
            )
            queryset = join_queryset(
                queryset,
                ServiceOrder.objects.filter(
                    Q(created_by=user)
                    | Q(actions__in=actions)
                    | Q(responsibles=user)
                    | Q(managers=user)
                ),
            )
        if "all" in allowed_queryset:
            queryset = join_queryset(
                queryset, ServiceOrder.objects.filter(company=user_company)
            )

    # If queryset isn't set by any means above
    if queryset is None:
        user_companies = user.companies.all()
        queryset = ServiceOrder.objects.filter(company__in=user_companies)

    return queryset


class ServiceOrderView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ServiceOrderPermissions]
    filterset_class = ServiceOrderFilter
    permissions = None

    ordering_fields = [
        "uuid",
        "number",
        "created_by__first_name",
        "closed_by__first_name",
        "opened_at",
        "updated_at",
        "closed_at",
        "is_closed",
        "closed_description",
        "priority",
        "description",
        "so_records__number",
        "status__name",
    ]
    ordering = "uuid"

    def get_serializer_class(self):
        if self.permissions and self.permissions.has_permission("can_view_money"):
            return ServiceOrderSerializer
        return ServiceOrderWithoutMoneySerializer

    def get_serializer_context(self):
        context = super(ServiceOrderView, self).get_serializer_context()
        user = context["request"].user

        # The current user is not anonymous and the action is list or retrieve
        if not user.is_anonymous and self.action in ["list", "retrieve"]:
            try:
                if context["view"].permissions:
                    context.update(
                        {
                            "user_entity": list(
                                user.user_firms.filter(
                                    company_id=context["view"].permissions.company_id
                                ).values_list("entity__uuid", flat=True)
                            )
                        }
                    )
            except AttributeError as err:
                # Send the exception to Sentry
                sentry_sdk.capture_exception(err)
        return context

    def get_queryset(self):
        queryset = get_service_order_queryset(
            self.action, self.request, self.permissions
        )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(methods=["get"], url_path="PDF", detail=True)
    def pdf_service_order(self, request, pk=None):
        obj = self.get_object()
        endpoint = PDFEndpoint(obj, pk, request, "ServiceOrder")
        return endpoint.get_response()

    @action(methods=["get"], url_path="PendingProcedures", detail=False)
    def pending_procedures(self, request, pk=None):
        results = extract_pending_procedures(
            request,
            self.permissions,
            self.request.query_params,
            self.request.user,
        )

        results = dict_to_casing(results)

        return Response({"type": "PendingProcedures", "attributes": results})


class ServiceOrderWatcherView(viewsets.ModelViewSet):
    serializer_class = ServiceOrderWatcherSerializer
    filterset_class = ServiceOrderWatcherFilter
    permissions = None
    ordering = "uuid"

    def get_permissions(self):
        if self.action == "change_status_email":
            self.permission_classes = []
        else:
            self.permission_classes = [
                IsAuthenticated,
                ServiceOrderWatcherPermissions,
            ]

        return super(ServiceOrderWatcherView, self).get_permissions()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def get_queryset(self):
        queryset = None
        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ServiceOrderWatcher.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ServiceOrderWatcher",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ServiceOrderWatcher.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ServiceOrderWatcher.objects.filter(
                        Q(user=self.request.user)
                        | Q(created_by=self.request.user)
                        | Q(updated_by=self.request.user)
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ServiceOrderWatcher.objects.filter(
                        service_order__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            if self.request.user.is_anonymous:
                obj_uuid = self.request.path.split("/")[2]
                queryset = ServiceOrderWatcher.objects.filter(uuid=obj_uuid)
            else:
                user_companies = self.request.user.companies.all()
                queryset = ServiceOrderWatcher.objects.filter(
                    service_order__company__in=user_companies
                )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["GET"], url_path="Status", detail=True)
    def change_status_email(self, request, pk=None):
        watcher = self.get_object()
        watcher.status_email = False
        watcher.save()

        html = "service_orders/email/watcher_unsubscribed.html"

        return render(request, html)


def get_service_order_action_queryset(action, request, permissions):
    queryset = None

    # On list action: limit queryset
    if action == "list":
        if "company" not in request.query_params:
            return ServiceOrderAction.objects.none()

        user_company = uuid.UUID(request.query_params["company"])

        if not permissions:
            permissions = PermissionManager(
                user=request.user,
                company_ids=user_company,
                model="ServiceOrderAction",
            )

        allowed_queryset = permissions.get_allowed_queryset()

        if "none" in allowed_queryset:
            queryset = join_queryset(queryset, ServiceOrderAction.objects.none())
        if "self" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                ServiceOrderAction.objects.filter(
                    Q(created_by=request.user)
                    | Q(procedures__created_by=request.user)
                    | Q(procedures__responsible=request.user)
                    | Q(service_order__responsibles=request.user)
                    | Q(service_order__managers=request.user)
                ),
            )
        if "all" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                ServiceOrderAction.objects.filter(
                    service_order__company_id=user_company
                ),
            )

    # If queryset isn't set by any means above
    if queryset is None:
        user_companies = request.user.companies.all()
        queryset = ServiceOrderAction.objects.filter(
            service_order__company__in=user_companies
        )

    return queryset


class ServiceOrderActionView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ServiceOrderActionPermissions]
    filterset_class = ServiceOrderActionFilter
    permissions = None
    ordering = "uuid"

    def get_serializer_class(self):
        if self.action == "create":
            return ServiceOrderActionCreateSerializer
        return ServiceOrderActionSerializer

    def get_serializer_context(self):
        context = super(ServiceOrderActionView, self).get_serializer_context()
        user = context["request"].user

        # The current user is not anonymous and the action is list or retrieve
        if not user.is_anonymous and self.action in ["list", "retrieve"]:
            try:
                if context["view"].permissions:
                    context.update(
                        {
                            "user_entity": list(
                                user.user_firms.filter(
                                    company_id=context["view"].permissions.company_id
                                ).values_list("entity__uuid", flat=True)
                            )
                        }
                    )
            except AttributeError as err:
                # Send the exception to Sentry
                sentry_sdk.capture_exception(err)
        return context

    def get_queryset(self):
        queryset = get_service_order_action_queryset(
            self.action, self.request, self.permissions
        )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(methods=["get"], url_path="PDF", detail=True)
    def pdf_service_order_action(self, request, pk=None):
        obj = self.get_object()
        endpoint = PDFEndpoint(obj, pk, request, "ServiceOrderAction")
        return endpoint.get_response()

    @action(methods=["get"], url_path="CheckEmailJudiciary", detail=True)
    def service_order_check_data_email_judiciary(self, request, pk):
        obj = self.get_object()
        context = build_data_check_email_judiciary(obj, request)

        data = {"data": keys_to_camel_case(context)}

        return JsonResponse(data)


def get_procedure_queryset(action, request, permissions):
    queryset = None

    # On list action: limit queryset
    if action == "list":
        if "company" not in request.query_params:
            return Procedure.objects.none()

        user_company = uuid.UUID(request.query_params["company"])

        if not permissions:
            permissions = PermissionManager(
                user=request.user, company_ids=user_company, model="Procedure"
            )

        allowed_queryset = permissions.get_allowed_queryset()

        if "none" in allowed_queryset:
            queryset = join_queryset(queryset, Procedure.objects.none())
        if "self" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                Procedure.objects.filter(
                    Q(created_by=request.user)
                    | Q(responsible=request.user)
                    | Q(action__service_order__responsibles=request.user)
                    | Q(action__service_order__managers=request.user)
                ),
            )
        if "firm" in allowed_queryset:
            user_firms = request.user.user_firms.all()
            queryset = join_queryset(
                queryset,
                Procedure.objects.filter(
                    Q(created_by__user_firms__in=user_firms)
                    | Q(responsible__user_firms__in=user_firms)
                    | Q(action__service_order__responsibles=request.user)
                    | Q(action__service_order__managers=request.user)
                ),
            )
        if "all" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                Procedure.objects.filter(action__service_order__company=user_company),
            )

    # If queryset isn't set by any means above
    if queryset is None:
        user_companies = request.user.companies.all()
        queryset = Procedure.objects.filter(
            action__service_order__company__in=user_companies
        )

    return queryset


class ProcedureView(viewsets.ModelViewSet):
    serializer_class = ProcedureSerializer
    permission_classes = [
        IsAuthenticated,
        ProcedurePermissions,
        ProcedureFlowPermissions,
    ]
    filterset_class = ProcedureFilter
    permissions = None
    ordering = "uuid"
    skip_eager_loading_on = ["send_judiciary_email"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = get_procedure_queryset(self.action, self.request, self.permissions)

        if self.action in self.skip_eager_loading_on:
            return queryset.distinct()

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="SendJudiciaryEmail", detail=True)
    def send_judiciary_email(self, request, pk=None):
        obj = self.get_object()
        is_send_valid = False
        if obj.action:
            service_order = obj.action.service_order
            company = service_order.company

            # For the special judiciary forward email
            # judiciary_firms = Firm.objects.filter(company=company, is_judiciary=True)
            judiciary_users = company.get_judiciary_users()

            should_forward = (
                # Service Order Action need allow_forwarding
                obj.action.allow_forwarding
                # The Procedure is set to be forward
                and obj.forward_to_judiciary
                # And there are User instances to forward the email to
                and judiciary_users.exists()
            )

            # Only process the data if there's someone to receive the email
            if should_forward:
                process_judiciary_emails(str(obj.uuid), str(self.request.user.uuid))
                is_send_valid = True

        message = {
            "data": {
                "type": "Procedure",
                "path": "SendJudiciaryEmail",
                "email_send": is_send_valid,
                "message": f"send {'successfully' if is_send_valid else 'failed'}",
            }
        }
        return JsonResponse(message, status=200 if is_send_valid else 400)


class ProcedureFileView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ProcedureFilePermissions]
    filterset_class = ProcedureFileFilter
    permissions = None
    ordering = "uuid"

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update", "create"]:
            return ProcedureFileObjectSerializer
        return ProcedureFileSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ProcedureFile.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ProcedureFile",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ProcedureFile.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ProcedureFile.objects.filter(
                        Q(created_by=self.request.user)
                        | Q(procedures__created_by=self.request.user)
                        | Q(procedures__responsible=self.request.user)
                        | Q(
                            procedures__action__service_order__responsibles=self.request.user
                        )
                        | Q(
                            procedures__action__service_order__managers=self.request.user
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ProcedureFile.objects.filter(
                        procedures__action__service_order__company=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ProcedureFile.objects.filter(
                procedures__action__service_order__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="Check", detail=True)
    def check(self, request, pk=None):
        return check_endpoint(self.get_object())


def get_procedure_resource_queryset(action, request, permissions):
    queryset = None

    # On list action: limit queryset
    if action == "list":
        if "company" not in request.query_params:
            return ProcedureResource.objects.none()

        user_company = uuid.UUID(request.query_params["company"])

        if not permissions:
            permissions = PermissionManager(
                user=request.user,
                company_ids=user_company,
                model="ProcedureResource",
            )

        allowed_queryset = permissions.get_allowed_queryset()

        if "none" in allowed_queryset:
            queryset = join_queryset(queryset, ProcedureResource.objects.none())
        if "self" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                ProcedureResource.objects.filter(created_by=request.user),
            )
        if "firm" in allowed_queryset:
            user_firms = request.user.user_firms.all()
            queryset = join_queryset(
                queryset,
                ProcedureResource.objects.filter(
                    Q(created_by=request.user)
                    | Q(created_by__user_firms__in=user_firms)
                ),
            )
        if "all" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                ProcedureResource.objects.filter(
                    service_order_resource__resource__company=user_company
                ),
            )

    # If queryset isn't set by any means above
    if queryset is None:
        user_companies = request.user.companies.all()
        queryset = ProcedureResource.objects.filter(
            service_order_resource__resource__company__in=user_companies
        )

    return queryset


class ProcedureResourceView(viewsets.ModelViewSet):
    serializer_class = ProcedureResourceSerializer
    permission_classes = [IsAuthenticated, ProcedureResourcePermissions]
    filterset_class = ProcedureResourceFilter
    permissions = None
    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "amount",
        "resource__name",
        "resource__unit",
        "service_order_resource__entity__name",
        "creation_date",
        "created_by__first_name",
    ]

    def get_serializer_class(self):
        if self.permissions and self.permissions.has_permission("can_view_money"):
            return ProcedureResourceSerializer
        return ProcedureResourceWithoutMoneySerializer

    def perform_create(self, serializer):
        if serializer.is_valid(raise_exception=True):
            serializer.save(created_by=self.request.user)

    def get_queryset(self, skip_eager_loading=False):
        queryset = get_procedure_resource_queryset(
            self.action, self.request, self.permissions
        )
        if skip_eager_loading:
            return queryset.filter(
                Q(service_order_resource__contract__firm__is_company_team=False)
                | Q(
                    service_order_resource__contract__subcompany__subcompany_type="HIRED"
                )
            )

        return self.get_serializer_class().setup_eager_loading(
            queryset.filter(
                Q(service_order_resource__contract__firm__is_company_team=False)
                | Q(
                    service_order_resource__contract__subcompany__subcompany_type="HIRED"
                )
            ).distinct()
        )

    @action(methods=["post"], url_path="Approval", detail=True)
    def approval(self, request, pk=None):
        resource = self.get_object()

        if "approve" in request.data.keys():
            if resource.measurement_bulletin:
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

            resource.approval_date = datetime.now()
            resource.approved_by = request.user

            if request.data.get("approve", False):
                resource.approval_status = resource_approval_status.APPROVED_APPROVAL
            else:
                resource.approval_status = resource_approval_status.DENIED_APPROVAL

            resource.save()

            return Response({"data": {"status": "OK"}})

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

    @action(methods=["post"], url_path="BulkApproval", detail=False)
    def bulk_approval(self, request, pk=None):
        resource_ids_list = [
            resource["id"] for resource in request.data["procedure_resources"]
        ]
        resources = ProcedureResource.objects.filter(pk__in=resource_ids_list)

        if "approve" in request.data.keys():
            approval_flag = request.data.get("approve", False)
            if resources.filter(measurement_bulletin__isnull=False).exists():
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

            for resource in resources:
                resource.approval_date = datetime.now()
                resource.approved_by = request.user

                resource.approval_status = (
                    resource_approval_status.APPROVED_APPROVAL
                    if approval_flag
                    else resource_approval_status.DENIED_APPROVAL
                )
                # call save because ProcedureResource has signals to be called
                resource.save()

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

    @action(methods=["GET"], url_path="Export", detail=False)
    def procedure_resource_export(self, request, pk=None):
        # Filter queryset and generate uuid_list
        queryset = self.filter_queryset(self.get_queryset(skip_eager_loading=True))
        uuid_list = [str(item.uuid) for item in queryset]
        if len(uuid_list) > 50000:
            raise serializers.ValidationError(
                "Você está tentando gerar uma exportação com mais de 50.000 itens. Por favor, aplique filtros."
            )
        try:
            company_name = Company.objects.get(pk=request.query_params["company"]).name
        except Exception:
            return error_message(
                400,
                'Parâmetro "Unidade" é obrigatório',
            )
        procedure_resource_object = ProcedureResourceExport(
            queryset=queryset[0], company_name=company_name
        )

        # Create and upload uuid list to prevent errors if there are too many items
        file_uuid = uuid.uuid4()
        generic_file = GenericFile.objects.create(pk=file_uuid)
        temp_path = "/tmp/procedure_resource_uuid/"
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

        # Generate URL and trigger async process
        filename = procedure_resource_object.filename
        object_name = procedure_resource_object.object_name
        url = procedure_resource_object.get_s3_url()
        procedure_resource_export_async(
            str(file_uuid), filename, object_name, company_name
        )

        return Response(
            {
                "type": "Export",
                "attributes": {"url": url, "name": filename},
            }
        )


def get_service_order_resource_queryset(action, request, permissions):
    queryset = None

    # On list action: limit queryset
    if action == "list":
        if "company" not in request.query_params:
            return ServiceOrderResource.objects.none()

        user_company = uuid.UUID(request.query_params["company"])

        if not permissions:
            permissions = PermissionManager(
                user=request.user,
                company_ids=user_company,
                model="ServiceOrderResource",
            )

        allowed_queryset = permissions.get_allowed_queryset()

        if "none" in allowed_queryset:
            queryset = join_queryset(queryset, ServiceOrderResource.objects.none())
        if "self" in allowed_queryset or "firm" in allowed_queryset:
            request_user = request.user
            user_firms = Firm.objects.filter(users__in=[request_user])

            contracts = Contract.objects.filter(
                Q(service_orders__actions__created_by=request.user)
                | Q(service_orders__actions__procedures__created_by=request.user)
                | Q(service_orders__actions__procedures__responsible=request.user)
                | Q(service_orders__responsibles=request.user)
                | Q(service_orders__managers=request.user)
                | Q(responsibles_hirer=request.user)
                | Q(responsibles_hired=request.user)
            )
            queryset = join_queryset(
                queryset,
                ServiceOrderResource.objects.filter(
                    (
                        Q(contract__firm__users=request_user)
                        | Q(contract__subcompany__subcompany_firms__in=user_firms)
                    )
                    & (Q(created_by=request.user) | Q(contract__in=contracts))
                ),
            )
            if "firm" in allowed_queryset:
                queryset.union(
                    ServiceOrderResource.objects.filter(
                        Q(contract__unit_price_services__firms__in=user_firms)
                        | Q(contract__administration_services__firms__in=user_firms)
                        | Q(contract__performance_services__firms__in=user_firms)
                    ),
                    all=True,
                )

        if "all" in allowed_queryset:
            queryset = join_queryset(
                queryset,
                ServiceOrderResource.objects.filter(
                    Q(contract__firm__company=user_company)
                    | Q(contract__subcompany__company=user_company)
                ),
            )
    # If queryset isn't set by any means above
    if queryset is None:
        user_companies = request.user.companies.all()
        queryset = ServiceOrderResource.objects.filter(
            Q(contract__firm__company__in=user_companies)
            | Q(contract__subcompany__company__in=user_companies)
        ).prefetch_related("serviceorderresource_procedures")

    return queryset


class ServiceOrderResourceView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ServiceOrderResourcePermissions]
    filterset_class = ServiceOrderResourceFilter
    permissions = None
    ordering = "uuid"

    ordering_fields = [
        "uuid",
        "amount",
        "unit_price",
        "used_price",
        "remaining_amount",
        "creation_date",
        "effective_date",
        "resource_kind",
        "additional_control",
        "resource__name",
        "resource__unit",
        "entity__name",
    ]

    def get_serializer_class(self):
        if self.permissions and self.permissions.has_permission("can_view_money"):
            if self.action in ["retrieve", "update", "partial_update"]:
                return ServiceOrderResourceObjectSerializer
            return ServiceOrderResourceSerializer
        return ServiceOrderResourceWithoutMoneySerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = get_service_order_resource_queryset(
            self.action, self.request, self.permissions
        )

        return self.get_serializer_class().setup_eager_loading(
            queryset.filter(
                Q(contract__firm__is_company_team=False)
                | Q(contract__subcompany__subcompany_type="HIRED")
            ).distinct()
        )


def get_measurement_bulletin_queryset(action, request, permissions):
    queryset = None

    # On list action: limit queryset
    if action == "list":
        if "company" not in request.query_params:
            return MeasurementBulletin.objects.none()

        user_company = uuid.UUID(request.query_params["company"])

        if not permissions:
            permissions = PermissionManager(
                user=request.user,
                company_ids=user_company,
                model="MeasurementBulletin",
            )

        allowed_queryset = permissions.get_allowed_queryset()

        if "none" in allowed_queryset:
            queryset = join_queryset(queryset, MeasurementBulletin.objects.none())
        if "self" in allowed_queryset:
            from apps.resources.views import get_contract_queryset

            contracts = get_contract_queryset("list", request, permissions)
            queryset = join_queryset(
                queryset,
                MeasurementBulletin.objects.filter(
                    Q(firm__in=request.user.user_firms.all())
                    | Q(contract__in=contracts)
                ),
            )
        if "all" in allowed_queryset:
            from apps.resources.views import get_contract_queryset

            contracts = get_contract_queryset("list", request, permissions)
            queryset = join_queryset(
                queryset,
                MeasurementBulletin.objects.filter(
                    Q(firm__company=user_company) | Q(contract__in=contracts)
                ),
            )

    # If queryset isn't set by any means above
    if queryset is None:
        user_companies = request.user.companies.all()
        queryset = MeasurementBulletin.objects.filter(
            Q(firm__company__in=user_companies)
            | Q(contract__firm__company__in=user_companies)
            | Q(contract__subcompany__company__in=user_companies)
        )

    return queryset


class MeasurementBulletinView(viewsets.ModelViewSet):
    serializer_class = MeasurementBulletinSerializer
    permission_classes = [IsAuthenticated, MeasurementBulletinPermissions]
    filterset_class = MeasurementBulletinFilter
    permissions = None
    resource_name = "MeasurementBulletin"
    ordering = "uuid"

    def get_serializer_class(self):
        action_obj = self.action in [
            "retrieve",
            "update",
            "partial_update",
            "create",
        ]

        if action_obj:
            return MeasurementBulletinObjectSerializer
        return MeasurementBulletinSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = get_measurement_bulletin_queryset(
            self.action, self.request, self.permissions
        )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def list(self, request, *args, **kwargs):
        with DisableSignals(disabled_signals=[pre_init, post_init]):
            return super().list(request, *args, **kwargs)

    @action(methods=["GET"], url_path="Preview", detail=False)
    def preview(self, request, pk=None):
        endpoint = MeasurementBulletinPreview(request)
        return endpoint.get_response()

    @action(methods=["get"], url_path="PDF", detail=True)
    def pdf_measurement_bulletin(self, request, pk=None):
        obj = self.get_object()
        endpoint = PDFEndpoint(obj, pk, request, "MeasurementBulletin")
        return endpoint.get_response()

    @action(methods=["get"], url_path="Summary", detail=True)
    def summary_measurement_bulletin(self, request, pk=None):
        obj = self.get_object()
        endpoint = BulletinSummaryEndpoint(obj)
        return endpoint.get_response()

    @action(methods=["post"], url_path="Approval", detail=True)
    def approval(self, request, pk=None):
        # Email functions
        functions = {"approved_measurement_bulletin": approved_measurement_bulletin}

        # Get all the ApprovalTransitions related to the current ApprovalStep
        bulletin = self.get_object()
        transitions = ApprovalTransition.objects.filter(origin=bulletin.approval_step)

        # Check if the condition from any ApprovalTransition was met
        # If the condition was met, execute the ApprovalStep change
        serializer = self.get_serializer_class()

        source = get_obj_serialized(bulletin, serializer, MeasurementBulletinView)

        data = {"request": request.data, "source": source}

        for transition in transitions:
            if apply_json_logic(transition.condition, data):
                bulletin.approval_step = transition.destination

                for key, callback in transition.callback.items():
                    if key == "change_fields":
                        for field in callback:
                            try:
                                value = get_nested_fields(field["value"], bulletin)
                                setattr(bulletin, field["name"], value)
                            except Exception as e:
                                print("Exception setting model fields", e)
                    if key == "send_notification":
                        for notification in callback:
                            if notification in functions:
                                notification_firms = transition.callback.get(
                                    "measurement_bulletin_notification_firms",
                                    [],
                                )
                                subject = transition.callback.get(
                                    "notification_subject", ""
                                )
                                description = transition.callback.get(
                                    "notification_description", ""
                                )

                                functions[notification](
                                    bulletin,
                                    notification_firms,
                                    subject,
                                    description,
                                )

                bulletin.save()

                if "to_do" in request.data:
                    to_do = request.data.get("to_do", "Boletim necessita de revisão.")

                    hist = bulletin.history.first()
                    hist.history_change_reason = to_do
                    hist.save()

                measurement_bulletin_approval_change(bulletin)
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


class AdministrativeInformationView(viewsets.ModelViewSet):
    serializer_class = AdministrativeInformationSerializer
    permission_classes = [IsAuthenticated, AdministrativeInformationPermissions]
    filterset_class = AdministrativeInformationFilter
    permissions = None
    ordering = "uuid"

    ordering_fields = [
        "uuid",
        "created_at",
        "created_by__first_name",
        "created_by__last_name",
        "responsible__first_name",
        "responsible__last_name",
        "service_order__number",
        "contract__extra_info__r_c_number",
        "spend_limit",
    ]

    def get_serializer_class(self):
        if self.permissions and self.permissions.has_permission("can_view_money"):
            return AdministrativeInformationSerializer
        return AdministrativeInformationWithoutMoneySerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return AdministrativeInformation.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="AdministrativeInformation",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(
                    queryset, AdministrativeInformation.objects.none()
                )
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    AdministrativeInformation.objects.filter(
                        Q(contract__firm__in=self.request.user.user_firms.all())
                        & (
                            Q(service_order__created_by=self.request.user)
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
                    ),
                )
            if "firm" in allowed_queryset:
                user_firms = self.request.user.user_firms.all()
                procedures = Procedure.objects.filter(
                    Q(created_by__user_firms__in=user_firms)
                    | Q(responsible__user_firms__in=user_firms)
                    | Q(action__service_order__responsibles=self.request.user)
                    | Q(action__service_order__managers=self.request.user)
                )
                actions = ServiceOrderAction.objects.filter(
                    Q(created_by=self.request.user) | Q(procedures__in=procedures)
                )
                service_orders = ServiceOrder.objects.filter(
                    Q(created_by=self.request.user)
                    | Q(actions__in=actions)
                    | Q(responsibles=self.request.user)
                    | Q(managers=self.request.user)
                )
                queryset = join_queryset(
                    queryset,
                    AdministrativeInformation.objects.filter(
                        Q(contract__firm__in=self.request.user.user_firms.all())
                        & Q(service_order__in=service_orders)
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    AdministrativeInformation.objects.filter(
                        service_order__company=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = AdministrativeInformation.objects.filter(
                service_order__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class AdditionalControlView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = AdditionalControlSerializer
    permission_classes = [IsAuthenticated, AdditionalControlPermissions]
    filterset_class = AdditionalControlFilter
    permissions = None
    ordering = "uuid"

    ordering_fields = [
        "uuid",
        "name",
        "created_at",
        "created_by",
        "company",
        "name",
        "is_active",
    ]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None
        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return AdditionalControl.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="AdditionalControl",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, AdditionalControl.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    AdditionalControl.objects.filter(company_id=user_company),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    AdditionalControl.objects.filter(company_id=user_company),
                )
        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            print(user_companies)
            queryset = AdditionalControl.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class PendingProceduresExportView(viewsets.ModelViewSet):
    serializer_class = PendingProceduresExportSerializer
    permission_classes = [IsAuthenticated, PendingProceduresExportPermissions]
    filterset_class = PendingProcedureExportFilter
    permissions = None
    ordering = "uuid"

    ordering_fields = [
        "uuid",
        "company",
        "created_at",
        "created_by",
        "error",
        "done",
    ]

    def get_queryset(self):
        queryset = None

        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return PendingProceduresExport.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="PendingProceduresExport",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(
                    queryset, PendingProceduresExport.objects.none()
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    PendingProceduresExport.objects.filter(company=user_company),
                )
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    PendingProceduresExport.objects.filter(
                        created_by=self.request.user
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = PendingProceduresExport.objects.filter(
                company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
