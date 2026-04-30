from django.db import IntegrityError
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import ResourceRelatedField
from simple_history.utils import bulk_create_with_history

from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import Reporting
from helpers.apps.services import (
    create_or_update_services_and_usages,
    create_services_from_measurement,
    remove_usages_from_measurement,
)
from helpers.mixins import EagerLoadingMixin

from .models import (
    Goal,
    GoalAggregate,
    Measurement,
    MeasurementService,
    Service,
    ServiceSpecs,
    ServiceUsage,
)


class ServiceSpecsFormulaSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    class Meta:
        model = ServiceSpecs
        fields = ["formula"]


class ServiceSerializer(serializers.ModelSerializer, EagerLoadingMixin):

    _SELECT_RELATED_FIELDS = ["company"]
    _PREFETCH_RELATED_FIELDS = ["occurrence_types", "service_specs"]

    uuid = serializers.UUIDField(required=False)
    occurrence_types = ResourceRelatedField(
        queryset=OccurrenceType.objects, many=True, required=False
    )
    discount = serializers.SerializerMethodField()
    included_serializers = {"service_specs": ServiceSpecsFormulaSerializer}

    class Meta:
        model = Service
        fields = [
            "uuid",
            "name",
            "unit_price",
            "total_amount",
            "current_balance",
            "adjustment_coefficient",
            "company",
            "occurrence_types",
            "service_specs",
            "kind",
            "code",
            "unit",
            "group",
            "initial_price",
            "discount",
            "metadata",
        ]
        extra_kwargs = {"service_specs": {"required": False}}

    class JSONAPIMeta:
        included_resources = ["service_specs"]

    def get_discount(self, obj):
        try:
            if (obj.unit_price != 0) and (obj.initial_price != 0):
                return (obj.unit_price - obj.initial_price) / obj.unit_price
        except Exception:
            return 0


class ServiceSpecsSerializer(serializers.ModelSerializer, EagerLoadingMixin):

    _SELECT_RELATED_FIELDS = ["service", "occurrence_type"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = ServiceSpecs
        fields = ["uuid", "formula", "service", "occurrence_type"]


class ServiceUsageSerializer(serializers.ModelSerializer, EagerLoadingMixin):

    _SELECT_RELATED_FIELDS = ["service", "reporting", "measurement"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = ServiceUsage
        fields = [
            "uuid",
            "service",
            "reporting",
            "measurement",
            "amount",
            "formula",
        ]
        read_only_fields = ["amount", "formula"]


class MeasurementSerializer(serializers.ModelSerializer, EagerLoadingMixin):

    _SELECT_RELATED_FIELDS = [
        "created_by",
        "company",
        "previous_measurement",
        "next_measurement",
    ]
    _PREFETCH_RELATED_FIELDS = ["measurement_usage", "measurement_services"]

    uuid = serializers.UUIDField(required=False)
    next_measurement = ResourceRelatedField(required=False, read_only=True)
    count = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Measurement
        fields = [
            "uuid",
            "number",
            "start_date",
            "end_date",
            "created_at",
            "created_by",
            "company",
            "previous_measurement",
            "next_measurement",
            "approved",
            "count",
            "total_price",
        ]
        read_only_fields = [
            "previous_measurement",
            "next_measurement",
            "created_at",
        ]

    def get_count(self, obj):
        try:
            reporting_ids = [a.reporting_id for a in obj.measurement_usage.all()]
            return len(set(reporting_ids))
        except Exception:
            return 0

    def get_total_price(self, obj):
        measurement_services = obj.measurement_services.all()
        price = 0
        for usage in obj.measurement_usage.all():
            try:
                service = next(
                    a for a in measurement_services if a.service_id == usage.service_id
                )
                price += (
                    usage.amount * service.unit_price * service.adjustment_coefficient
                )
            except (StopIteration, TypeError):
                continue

        return round(price, 2)

    def validate(self, data):
        dates = ["start_date", "end_date"]

        if set(dates).issubset(data):

            if data["start_date"] >= data["end_date"]:
                raise serializers.ValidationError(
                    "A data final deve ser maior que a inicial"
                )

            if self.instance:
                company = self.instance.company
            else:
                company = data["company"]

            qs = Measurement.objects.filter(company=company).filter(
                start_date__lte=data["end_date"],
                end_date__gte=data["start_date"],
            )

            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise serializers.ValidationError(
                    "Já existe um período conflitante com o selecionado"
                )

        return super(MeasurementSerializer, self).validate(data)

    def update(self, instance, validated_data):
        if instance.approved:
            raise serializers.ValidationError(
                "Não é possível editar uma medição que já foi aprovada"
            )

        if "reportings" in self.initial_data:
            reporting_ids_list = [
                reporting["id"] for reporting in self.initial_data["reportings"]
            ]
            reportings = Reporting.objects.filter(pk__in=reporting_ids_list).distinct()
            user = self._context["request"].user
            create_or_update_services_and_usages(instance, reportings, user)

        if "remove_reportings" in self.initial_data:
            reporting_ids_list = [
                reporting["id"] for reporting in self.initial_data["remove_reportings"]
            ]
            reportings = Reporting.objects.filter(pk__in=reporting_ids_list).distinct()
            user = self._context["request"].user
            remove_usages_from_measurement(instance, reportings, user)

        return super(MeasurementSerializer, self).update(instance, validated_data)

    def create(self, validated_data):
        try:
            previous_measurement = Measurement.objects.filter(
                company=validated_data["company"]
            ).latest("created_at")
        except Exception:
            previous_measurement = None

        instance = Measurement.objects.create(
            previous_measurement=previous_measurement, **validated_data
        )
        create_services_from_measurement(instance)

        if "reportings" in self.initial_data:
            reporting_ids_list = [
                reporting["id"] for reporting in self.initial_data["reportings"]
            ]
            reportings = Reporting.objects.filter(pk__in=reporting_ids_list).distinct()
            user = self._context["request"].user
            create_or_update_services_and_usages(instance, reportings, user)

        return instance


class MeasurementServiceSerializer(serializers.ModelSerializer, EagerLoadingMixin):

    _SELECT_RELATED_FIELDS = ["service", "measurement"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = MeasurementService
        fields = [
            "uuid",
            "service",
            "measurement",
            "unit_price",
            "balance",
            "adjustment_coefficient",
        ]
        read_only_fields = ["unit_price", "balance", "adjustment_coefficient"]


class GoalSerializer(serializers.ModelSerializer, EagerLoadingMixin):

    _SELECT_RELATED_FIELDS = ["occurrence_type", "aggregate", "service"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = Goal
        fields = [
            "uuid",
            "occurrence_type",
            "amount",
            "aggregate",
            "service",
            "internal",
        ]


class GoalAggregateSerializer(serializers.ModelSerializer, EagerLoadingMixin):

    _SELECT_RELATED_FIELDS = ["company"]
    _PREFETCH_RELATED_FIELDS = ["goals"]

    uuid = serializers.UUIDField(required=False)
    goals = ResourceRelatedField(required=False, read_only=True, many=True)

    def validate(self, data):
        dates = ["start_date", "end_date"]

        if set(dates).issubset(data):

            if data["start_date"] >= data["end_date"]:
                raise serializers.ValidationError(
                    "A data final deve ser maior que a inicial"
                )

            if self.instance:
                company = self.instance.company
            else:
                company = data["company"]

            qs = GoalAggregate.objects.filter(company=company).filter(
                start_date__lte=data["end_date"],
                end_date__gte=data["start_date"],
            )

            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise serializers.ValidationError(
                    "Já existe um período conflitante com o selecionado"
                )

        return super(GoalAggregateSerializer, self).validate(data)

    def update(self, instance, validated_data):

        if "add_goals" in self.initial_data:
            fields = ["occurrence_type", "amount", "service"]

            goals_list = [
                Goal(
                    aggregate=instance,
                    occurrence_type_id=goal["occurrence_type"],
                    amount=goal["amount"],
                    service_id=goal["service"],
                    internal=goal.get("internal", False),
                )
                for goal in self.initial_data["add_goals"]
                if set(fields).issubset(goal)
            ]
            try:
                bulk_create_with_history(goals_list, Goal)
            except IntegrityError:
                raise serializers.ValidationError(
                    "Já existe uma meta para essa classe neste período"
                )

        return super(GoalAggregateSerializer, self).update(instance, validated_data)

    def create(self, validated_data):

        # Create object
        aggregate = GoalAggregate.objects.create(**validated_data)

        if "add_goals" in self.initial_data:
            fields = ["occurrence_type", "amount", "service"]

            goals_list = [
                Goal(
                    aggregate=aggregate,
                    occurrence_type_id=goal["occurrence_type"],
                    amount=goal["amount"],
                    service_id=goal["service"],
                    internal=goal.get("internal", False),
                )
                for goal in self.initial_data["add_goals"]
                if set(fields).issubset(goal)
            ]
            if goals_list:
                bulk_create_with_history(goals_list, Goal)

        return aggregate

    class Meta:
        model = GoalAggregate
        fields = [
            "uuid",
            "company",
            "start_date",
            "end_date",
            "goals",
            "number",
            "group_goals",
        ]
