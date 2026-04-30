import uuid
from datetime import datetime, timedelta

from arrow import get as arrow_get
from arrow.arrow import Arrow
from django.db.models import Q, TextField, Value
from django.db.models.functions import Concat
from django.utils import timezone
from django_filters import rest_framework as filters
from django_filters.filters import BooleanFilter, CharFilter, DateTimeFromToRangeFilter
from fnc.mappings import get
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_json_api import serializers

from apps.companies.models import Company, Firm
from apps.monitorings.models import (
    MaterialItem,
    MaterialUsage,
    MonitoringCampaign,
    MonitoringCollect,
    MonitoringCycle,
    MonitoringFrequency,
    MonitoringPlan,
    MonitoringPoint,
    MonitoringRecord,
    OperationalControl,
    OperationalCycle,
)
from apps.monitorings.permissions import (
    MaterialItemPermissions,
    MaterialUsagePermissions,
    MonitoringCampaignPermissions,
    MonitoringCollectPermissions,
    MonitoringCyclePermissions,
    MonitoringFrequencyPermissions,
    MonitoringPlanPermissions,
    MonitoringPointPermissions,
    MonitoringRecordPermissions,
    OperationalControlPermissions,
    OperationalCyclePermissions,
)
from apps.monitorings.serializers import (
    MaterialItemSerializer,
    MaterialUsageSerializer,
    MonitoringCampaignSerializer,
    MonitoringCollectSerializer,
    MonitoringCycleSerializer,
    MonitoringFrequencySerializer,
    MonitoringPlanSerializer,
    MonitoringPointGeoSerializer,
    MonitoringPointSerializer,
    MonitoringRecordSerializer,
    OperationalControlSerializer,
    OperationalCycleSerializer,
)
from apps.service_orders.models import ServiceOrderAction
from helpers.dates import date_tz, get_dates_by_frequency
from helpers.error_messages import error_message
from helpers.filters import (
    DateFromToRangeCustomFilter,
    DateTzFilter,
    KeyFilter,
    ListFilter,
    UUIDListFilter,
)
from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset
from helpers.strings import to_snake_case


class MonitoringPlanFilter(filters.FilterSet):
    uuid = UUIDListFilter()

    class Meta:
        model = MonitoringPlan
        fields = ["company"]


class MonitoringPlanView(viewsets.ModelViewSet):
    serializer_class = MonitoringPlanSerializer
    permission_classes = [IsAuthenticated, MonitoringPlanPermissions]
    filterset_class = MonitoringPlanFilter
    permissions = None
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        if self.action in ["list", "retrieve"]:
            if "company" not in self.request.query_params:
                return MonitoringPlan.objects.none()

            is_record_creation = (
                True if "record_create" in self.request.query_params else False
            )

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MonitoringPlan",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if is_record_creation:
                all_permission = self.permissions.all_permissions
                can_create_monitoring = any(
                    get(
                        "occurrence_record.can_create_monitoring",
                        all_permission,
                        default=[],
                    )
                )
                if can_create_monitoring:
                    allowed_queryset = ["all"]

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, MonitoringPlan.objects.none())
            if "self" in allowed_queryset:
                now = timezone.now()
                user_firms = self.request.user.user_firms.all()
                if is_record_creation:
                    queryset = join_queryset(
                        queryset,
                        MonitoringPlan.objects.filter(
                            Q(company_id=user_company)
                            & Q(cycles_plan__start_date__date__lte=now.date())
                            & Q(cycles_plan__end_date__date__gte=now.date())
                            & Q(cycles_plan__executers__in=user_firms)
                        ),
                    )
                else:
                    queryset = join_queryset(
                        queryset,
                        MonitoringPlan.objects.filter(
                            Q(company_id=user_company)
                            & Q(cycles_plan__start_date__date__lte=now.date())
                            & Q(cycles_plan__end_date__date__gte=now.date())
                            & (
                                Q(cycles_plan__executers__in=user_firms)
                                | Q(cycles_plan__viewers__in=user_firms)
                                | Q(cycles_plan__evaluators__in=user_firms)
                                | Q(cycles_plan__approvers__in=user_firms)
                                | Q(cycles_plan__responsibles=self.request.user)
                            )
                        ),
                    )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MonitoringPlan.objects.filter(company_id=user_company),
                )

            if is_record_creation:
                queryset = queryset.filter(
                    status__is_final=True, monitoring_points__isnull=False
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MonitoringPlan.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class MonitoringCycleFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="monitoring_plan__company")
    monitoring_plan = UUIDListFilter()
    service_orders = UUIDListFilter()

    class Meta:
        model = MonitoringCycle
        fields = ["company"]


class MonitoringCycleView(viewsets.ModelViewSet):
    serializer_class = MonitoringCycleSerializer
    permission_classes = [IsAuthenticated, MonitoringCyclePermissions]
    filterset_class = MonitoringCycleFilter
    permissions = None
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return MonitoringCycle.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MonitoringCycle",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, MonitoringCycle.objects.none())
            if "self" in allowed_queryset:
                user_firms = list(
                    (self.request.user.user_firms.all()).union(
                        self.request.user.user_firms_manager.all()
                    )
                )
                queryset = join_queryset(
                    queryset,
                    MonitoringCycle.objects.filter(
                        Q(monitoring_plan__company_id=user_company)
                        & (
                            Q(created_by=self.request.user)
                            | Q(executers__in=user_firms)
                            | Q(viewers__in=user_firms)
                            | Q(evaluators__in=user_firms)
                            | Q(approvers__in=user_firms)
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MonitoringCycle.objects.filter(
                        monitoring_plan__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MonitoringCycle.objects.filter(
                monitoring_plan__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class MonitoringFrequencyFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="monitoring_plan__company")
    monitoring_plan = UUIDListFilter()
    monitoring_points = UUIDListFilter()
    active = BooleanFilter()

    class Meta:
        model = MonitoringFrequency
        fields = ["company"]


class MonitoringFrequencyView(viewsets.ModelViewSet):
    serializer_class = MonitoringFrequencySerializer
    permission_classes = [IsAuthenticated, MonitoringFrequencyPermissions]
    filterset_class = MonitoringFrequencyFilter
    permissions = None
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return MonitoringFrequency.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MonitoringFrequency",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, MonitoringFrequency.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MonitoringFrequency.objects.filter(
                        monitoring_plan__company_id=user_company
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MonitoringFrequency.objects.filter(
                        monitoring_plan__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MonitoringFrequency.objects.filter(
                monitoring_plan__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class MonitoringPointFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    monitoring_plan = UUIDListFilter()
    company = UUIDListFilter(field_name="monitoring_plan__company")
    active = BooleanFilter()

    class Meta:
        model = MonitoringPoint
        fields = ["company"]


class MonitoringPointView(viewsets.ModelViewSet):
    serializer_class = MonitoringPointSerializer
    permission_classes = [IsAuthenticated, MonitoringPointPermissions]
    filterset_class = MonitoringPointFilter
    permissions = None

    ordering_fields = [
        "uuid",
        "river__name",
        "active",
        "code",
        "uf_code",
        "city__name",
        "location__name",
        "place_on_dam",
        "segment",
        "description",
        "depth",
        "position",
        "stratification",
        "zone",
        "created_by__first_name",
        "created_at",
        "updated_at",
    ]
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return MonitoringPoint.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MonitoringPoint",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, MonitoringPoint.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MonitoringPoint.objects.filter(
                        monitoring_plan__company_id=user_company
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MonitoringPoint.objects.filter(
                        monitoring_plan__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MonitoringPoint.objects.filter(
                monitoring_plan__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class MonitoringPointGeoView(MonitoringPointView, viewsets.ReadOnlyModelViewSet):
    serializer_class = MonitoringPointGeoSerializer


class MonitoringCampaignFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    monitoring_plan = UUIDListFilter()
    company = UUIDListFilter(field_name="monitoring_plan__company")

    date__gte = DateTzFilter(field_name="end_date", lookup_expr="gte")
    date__lte = DateTzFilter(field_name="start_date", lookup_expr="lte")

    firm = UUIDListFilter()
    action = ListFilter(method="get_action")
    procedures = UUIDListFilter()
    cycle_firm = ListFilter(method="get_cycle_firm")

    class Meta:
        model = MonitoringCampaign
        fields = ["company"]

    def get_action(self, queryset, name, value):
        actions = ServiceOrderAction.objects.filter(uuid__in=value.split(","))

        cycles = MonitoringCycle.objects.filter(service_orders__actions__in=actions)

        return queryset.filter(monitoring_plan__cycles_plan__in=cycles)

    def get_cycle_firm(self, queryset, name, value):
        firms = Firm.objects.filter(uuid__in=value.split(","))

        cycles = MonitoringCycle.objects.filter(
            Q(executers__in=firms)
            | Q(viewers__in=firms)
            | Q(evaluators__in=firms)
            | Q(approvers__in=firms)
        )

        return queryset.filter(monitoring_plan__cycles_plan__in=cycles)


def get_self_campaigns(user, user_company):
    user_firms = list((user.user_firms.all()).union(user.user_firms_manager.all()))
    return MonitoringCampaign.objects.filter(
        Q(monitoring_plan__company_id=user_company)
        & (Q(created_by=user) | Q(firm__in=user_firms))
    )


class MonitoringCampaignView(viewsets.ModelViewSet):
    serializer_class = MonitoringCampaignSerializer
    permission_classes = [IsAuthenticated, MonitoringCampaignPermissions]
    filterset_class = MonitoringCampaignFilter
    permissions = None
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return MonitoringCampaign.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MonitoringCampaign",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, MonitoringCampaign.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    get_self_campaigns(self.request.user, user_company),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MonitoringCampaign.objects.filter(
                        monitoring_plan__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MonitoringCampaign.objects.filter(
                monitoring_plan__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class MonitoringCollectFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    monitoring_plan = ListFilter(field_name="occurrence_record__monitoring_plan")
    company = UUIDListFilter()
    monitoring_point = UUIDListFilter()
    parameter_group = UUIDListFilter()
    occurrence_record = UUIDListFilter()

    datetime = DateFromToRangeCustomFilter()
    search = CharFilter(label="search", method="get_search")
    dict_form_data = KeyFilter(allow_null=True)
    status_is_final = filters.BooleanFilter(
        label="status_is_final", method="get_status_is_final"
    )

    firm = UUIDListFilter(field_name="occurrence_record__firm")

    class Meta:
        model = MonitoringCollect
        fields = ["company"]

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "number",
                Value(" "),
                "monitoring_point__code",
                Value(" "),
                "occurrence_record__number",
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )

    def get_status_is_final(self, queryset, name, value):
        if value:
            return queryset.filter(occurrence_record__is_approved=True).distinct()
        return MonitoringCollect.objects.none()


class MonitoringCollectView(viewsets.ModelViewSet):
    serializer_class = MonitoringCollectSerializer
    permission_classes = [IsAuthenticated, MonitoringCollectPermissions]
    filterset_class = MonitoringCollectFilter
    permissions = None
    # Manually setting resource_name because we use the JSON API renderer manually
    # in the autofill function
    resource_name = "MonitoringCollect"
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return MonitoringCollect.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MonitoringCollect",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, MonitoringCollect.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MonitoringCollect.objects.filter(
                        Q(company_id=user_company)
                        & (
                            Q(created_by=self.request.user)
                            | Q(responsible=self.request.user)
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MonitoringCollect.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MonitoringCollect.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="GetCollects", detail=False)
    def get_collects(self, request, pk=None):
        if (
            "company" not in request.query_params.keys()
            or "monitoring_plan" not in request.query_params.keys()
            or "monitoring_points" not in request.query_params.keys()
        ):
            raise serializers.ValidationError("kartado.error.missing_parameters")

        try:
            frequencies = MonitoringFrequency.objects.filter(
                monitoring_plan__company_id=request.query_params.get("company"),
                monitoring_plan_id=request.query_params.get("monitoring_plan"),
                monitoring_points__in=request.query_params.get(
                    "monitoring_points"
                ).split(","),
                active=True,
            ).distinct()
        except Exception:
            raise serializers.ValidationError("kartado.error.incorrect_parameters")

        all_results = [
            {
                "uuid": str(uuid.uuid4()),
                "monitoring_point": str(item.uuid),
                "monitoring_frequency": str(frequency.uuid),
                "parameter_group": str(frequency.parameter_group_id),
                "datetime": None,
                "responsible": None,
                "parameters": len(
                    get(
                        "form_fields.fields",
                        frequency.parameter_group,
                        default=[],
                    )
                )
                + len(
                    get(
                        "repetition.form_fields.extra_fields",
                        frequency.parameter_group,
                        default=[],
                    )
                )
                + get("repetition.limit", frequency.parameter_group, default=0),
            }
            for frequency in frequencies
            for item in frequency.monitoring_points.all()
        ]

        results = [{"id": i + 1, **item} for i, item in enumerate(all_results)]

        def uniqWith(input_array, compare_function):
            return [
                elem
                for index, elem in enumerate(input_array)
                if not any(compare_function(elem, b) for b in input_array[:index])
            ]

        # make unique by point and parameter group
        results = uniqWith(
            results,
            lambda a, b: a["monitoring_point"] == b["monitoring_point"]
            and a["parameter_group"] == b["parameter_group"],
        )

        return Response({"type": "MonitoringCollects", "attributes": results})


class MonitoringRecordFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    monitoring_plan = ListFilter(field_name="monitoring_campaign__monitoring_plan")
    company = UUIDListFilter()
    monitoring_point = UUIDListFilter()
    parameter_group = UUIDListFilter()
    abnormal = filters.BooleanFilter(label="abnormal", method="is_abnormal")

    date__gte = DateTzFilter(field_name="datetime", lookup_expr="gte")
    date__lte = DateTzFilter(field_name="datetime", lookup_expr="lte")

    campaign_date__gte = DateTzFilter(
        field_name="monitoring_campaign__end_date", lookup_expr="gte"
    )
    campaign_date__lte = DateTzFilter(
        field_name="monitoring_campaign__start_date", lookup_expr="lte"
    )

    firm = UUIDListFilter(field_name="monitoring_campaign__firm")
    cycle_firm = ListFilter(method="get_cycle_firm")
    action = ListFilter(method="get_action")
    procedures = UUIDListFilter()

    class Meta:
        model = MonitoringRecord
        fields = ["company"]

    def is_abnormal(self, queryset, name, value):
        # It is necessary to use list comprehension
        # because @property cannot be used in filters
        normal_ids = [item.pk for item in queryset if item.is_normal]
        if value:
            return queryset.exclude(pk__in=normal_ids).distinct()
        return queryset.filter(pk__in=normal_ids).distinct()

    def get_action(self, queryset, name, value):
        actions = ServiceOrderAction.objects.filter(uuid__in=value.split(","))

        cycles = MonitoringCycle.objects.filter(service_orders__actions__in=actions)

        return queryset.filter(
            monitoring_campaign__monitoring_plan__cycles_plan__in=cycles
        )

    def get_cycle_firm(self, queryset, name, value):
        firms = Firm.objects.filter(uuid__in=value.split(","))

        cycles = MonitoringCycle.objects.filter(
            Q(executers__in=firms)
            | Q(viewers__in=firms)
            | Q(evaluators__in=firms)
            | Q(approvers__in=firms)
        )

        return queryset.filter(
            monitoring_campaign__monitoring_plan__cycles_plan__in=cycles
        )


class MonitoringRecordView(viewsets.ModelViewSet):
    serializer_class = MonitoringRecordSerializer
    permission_classes = [IsAuthenticated, MonitoringRecordPermissions]
    filterset_class = MonitoringRecordFilter
    permissions = None
    # Manually setting resource_name because we use the JSON API renderer manually
    # in the autofill function
    resource_name = "MonitoringRecord"
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return MonitoringRecord.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MonitoringRecord",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, MonitoringRecord.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MonitoringRecord.objects.filter(
                        Q(company_id=user_company)
                        & (
                            Q(created_by=self.request.user)
                            | Q(
                                monitoring_campaign__in=get_self_campaigns(
                                    self.request.user, user_company
                                )
                            )
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MonitoringRecord.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MonitoringRecord.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class OperationalControlFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="firm__company")
    service_orders = UUIDListFilter()
    kind = ListFilter()
    map_default_filters = KeyFilter(allow_null=True)
    op_control_records = UUIDListFilter()
    config_occurrence_types = UUIDListFilter()

    class Meta:
        model = OperationalControl
        fields = ["company", "show_map"]


class OperationalControlView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = OperationalControlSerializer
    permission_classes = [IsAuthenticated, OperationalControlPermissions]
    filterset_class = OperationalControlFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        if self.action in ["list", "retrieve"]:
            if "company" not in self.request.query_params:
                return OperationalControl.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="OperationalControl",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()
            all_permission = self.permissions.all_permissions
            can_create_operational = any(
                get(
                    "occurrence_record.can_create_operational",
                    all_permission,
                    default=[],
                )
            )

            if can_create_operational:
                allowed_queryset = ["all"]

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, OperationalControl.objects.none())
            if "self" in allowed_queryset:
                now = timezone.now()
                user_firms = self.request.user.user_firms.all()

                queryset = join_queryset(
                    queryset,
                    OperationalControl.objects.filter(
                        Q(firm__company_id=user_company)
                        & (
                            Q(responsible=self.request.user)
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
                                    Q(
                                        operational_control_cycles__creators__in=user_firms
                                    )
                                    | Q(
                                        operational_control_cycles__viewers__in=user_firms
                                    )
                                )
                            )
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    OperationalControl.objects.filter(firm__company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = OperationalControl.objects.filter(
                firm__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["GET"], url_path="Plots", detail=True)
    def get_plots(self, request, pk=None):
        op_control = self.get_object()

        # Handle dates
        date_before = (
            request.query_params["date_before"]
            if "date_before" in request.query_params
            else None
        )
        date_after = (
            request.query_params["date_after"]
            if "date_after" in request.query_params
            else None
        )

        # Attempts to parse dates
        try:
            if date_before is not None:
                date_before = datetime.strptime(date_before, "%Y-%m-%d")
            if date_after is not None:
                date_after = datetime.strptime(date_after, "%Y-%m-%d")
        except ValueError:
            raise serializers.ValidationError("kartado.error.invalid_date_format")

        # Handle water meter filter
        hydrometer_uuid = (
            request.query_params["hydrometer"].split(",")
            if "hydrometer" in request.query_params
            and request.query_params["hydrometer"]
            else None
        )

        # Get the records
        kwargs = {"form_data__records__isnull": True}
        if hydrometer_uuid:  # If filter is being used
            kwargs["uuid__in"] = hydrometer_uuid
        water_meter_records = op_control.op_control_records.filter(**kwargs)

        # If no water meter is found, throw error
        if water_meter_records.count() == 0:
            raise serializers.ValidationError(
                "kartado.error.occurrence_record.water_meter_not_found"
            )

        # Prepare query according to provided data
        kwargs = {"form_data__records__isnull": False}
        if hydrometer_uuid:
            kwargs["form_data__records__in"] = hydrometer_uuid
        if date_before:
            kwargs["datetime__date__lte"] = date_before
        if date_after:
            kwargs["datetime__date__gte"] = date_after

        # Run the query for consumption records
        consumption_records = op_control.op_control_records.filter(**kwargs).order_by(
            "datetime"
        )

        # If no consumption record is found, throw error
        if consumption_records.count() == 0:
            raise serializers.ValidationError(
                "kartado.error.occurrence_record.water_meter_not_found"
            )

        # Get meter's OccurrenceType
        meter_occ_type = water_meter_records.first().occurrence_type

        # Build month_sum dict with possible apiName values
        API_NAMES = ["fontType", "useType", "treatmentType", "discardType"]
        month_sum = {}
        for api_name in API_NAMES:
            field_name = to_snake_case(api_name)

            result_dict = {}

            font_type = next(
                field
                for field in meter_occ_type.form_fields["fields"]
                if field["api_name"] == api_name
            )
            font_type_opts = font_type["select_options"]["options"]

            for option in font_type_opts:
                meter_uuids = [
                    str(x.uuid)
                    for x in water_meter_records
                    if field_name in x.form_data
                    and x.form_data[field_name] == option["value"]
                ]
                quantities = [
                    x.form_data["quantity"]
                    for x in consumption_records
                    if x.form_data["records"] in meter_uuids
                ]
                result_dict[option["name"]] = sum(quantities)

            result_dict["Total"] = sum(result_dict.values())

            month_sum[api_name] = result_dict

        # Extract info by day
        data_dict = {}  # Holds the data temporarily as dict for easy indexing
        daily_amount = []  # Holds the data in the final arragement

        for record in consumption_records:
            day = record.datetime.strftime("%Y-%m-%d")
            amount = record.form_data["quantity"]

            if day in data_dict:
                data_dict[day] += amount
            else:
                data_dict[day] = amount

        # remember consumption_records is ordered by datetime
        first_record_date = consumption_records.first().datetime
        now = timezone.now()
        # If both filters are provided, use that range
        if date_after and date_before:
            days = Arrow.range("day", date_after, date_before)
        # Only ending limit is provided
        elif date_before and date_after is None:
            days = Arrow.range("day", first_record_date, date_before)
        # Only starting limit is provided
        elif date_after and date_before is None:
            days = Arrow.range("day", date_after, now)
        # No limit provided
        else:
            days = Arrow.range("day", first_record_date, now)

        # Convert iterable to list
        days = list(days)

        # Fill remaning daily data with zeros
        for day in days:
            if day.date() > now.date():
                continue

            day_key = day.format("YYYY-MM-DD")
            if day_key not in data_dict:
                data_dict[day_key] = 0

        # Organize data inside daily_amount
        for day, amount in data_dict.items():
            entry = {"day": day, "amount": amount}
            daily_amount.append(entry)

        # Sort daily_amount
        def daily_amount_sort(entry):
            return datetime.strptime(entry["day"], "%Y-%m-%d")

        daily_amount.sort(key=daily_amount_sort)

        # Extract info by hour
        data_dict = {}  # Holds the data temporarily as dict for easy indexing
        hourly_amount = []  # Holds the data in the final arragement
        for record in consumption_records:
            date_and_hour = record.datetime.strftime("%Y-%m-%d %H:00")
            amount = record.form_data["quantity"]

            if date_and_hour in data_dict:
                data_dict[date_and_hour] += amount
            else:
                data_dict[date_and_hour] = amount

        # Fill remaning hourly data with zeros
        for day in days:
            # If date is in the future, ignore it
            if day.date() > now.date():
                continue
            # If day has same date as now, limit to current hour
            if day.date() == now.date():
                hour_range = range(0, now.hour + 1)  # +1 due to exclusive range
            # Other cases are free from restrictions
            else:
                hour_range = range(0, 24)  # 24 hours

            date_portion = day.format("YYYY-MM-DD")

            for hour in hour_range:
                date_hour_key = "{} {:02d}:00".format(date_portion, hour)
                if date_hour_key not in data_dict:
                    data_dict[date_hour_key] = 0

        # Organize data inside hourly_amount
        for date_and_hour, amount in data_dict.items():
            entry = {"dateAndHour": date_and_hour, "amount": amount}
            hourly_amount.append(entry)

        # Sort hourly_amount
        def hourly_amount_sort(entry):
            return datetime.strptime(entry["dateAndHour"], "%Y-%m-%d %H:00")

        hourly_amount.sort(key=hourly_amount_sort)

        response_data = {
            "monthSum": month_sum,
            "dailyAmount": daily_amount,
            "hourlyAmount": hourly_amount,
        }

        return Response(response_data)


class OperationalCycleFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    creators = UUIDListFilter()
    viewers = UUIDListFilter()
    operational_control = UUIDListFilter()
    created_by = UUIDListFilter()
    created_at = DateTimeFromToRangeFilter()

    class Meta:
        model = OperationalCycle
        fields = [
            "uuid",
            "number",
            "start_date",
            "end_date",
            "creators",
            "viewers",
            "operational_control",
            "created_by",
            "created_at",
        ]


class OperationalCycleView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = OperationalCycleSerializer
    permission_classes = [IsAuthenticated, OperationalCyclePermissions]
    filterset_class = OperationalCycleFilter
    permissions = None
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return OperationalCycle.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="OperationalCycle",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, OperationalCycle.objects.none())
            if "self" in allowed_queryset:
                user_firms = list(
                    (self.request.user.user_firms.all()).union(
                        self.request.user.user_firms_manager.all()
                    )
                )
                queryset = join_queryset(
                    queryset,
                    OperationalCycle.objects.filter(
                        Q(operational_control__firm__company_id=user_company)
                        & (
                            Q(created_by=self.request.user)
                            | Q(creators__in=user_firms)
                            | Q(viewers__in=user_firms)
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    OperationalCycle.objects.filter(
                        operational_control__firm__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = OperationalCycle.objects.filter(
                operational_control__firm__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


def shift_ranges_by(date_ranges, days=0):
    new_ranges = []
    for date_range in date_ranges:
        new_ranges.append([a + timedelta(days=days) for a in date_range])

    return new_ranges


def trim_ranges(date_ranges, start_date, end_date):
    if date_ranges[0][0] < start_date:
        date_ranges[0] = (arrow_get(start_date), date_ranges[0][1])
    if date_ranges[-1][1] > end_date:
        date_ranges[-1] = (date_ranges[-1][0], arrow_get(end_date))

    return date_ranges


class MonitoringFullScheduleView(APIView):
    permission_classes = [IsAuthenticated]
    permissions = None

    def get(self, request, format=None):
        try:
            _ = Company.objects.get(
                pk=self.request.query_params["company"], users=self.request.user
            )
        except Exception:
            return error_message(400, "Company não encontrada")

        date_filters = {
            "date__lte": None,
            "date__gte": None,
            "campaign_date__lte": None,
            "campaign_date__gte": None,
        }

        for filter_name in date_filters.keys():
            if filter_name in self.request.query_params:
                date_filters[filter_name] = date_tz(
                    self.request.query_params[filter_name]
                )

        plans = MonitoringPlan.objects.filter(
            company=self.request.query_params["company"]
        )

        if "monitoring_plan" in self.request.query_params:
            plans = plans.filter(pk=self.request.query_params["monitoring_plan"])

        frequencies = MonitoringFrequency.objects.filter(
            monitoring_plan__in=plans
        ).prefetch_related("monitoring_points", "parameter_group")

        collects = MonitoringCollect.objects.filter(
            occurrence_record__monitoring_plan__in=plans
        )

        schedules = []

        def get_collect_for_point(point, parameter_group, date_range):
            try:
                collect = next(
                    a
                    for a in collects
                    if str(a.monitoring_point.uuid) == str(point.uuid)
                    if str(a.parameter_group.uuid) == str(parameter_group.uuid)
                    and a.datetime
                    and a.datetime >= date_range[0]
                    and a.datetime <= date_range[1]
                )
            except StopIteration:
                return None
            else:
                return collect

        for frequency in frequencies:
            ranges = get_dates_by_frequency(
                frequency.frequency, frequency.start_date, frequency.end_date
            )
            if frequency.frequency == "week":
                ranges = shift_ranges_by(ranges, days=-1)
            ranges = trim_ranges(ranges, frequency.start_date, frequency.end_date)
            parameter_group = frequency.parameter_group
            if not parameter_group:
                continue

            frequency_points = frequency.monitoring_points.all()

            for date_range in ranges:
                # remove schedules that are within weekends
                if (
                    date_range[0].isoweekday() > 5
                    and date_range[1].isoweekday() > 5
                    and date_range[0].shift(days=+3) > date_range[1]
                ):
                    continue

                done = True
                done_late = False
                for point in frequency_points:
                    collect = get_collect_for_point(point, parameter_group, date_range)
                    if collect:
                        try:
                            filled_fields = len(collect.dict_form_data.keys())
                        except AttributeError:
                            # In case no field is filled and form_data is None
                            filled_fields = 0

                        form_fields = len(collect.parameter_group.form_fields["fields"])
                        if filled_fields < form_fields:
                            done = False
                            break
                        if collect.created_at > date_range[1]:
                            done_late = True
                    else:
                        done = False
                        break

                # has_campaign = get_campaign_for_frequency(frequency, date_range)

                schedules.append(
                    {
                        "id": str(frequency.uuid),
                        "attributes": {
                            "start": date_range[0].isoformat(),
                            "end": date_range[1].isoformat(),
                            "frequency": frequency.frequency,
                            "parameterGroupName": parameter_group.name,
                            "pointCodes": ", ".join([a.code for a in frequency_points]),
                            "done": done,
                            "doneLate": done_late,
                        },
                        "relationships": {
                            "parameterGroup": {
                                "data": {
                                    "id": str(parameter_group.uuid),
                                    "type": "ParameterGroup",
                                }
                            },
                            "points": [
                                {"id": str(a.uuid), "type": "MonitoringPoint"}
                                for a in frequency_points
                            ],
                        },
                    }
                )

        return Response(
            {
                "type": "MonitoringSchedule",
                "id": "",
                "attributes": {"schedules": schedules},
            }
        )


class MaterialItemFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    operational_control = UUIDListFilter()
    occurrence_record = ListFilter(field_name="operational_control__op_control_records")
    entity = UUIDListFilter()

    class Meta:
        model = MaterialItem
        fields = ["company"]


class MaterialItemView(viewsets.ModelViewSet):
    serializer_class = MaterialItemSerializer
    permission_classes = [IsAuthenticated, MaterialItemPermissions]
    filterset_class = MaterialItemFilter
    permissions = None
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return MaterialItem.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MaterialItem",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, MaterialItem.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MaterialItem.objects.filter(
                        company_id=user_company,
                        created_by_id=self.request.user.uuid,
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MaterialItem.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MaterialItem.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class MaterialUsageFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    material_item = UUIDListFilter()
    occurrence_record = UUIDListFilter()
    operational_control = ListFilter(method="get_operational_control")
    company = UUIDListFilter(field_name="material_item__company")

    class Meta:
        model = MaterialUsage
        fields = ["company"]

    def get_operational_control(self, queryset, name, value):
        ids = value.split(",")

        return queryset.filter(occurrence_record__operational_control__in=ids)


class MaterialUsageView(viewsets.ModelViewSet):
    serializer_class = MaterialUsageSerializer
    permission_classes = [IsAuthenticated, MaterialUsagePermissions]
    filterset_class = MaterialUsageFilter
    permissions = None

    ordering_fields = [
        "uuid",
        "created_by__first_name",
        "created_by__last_name",
        "approved_by__first_name",
        "approved_by__last_name",
        "amount",
        "unit_price",
        "total_price",
        "creation_date",
        "approval_status",
        "approval_date",
        "material_item__name",
    ]
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return MaterialUsage.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="MaterialUsage",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, MaterialUsage.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MaterialUsage.objects.filter(
                        material_item__company_id=user_company,
                        created_by_id=self.request.user.uuid,
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    MaterialUsage.objects.filter(
                        material_item__company_id=user_company
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = MaterialUsage.objects.filter(
                material_item__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())
