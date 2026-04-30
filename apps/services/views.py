import uuid

from arrow import Arrow
from django.db import IntegrityError
from django_filters import rest_framework as filters
from django_filters.filters import CharFilter
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from simple_history.utils import bulk_create_with_history

from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import Reporting
from helpers.apps.dnit_rdo import (
    get_executed_services,
    get_notes,
    get_occurrence_types,
    get_rain,
    get_restrictions,
    get_weather,
)
from helpers.apps.transports import TransportsEndpoint
from helpers.dates import date_tz
from helpers.error_messages import error_message
from helpers.filters import ListFilter, UUIDListFilter
from helpers.histories import bulk_update_with_history
from helpers.permissions import PermissionManager, join_queryset

from .models import (
    Goal,
    GoalAggregate,
    Measurement,
    MeasurementService,
    Service,
    ServiceSpecs,
    ServiceUsage,
)
from .permissions import (
    GoalAggregatePermissions,
    GoalPermissions,
    MeasurementPermissions,
    MeasurementServicePermissions,
    ServicePermissions,
    ServiceSpecsPermissions,
    ServiceUsagePermissions,
)
from .serializers import (
    GoalAggregateSerializer,
    GoalSerializer,
    MeasurementSerializer,
    MeasurementServiceSerializer,
    ServiceSerializer,
    ServiceSpecsSerializer,
    ServiceUsageSerializer,
)


class ServiceFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    group = ListFilter()
    kind = ListFilter()
    unit = ListFilter()
    code = ListFilter()
    occurrence_type = UUIDListFilter(field_name="occurrence_types", distinct=True)

    class Meta:
        model = Service
        fields = {"company": ["exact"]}


class ServiceView(viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated, ServicePermissions]
    filterset_class = ServiceFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return Service.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="Service",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, Service.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset, Service.objects.filter(company_id=user_company)
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, Service.objects.filter(company_id=user_company)
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = Service.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ServiceSpecsFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="service__company__uuid")

    class Meta:
        model = ServiceSpecs
        fields = {"occurrence_type": ["exact"], "service": ["exact"]}


class ServiceSpecsView(viewsets.ModelViewSet):
    serializer_class = ServiceSpecsSerializer
    permission_classes = [IsAuthenticated, ServiceSpecsPermissions]
    filterset_class = ServiceSpecsFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ServiceSpecs.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ServiceSpecs",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ServiceSpecs.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ServiceSpecs.objects.filter(service__company_id=user_company),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ServiceSpecs.objects.filter(service__company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ServiceSpecs.objects.filter(service__company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ServiceUsageFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    reporting_resource = CharFilter(
        method="get_reporting_resource", label="reporting_resource"
    )
    company = CharFilter(field_name="service__company__uuid")

    class Meta:
        model = ServiceUsage
        fields = {"service": ["exact"], "reporting": ["exact"]}

    def get_reporting_resource(self, queryset, name, value):
        try:
            reporting_id = uuid.UUID(value)
        except Exception:
            raise ValidationError("UUID inválido")

        reporting = Reporting.objects.get(pk=reporting_id)
        services = ServiceSpecs.objects.filter(
            occurrence_type=reporting.occurrence_type
        ).values_list("service_id", flat=True)

        usages = queryset.filter(reporting=reporting).exclude(service_id__in=services)

        return usages


class ServiceUsageView(viewsets.ModelViewSet):
    serializer_class = ServiceUsageSerializer
    permission_classes = [IsAuthenticated, ServiceUsagePermissions]
    filterset_class = ServiceUsageFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ServiceUsage.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ServiceUsage",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ServiceUsage.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ServiceUsage.objects.filter(service__company_id=user_company),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ServiceUsage.objects.filter(service__company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ServiceUsage.objects.filter(service__company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class MeasurementFilter(filters.FilterSet):
    uuid = UUIDListFilter()

    class Meta:
        model = Measurement
        fields = {"company": ["exact"], "number": ["exact"]}


class MeasurementView(viewsets.ModelViewSet):
    serializer_class = MeasurementSerializer
    permission_classes = [IsAuthenticated, MeasurementPermissions]
    filterset_class = MeasurementFilter
    permissions = None
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return Measurement.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="Measurement",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, Measurement.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    Measurement.objects.filter(created_by=self.request.user),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    Measurement.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = Measurement.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="Summary", detail=True)
    def summary(self, request, pk=None):
        measurement = self.get_object()
        previous_measurement = measurement.previous_measurement

        measurement_services = measurement.measurement_services.all()
        try:
            previous_services = previous_measurement.measurement_services.all()
        except AttributeError:
            return Response(
                {
                    "type": "Summary",
                    "id": pk,
                    "attributes": {"uuid": pk, "usages": []},
                }
            )

        services = []

        administration_service = None

        for current in measurement_services:
            previous = next(
                a for a in previous_services if a.service.uuid == current.service.uuid
            )

            if "is_administration" in current.service.metadata:
                administration_service = current
                continue

            services.append(
                {
                    "name": current.service.name,
                    "code": current.service.code,
                    "kind": current.service.kind,
                    "unit": current.service.unit,
                    "unit_price": current.unit_price,
                    "adjustment_coefficient": current.adjustment_coefficient,
                    "amount": previous.balance - current.balance,
                    "start_balance": previous.balance,
                    "end_balance": current.balance,
                    "total_amount": current.service.total_amount,
                }
            )

        if administration_service:
            try:
                total_price = 0
                executed_price_previous = 0
                executed_price = 0
                for service in services:
                    total_price += service["total_amount"] * service["unit_price"]
                    executed_price_previous += (
                        service["start_balance"] * service["unit_price"]
                    )
                    executed_price += service["amount"] * service["unit_price"]

                amount = (executed_price / total_price) * 100
                start_balance = 100 - ((executed_price_previous / total_price) * 100)
            except Exception as e:
                print(str(e))
                amount = 0
                start_balance = 0

            services.append(
                {
                    "name": administration_service.service.name,
                    "code": administration_service.service.code,
                    "kind": administration_service.service.kind,
                    "unit": administration_service.service.unit,
                    "unit_price": administration_service.unit_price,
                    "adjustment_coefficient": administration_service.adjustment_coefficient,
                    "amount": amount,
                    "start_balance": start_balance,
                    "end_balance": start_balance - amount,
                    "total_amount": administration_service.service.total_amount,
                }
            )

        return Response(
            {
                "type": "Summary",
                "id": pk,
                "attributes": {"uuid": pk, "usages": services},
            }
        )

    @action(methods=["get"], url_path="Transports", detail=True)
    def transports(self, request, pk=None):
        measurement = self.get_object()
        transports_endpoint = TransportsEndpoint(measurement, pk)
        return transports_endpoint.get_response()

    @action(methods=["get"], url_path="RDO", detail=True)
    def dnit_rdo(self, request, pk=None):
        measurement = self.get_object()

        days = Arrow.range("day", measurement.start_date, measurement.end_date)

        try:
            daily_kind = measurement.company.metadata["daily_occurrence_kind"]
        except Exception:
            daily_kind = "5"

        daily_reportings = Reporting.objects.filter(
            company=measurement.company,
            occurrence_type__occurrence_kind=daily_kind,
            found_at__gte=measurement.start_date,
            found_at__lte=measurement.end_date,
        ).select_related("occurrence_type")

        daily_type = OccurrenceType.objects.filter(
            company__in=[measurement.company], occurrence_kind=daily_kind
        ).first()

        executed_reportings = (
            Reporting.objects.filter(
                reporting_usage__in=measurement.measurement_usage.all(),
                executed_at__isnull=False,
            )
            .distinct()
            .select_related("occurrence_type", "company")
        )

        daily_report = []
        for day in days:
            try:
                daily_reporting = next(
                    a for a in daily_reportings if a.found_at.day == day.day
                )
            except Exception:
                daily_reporting = None

            daily_report.append(
                {
                    "day": day.isoformat(),
                    "weather": get_weather(daily_reporting, daily_type),
                    "executedServices": get_executed_services(
                        daily_reporting, daily_type
                    ),
                    "restrictions": get_restrictions(daily_reporting, daily_type),
                    "notes": get_notes(daily_reporting, executed_reportings, day),
                    "occurrence_types": get_occurrence_types(
                        daily_reporting, executed_reportings, day
                    ),
                    "rain": get_rain(daily_reporting),
                }
            )

        return Response(
            {
                "type": "RDO",
                "id": pk,
                "attributes": {
                    "start_date": measurement.start_date,
                    "end_date": measurement.end_date,
                    "daily_report": daily_report,
                },
            }
        )

    @action(methods=["post"], url_path="UpdateServices", detail=True)
    def update_services(self, request, pk=None):
        measurement = self.get_object()
        measurement_services = measurement.measurement_services.all().select_related(
            "service"
        )
        services = Service.objects.filter(company=measurement.company)

        bulk_measurement_service_list = []

        error_ids = []
        for service in measurement_services:
            try:
                new_service = next(
                    a for a in services if a.uuid == service.service.uuid
                )
            except StopIteration:
                error_ids.append(service.uuid)
                continue
            # Refresh unit_price and adjustment_coefficient from Service
            service.unit_price = new_service.unit_price
            service.adjustment_coefficient = new_service.adjustment_coefficient
            bulk_measurement_service_list.append(service)

        bulk_update_with_history(
            bulk_measurement_service_list,
            MeasurementService,
            user=request.user,
            use_django_bulk=True,
        )

        return Response(
            {
                "type": "UpdateServices",
                "id": pk,
                "attributes": {"errors": error_ids},
            }
        )


class MeasurementServiceFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="service__company__uuid")

    class Meta:
        model = MeasurementService
        fields = {"service": ["exact"], "measurement": ["exact"]}


class MeasurementServiceView(viewsets.ReadOnlyModelViewSet):
    serializer_class = MeasurementServiceSerializer
    permission_classes = [IsAuthenticated, MeasurementServicePermissions]
    filterset_class = MeasurementServiceFilter
    permissions = None
    ordering = "uuid"

    ordering_fields = [
        "uuid",
        "unit_price",
        "balance",
        "adjustment_coefficient",
        "service__name",
        "service__kind",
    ]

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return MeasurementService.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MeasurementService",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, MeasurementService.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MeasurementService.objects.filter(service__company_id=user_company),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MeasurementService.objects.filter(service__company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MeasurementService.objects.filter(
                service__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class GoalFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    date = CharFilter(method="get_date", label="date")

    class Meta:
        model = Goal
        fields = {"occurrence_type": ["exact"]}

    def get_date(self, queryset, name, value):
        value = date_tz(value)

        qs = GoalAggregate.objects.filter(
            company_id=self.request.query_params["company"]
        ).filter(start_date__lte=value, end_date__gte=value)

        return queryset.filter(aggregate__in=qs)


class GoalView(viewsets.ModelViewSet):
    serializer_class = GoalSerializer
    permission_classes = [IsAuthenticated, GoalPermissions]
    filterset_class = GoalFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return Goal.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="Goal",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, Goal.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    Goal.objects.filter(aggregate__company_id=user_company),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    Goal.objects.filter(aggregate__company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = Goal.objects.filter(aggregate__company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["post"], url_path="bulk_create", detail=False)
    def bulk_create(self, request, pk=None):
        goals_names = ["occurrence_type", "amount", "service"]

        bulk_create_list = []

        for item in request.data["goals"]:
            if set(goals_names).issubset(item):
                continue
            else:
                raise ValidationError(
                    "É necessário enviar amount, service and occurrence_type"
                )

        for item in request.data["goals"]:
            bulk_create_list.append(
                Goal(
                    aggregate_id=request.data["aggregate"]["id"],
                    occurrence_type_id=item.get("occurrence_type"),
                    service_id=item.get("service"),
                    amount=item.get("amount"),
                )
            )

        try:
            bulk_create_with_history(bulk_create_list, Goal)
        except IntegrityError:
            raise ValidationError("Já existe uma meta para essa classe neste período")

        return error_message(201, "OK")


class GoalAggregateFilter(filters.FilterSet):
    uuid = UUIDListFilter()

    class Meta:
        model = GoalAggregate
        fields = {"company": ["exact"]}


class GoalAggregateView(viewsets.ModelViewSet):
    serializer_class = GoalAggregateSerializer
    permission_classes = [IsAuthenticated, GoalAggregatePermissions]
    filterset_class = GoalAggregateFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return GoalAggregate.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="GoalAggregate",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, GoalAggregate.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    GoalAggregate.objects.filter(company_id=user_company),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    GoalAggregate.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = GoalAggregate.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())
