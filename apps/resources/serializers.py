import copy
from collections import OrderedDict, defaultdict

from django.db import transaction
from django.db.models import OuterRef, Prefetch, Q, Subquery
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import (
    ResourceRelatedField,
    SerializerMethodResourceRelatedField,
)

from apps.companies.models import Firm
from apps.daily_reports.models import (
    DailyReportEquipment,
    DailyReportRelation,
    DailyReportVehicle,
    DailyReportWorker,
    MultipleDailyReport,
)
from apps.monitorings.models import OperationalControl
from apps.resources.helpers.calculate_contract_additive import (
    calculate_contract_additive_values,
)
from apps.resources.models import (
    FieldSurvey,
    FieldSurveyExport,
    FieldSurveyRoad,
    MeasurementBulletinExport,
)
from apps.service_orders.const import resource_approval_status
from apps.service_orders.models import (
    AdditionalControl,
    MeasurementBulletin,
    ProcedureResource,
    ServiceOrderResource,
)
from apps.service_orders.serializers import (
    ProcedureResourceSerializer,
    ServiceOrderResourceSerializer,
)
from apps.users.models import User
from helpers.apps.contract_utils import (
    get_provisioned_price,
    get_spent_price,
    get_total_price,
)
from helpers.apps.performance_calculations import ContractItemPerformanceScope
from helpers.apps.resources import get_board_item_relation_qs
from helpers.dates import format_minutes_decimal
from helpers.field_survey import generate_survey
from helpers.fields import ReportingRelatedField
from helpers.measurement_bulletin import generate_bulletin
from helpers.mixins import EagerLoadingMixin
from helpers.serializers import UUIDSerializerMethodResourceRelatedField
from helpers.signals import DisableSignals
from helpers.strings import minutes_to_hour_str, str_hours_to_int

from .models import (
    Contract,
    ContractAdditive,
    ContractItemAdministration,
    ContractItemPerformance,
    ContractItemUnitPrice,
    ContractPeriod,
    ContractService,
    FieldSurveySignature,
    Resource,
)


class ResourceSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "resource_service_orders",
        "company",
        "created_by",
    ]

    uuid = serializers.UUIDField(required=False)

    resource_service_orders = ResourceRelatedField(read_only=True, many=True)
    contract = SerializerMethodResourceRelatedField(
        model=Contract, method_name="get_contract", read_only=True, many=False
    )

    class Meta:
        model = Resource
        fields = [
            "uuid",
            "company",
            "name",
            "total_amount",
            "unit",
            "is_extra",
            "resource_service_orders",
            "created_by",
            "contract",
        ]

    def get_contract(self, obj):
        try:
            return obj._prefetched_objects_cache["resource_service_orders"][0].contract
        except Exception:
            return None


class CustomResourceSerializer(ResourceSerializer):
    contract_service_description = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()
    order = serializers.SerializerMethodField()
    sort_string = serializers.SerializerMethodField()

    class Meta:
        model = Resource
        fields = ResourceSerializer.Meta.fields + [
            "contract_service_description",
            "remaining_amount",
            "order",
            "sort_string",
        ]

    def get_contract_service_description(self, obj):
        try:
            return obj.contract_service_description
        except Exception:
            return ""

    def get_remaining_amount(self, obj):
        try:
            return obj._prefetched_objects_cache["resource_service_orders"][
                0
            ].remaining_amount
        except Exception:
            return 0

    def get_order(self, obj):
        try:
            return obj.order
        except Exception:
            return None

    def get_sort_string(self, obj):
        try:
            return obj.sort_string
        except Exception:
            return ""


class ContractWithoutMoneySerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "firm",
        "created_by",
        "subcompany",
        "service_orders",
        "bulletins",
        "bulletins__bulletin_surveys",
        "unit_price_services",
        "administration_services",
        "performance_services",
        "performance_services__contract_item_performance",
        "administrative_informations",
        "resources",
        "responsibles_hirer",
        "responsibles_hired",
        "roads",
        "survey_responsibles_hirer",
        "survey_responsibles_hired",
        "status",
        Prefetch(
            "contract_op_controls", queryset=OperationalControl.objects.all().distinct()
        ),
    ]

    uuid = serializers.UUIDField(required=False)

    bulletins = ResourceRelatedField(
        queryset=MeasurementBulletin.objects, many=True, required=False
    )

    unit_price_services = ResourceRelatedField(
        queryset=ContractService.objects, many=True, required=False
    )
    administration_services = ResourceRelatedField(
        queryset=ContractService.objects, many=True, required=False
    )
    performance_services = ResourceRelatedField(
        queryset=ContractService.objects, many=True, required=False
    )

    survey_responsibles_hired = ResourceRelatedField(
        queryset=User.objects, many=True, required=False
    )
    survey_responsibles_hirer = ResourceRelatedField(
        queryset=User.objects, many=True, required=False
    )

    operational_controls = SerializerMethodResourceRelatedField(
        model=OperationalControl,
        method_name="get_operational_controls",
        read_only=True,
        many=True,
    )

    firms = UUIDSerializerMethodResourceRelatedField(
        model=Firm, method_name="get_firms", read_only=True, many=True
    )

    class Meta:
        model = Contract
        fields = [
            "uuid",
            "name",
            "created_at",
            "contract_start",
            "contract_end",
            "created_by",
            "firm",
            "subcompany",
            "extra_info",
            "service_orders",
            "bulletins",
            "unit_price_services",
            "administration_services",
            "performance_services",
            "administrative_informations",
            "responsibles_hirer",
            "responsibles_hired",
            "survey_responsibles_hirer",
            "survey_responsibles_hired",
            "operational_controls",
            "survey_default",
            "has_survey_default",
            "lower_grade",
            "higher_grade",
            "default_grade",
            "status",
            "performance_months",
            "firms",
        ]
        read_only_fields = [
            "created_at",
            "created_by",
            "bulletins",
            "service_orders",
            "administrative_informations",
        ]

    def get_firms(self, obj):
        filtered_firms = []
        for data in self.context["firms"]:
            if (
                data["firm_contract_services__unit_price_service_contracts"] == obj.pk
                or data["firm_contract_services__performance_service_contracts"]
                == obj.pk
                or data["firm_contract_services__administration_service_contracts"]
                == obj.pk
            ):
                if data["uuid"] not in filtered_firms:
                    filtered_firms.append(data["uuid"])
        # filtered_firms = list(set(filtered_firms))
        return filtered_firms

    def get_operational_controls(self, obj):
        return obj.contract_op_controls.all()

    def get_survey_default(self, obj):
        return obj.survey_default

    def handle_model_fields(self, contract=None):
        """
        Handles manipulation of models related to Contract
        """

        FIELD_SERIALIZERS = [
            ("unit_price_services", ContractServiceSerializer),
            ("administration_services", ContractServiceSerializer),
            ("performance_services", ContractServiceSerializer),
            ("field_survey_roads", FieldSurveyRoadSerializer),
        ]
        possible_fields = []
        deferred_serializers = {}

        # Adds the create and edit variations of the fields to possible_fields
        # along with their respective serializers
        for field in FIELD_SERIALIZERS:
            (field_name, field_serializer) = field
            field_create_name = "create_" + field_name
            field_edit_name = "edit_" + field_name

            possible_fields.append((field_create_name, field_serializer))
            possible_fields.append((field_edit_name, field_serializer))

            # Set defaults for deferred_serializers
            deferred_serializers[field_create_name] = []
            deferred_serializers[field_edit_name] = []

        for model_field, model_serializer in possible_fields:
            if model_field in self.initial_data:
                for item in self.initial_data[model_field]:
                    # If editing require an id
                    is_editing = model_field.split("_")[0] == "edit"
                    if is_editing and "id" in item:
                        item_id = item.pop("id")
                    elif is_editing and "id" not in item:
                        raise serializers.ValidationError(
                            "kartado.error.contract.inform_id_when_using_edit_fields"
                        )
                    else:
                        item_id = None

                    # Pass contract & company
                    if contract is not None:
                        contract_id = contract.uuid
                        item["contract"] = OrderedDict(
                            {"type": "Contract", "id": str(contract_id)}
                        )

                        company_id = (
                            contract.subcompany.company.uuid
                            if contract.subcompany
                            else contract.firm.company.uuid
                        )
                        item["company"] = OrderedDict(
                            {"type": "Company", "id": str(company_id)}
                        )

                    if is_editing:
                        # Determine the model
                        model = model_serializer.Meta.model

                        # Try to get the instance
                        try:
                            instance = model.objects.get(pk=item_id)
                        except model.DoesNotExist:
                            raise serializers.ValidationError(
                                "kartado.error.contract.invalid_id_on_{}".format(
                                    model_field
                                )
                            )

                        # Determine if the update is partial
                        is_partial = self.partial

                        # Add instance and item data to serializer
                        serializer = model_serializer(
                            instance=instance, data=item, partial=is_partial
                        )
                    else:
                        # Pass created_by
                        if "request" in self.context:
                            try:
                                user = self.context["request"].user
                                user_data = OrderedDict(
                                    {"type": "User", "id": str(user.pk)}
                                )
                                item["created_by"] = user_data
                                self.initial_data["created_by"] = user_data
                            except Exception:
                                pass
                        elif "created_by" in self.initial_data:
                            item["created_by"] = self.initial_data["created_by"]

                        serializer = model_serializer(data=item)

                    # If valid, defer the save until everything else is valid
                    # If not valid, errors are returned normally as JSON
                    if serializer.is_valid(raise_exception=True):
                        deferred_serializers[model_field].append(serializer)

        return deferred_serializers

    def handle_deferred_serializers(self, contract, deferred_serializers):
        """
        Receives the deferred model field serializers, creates or updates
        each instance and relate them to the provided instance if the "item_id"
        in deferred_serializers is None
        """

        unit_price_services_instances = []
        administration_services_instances = []
        performance_services_instances = []
        field_survey_roads_instances = []

        for (
            model_field,
            model_field_serializers,
        ) in deferred_serializers.items():
            for serializer in model_field_serializers:
                # Save the serializer
                related_instance = serializer.save()

                # Setup relationship to instance if it was created just now
                is_creating = model_field.split("_")[0] == "create"
                if is_creating:
                    if "unit_price_services" in model_field:
                        unit_price_services_instances.append(related_instance)
                    elif "administration_services" in model_field:
                        administration_services_instances.append(related_instance)
                    elif "performance_services" in model_field:
                        performance_services_instances.append(related_instance)
                    elif "field_survey_roads_instances" in model_field:
                        field_survey_roads_instances.append(related_instance)

        # Finally relate the instances to the Contract
        if unit_price_services_instances:
            contract.unit_price_services.add(*unit_price_services_instances)
        if administration_services_instances:
            contract.administration_services.add(*administration_services_instances)
        if performance_services_instances:
            contract.performance_services.add(*performance_services_instances)
        if field_survey_roads_instances:
            contract.roads.add(*field_survey_roads_instances)
        return contract

    @transaction.atomic
    def create(self, validated_data):
        instance = super().create(validated_data)

        # Prepare the serializers for the created models
        deferred_serializers = self.handle_model_fields(instance)

        # Finally save the serializers and relate the models to Contract
        instance = self.handle_deferred_serializers(instance, deferred_serializers)

        instance.refresh_from_db()
        instance.total_price = get_total_price(instance)
        instance.spent_price = get_spent_price(instance)
        with DisableSignals():
            instance.save()

        return instance

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)

        # Prepare the serializers for the created models
        deferred_serializers = self.handle_model_fields()

        # Finally save the serializers and relate the models to Contract
        instance = self.handle_deferred_serializers(instance, deferred_serializers)

        instance.refresh_from_db()
        instance.total_price = get_total_price(instance)
        instance.spent_price = get_spent_price(instance)
        with DisableSignals():
            instance.save()

        return instance

    def validate(self, data):
        dates = ["contract_start", "contract_end"]

        if set(dates).issubset(data):
            if data["contract_start"] >= data["contract_end"]:
                raise serializers.ValidationError(
                    "kartado.error.contract.contract_end_should_be_after_contract_start"
                )

        return super(ContractWithoutMoneySerializer, self).validate(data)


class ContractSerializer(ContractWithoutMoneySerializer, EagerLoadingMixin):
    provisioned_price = serializers.SerializerMethodField()
    remaining_price = serializers.FloatField(read_only=True)

    class Meta(ContractWithoutMoneySerializer.Meta):
        fields = ContractWithoutMoneySerializer.Meta.fields + [
            "total_price",
            "spent_price",
            "remaining_price",
            "provisioned_price",
            "spend_schedule",
        ]
        read_only_fields = ContractWithoutMoneySerializer.Meta.read_only_fields + [
            "total_price",
            "spent_price",
            "provisioned_price",
            "remaining_price",
        ]

    def get_provisioned_price(self, obj):
        provisioned_price = get_provisioned_price(obj)
        return provisioned_price

    def validate(self, data):
        dates = ["contract_start", "contract_end"]

        if set(dates).issubset(data):
            if data["contract_start"] >= data["contract_end"]:
                raise serializers.ValidationError(
                    "A data final deve ser maior que a inicial"
                )

        return super(ContractSerializer, self).validate(data)


class ContractServiceSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "firms",
        "unit_price_service_contracts",
        "administration_service_contracts",
        "performance_service_contracts",
        "contract_item_unit_prices",
        "contract_item_unit_prices__resource",
        "contract_item_administration",
        "contract_item_administration__resource",
        "contract_item_performance",
        "contract_item_performance__resource",
    ]

    uuid = serializers.UUIDField(required=False)
    unit_price_service_contracts = ResourceRelatedField(
        queryset=Contract.objects, many=True, required=False
    )
    administration_service_contracts = ResourceRelatedField(
        queryset=Contract.objects, many=True, required=False
    )
    performance_service_contracts = ResourceRelatedField(
        queryset=Contract.objects, many=True, required=False
    )

    contract_item_unit_prices = ResourceRelatedField(
        queryset=ContractItemUnitPrice.objects, many=True, required=False
    )
    contract_item_administration = ResourceRelatedField(
        queryset=ContractItemAdministration.objects, many=True, required=False
    )
    contract_item_performance = ResourceRelatedField(
        queryset=ContractItemPerformance.objects, many=True, required=False
    )

    total_price = serializers.SerializerMethodField()
    spent_price = serializers.SerializerMethodField()

    class Meta:
        model = ContractService
        fields = [
            "uuid",
            "description",
            "firms",
            "weight",
            "price",
            "unit_price_service_contracts",
            "administration_service_contracts",
            "performance_service_contracts",
            "contract_item_unit_prices",
            "contract_item_administration",
            "contract_item_performance",
            "total_price",
            "spent_price",
        ]

    def get_total_price(self, obj):
        total_price = 0.0

        try:
            if obj.contract_item_unit_prices.exists():
                item_queryset = obj.contract_item_unit_prices.all()
            elif obj.contract_item_administration.exists():
                item_queryset = obj.contract_item_administration.all()
            elif obj.contract_item_performance():
                item_queryset = obj.contract_item_performance.all()
            else:
                return total_price
            items_resources_values = item_queryset.values_list(
                "resource__unit_price", "resource__amount"
            )

            for unit_price, amount in items_resources_values:
                try:
                    resource_total_price = unit_price * amount
                    if not isinstance(resource_total_price, (int, float)):
                        raise Exception()
                    total_price += resource_total_price
                except Exception:
                    continue
        except Exception:
            pass

        return total_price

    def get_spent_price(self, obj):
        spent_price = 0.0

        try:
            if obj.contract_item_unit_prices.exists():
                item_queryset = obj.contract_item_unit_prices.all()
                procedure_resources = item_queryset.exclude(
                    resource__serviceorderresource_procedures__isnull=True
                ).values_list(
                    "resource__serviceorderresource_procedures__unit_price",
                    "resource__serviceorderresource_procedures__amount",
                    "resource__serviceorderresource_procedures__total_price",
                    "resource__serviceorderresource_procedures__measurement_bulletin",
                )
                for (
                    unit_price,
                    amount,
                    total_price,
                    measurement_bulletin,
                ) in procedure_resources:
                    try:
                        if measurement_bulletin:
                            # If total_price is not provided, find the total
                            resource_spent_price = (
                                total_price if total_price else (unit_price * amount)
                            )
                            if not isinstance(resource_spent_price, (int, float)):
                                raise Exception()
                            spent_price += resource_spent_price
                    except Exception:
                        continue
            elif obj.contract_item_administration.exists():
                item_queryset = obj.contract_item_administration.all()
                mdr_equipment = MultipleDailyReport.objects.filter(
                    multiple_daily_report_equipment=OuterRef("pk")
                )
                mdr_worker = MultipleDailyReport.objects.filter(
                    multiple_daily_report_workers=OuterRef("pk")
                )
                mdr_vehicle = MultipleDailyReport.objects.filter(
                    multiple_daily_report_vehicles=OuterRef("pk")
                )
                relation_equipment = DailyReportRelation.objects.filter(
                    equipment_id=OuterRef("pk")
                )
                relation_worker = DailyReportRelation.objects.filter(
                    worker_id=OuterRef("pk")
                )
                relation_vehicle = DailyReportRelation.objects.filter(
                    vehicle_id=OuterRef("pk")
                )
                workers = list(
                    DailyReportWorker.objects.filter(
                        contract_item_administration__uuid__in=item_queryset,
                        measurement_bulletin__isnull=False,
                        total_price__isnull=False,
                    ).annotate(
                        mdr_annotation=Subquery(
                            mdr_worker.values("day_without_work")[:1]
                        ),
                        relation_annotation=Subquery(
                            relation_worker.values("active")[:1]
                        ),
                    )
                )
                equipments = list(
                    DailyReportEquipment.objects.filter(
                        contract_item_administration__uuid__in=item_queryset,
                        measurement_bulletin__isnull=False,
                        total_price__isnull=False,
                    ).annotate(
                        mdr_annotation=Subquery(
                            mdr_equipment.values("day_without_work")[:1]
                        ),
                        relation_annotation=Subquery(
                            relation_equipment.values("active")[:1]
                        ),
                    )
                )
                vehicles = list(
                    DailyReportVehicle.objects.filter(
                        contract_item_administration__uuid__in=item_queryset,
                        measurement_bulletin__isnull=False,
                        total_price__isnull=False,
                    ).annotate(
                        mdr_annotation=Subquery(
                            mdr_vehicle.values("day_without_work")[:1]
                        ),
                        relation_annotation=Subquery(
                            relation_vehicle.values("active")[:1]
                        ),
                    )
                )
                for item in workers:
                    if item.mdr_annotation is None or (
                        item.mdr_annotation is False
                        and item.relation_annotation is True
                    ):
                        spent_price += item.total_price
                for item in equipments:
                    if item.mdr_annotation is None or (
                        item.mdr_annotation is False
                        and item.relation_annotation is True
                    ):
                        spent_price += item.total_price
                for item in vehicles:
                    if item.mdr_annotation is None or (
                        item.mdr_annotation is False
                        and item.relation_annotation is True
                    ):
                        spent_price += item.total_price
            else:
                return spent_price
        except Exception:
            pass

        return spent_price

    def handle_model_fields(self):
        """
        Handles manipulation of models related to ContractService
        """

        FIELD_SERIALIZERS = [
            ("contract_item_unit_prices", ContractItemUnitPriceSerializer),
            (
                "contract_item_administration",
                ContractItemAdministrationSerializer,
            ),
            ("contract_item_performance", ContractItemPerformanceSerializer),
        ]
        possible_fields = []
        deferred_serializers = []

        # Adds the create and edit variations of the fields to possible_fields
        # along with their respective serializers
        for field in FIELD_SERIALIZERS:
            (field_name, field_serializer) = field
            field_create_name = "create_" + field_name
            field_edit_name = "edit_" + field_name

            possible_fields.append((field_create_name, field_serializer))
            possible_fields.append((field_edit_name, field_serializer))

        # Used to avoid creating different types of contract item for the same contract service
        contract_item_type = None

        for model_field, model_serializer in possible_fields:
            if model_field in self.initial_data:
                # Throw error if two different types of contract items are used
                if contract_item_type is None:
                    contract_item_type = model_serializer.__name__
                elif contract_item_type != model_serializer.__name__:
                    raise serializers.ValidationError(
                        "kartado.error.contract_service.only_one_contract_item_type_can_be_filled_per_contract_service"
                    )

                for item in self.initial_data[model_field]:
                    # If editing require an id
                    is_editing = model_field.split("_")[0] == "edit"
                    if is_editing and "id" in item:
                        item_id = item.pop("id")
                    elif is_editing and "id" not in item:
                        raise serializers.ValidationError(
                            "kartado.error.contract_service.inform_id_when_using_edit_fields"
                        )
                    else:
                        item_id = None

                    # Pass contract regardless of operation
                    if "contract" in self.initial_data:
                        item["contract"] = self.initial_data["contract"]

                    if is_editing:
                        # Determine the model
                        model = model_serializer.Meta.model

                        # Try to get the instance
                        try:
                            instance = model.objects.get(pk=item_id)
                        except model.DoesNotExist:
                            raise serializers.ValidationError(
                                "kartado.error.contract_service.invalid_id_on_{}".format(
                                    model_field
                                )
                            )

                        # Determine if the update is partial
                        is_partial = self.partial

                        # Add instance and item data to serializer
                        serializer = model_serializer(
                            instance=instance, data=item, partial=is_partial
                        )
                    else:
                        # Pass created_by
                        if "request" in self.context:
                            try:
                                user = self.context["request"].user
                                user_data = OrderedDict(
                                    {"type": "User", "id": str(user.pk)}
                                )
                                item["created_by"] = user_data
                                self.initial_data["created_by"] = user_data
                            except Exception:
                                pass
                        elif "created_by" in self.initial_data:
                            item["created_by"] = self.initial_data["created_by"]

                        # Pass company
                        if "company" in self.initial_data:
                            item["company"] = self.initial_data["company"]

                        serializer = model_serializer(data=item)

                    # If valid, defer the save until everything else is valid
                    # If not valid, errors are returned normally as JSON
                    if serializer.is_valid(raise_exception=True):
                        deferred_serializers.append(serializer)

        return deferred_serializers

    def handle_deferred_serializers(self, contract_service, deferred_serializers):
        """
        Receives the deferred model field serializers, creates or updates
        each instance and relate them to the provided instance if the "item_id"
        in deferred_serializers is None
        """

        contract_item_unit_prices_instances = []
        contract_item_administration_instances = []
        contract_item_performance_instances = []

        for serializer in deferred_serializers:
            # Save the serializer
            related_instance = serializer.save()

            if isinstance(related_instance, ContractItemUnitPrice):
                contract_item_unit_prices_instances.append(related_instance)

            if isinstance(related_instance, ContractItemAdministration):
                contract_item_administration_instances.append(related_instance)

            if isinstance(related_instance, ContractItemPerformance):
                contract_item_performance_instances.append(related_instance)

        # Finally relate the instances to the Contract
        if contract_item_unit_prices_instances:
            contract_service.contract_item_unit_prices.add(
                *contract_item_unit_prices_instances
            )
        if contract_item_administration_instances:
            contract_service.contract_item_administration.add(
                *contract_item_administration_instances
            )
        if contract_item_performance_instances:
            contract_service.contract_item_performance.add(
                *contract_item_performance_instances
            )

    @transaction.atomic
    def create(self, validated_data):
        instance = super().create(validated_data)

        # Prepare the serializers for the created models
        deferred_serializers = self.handle_model_fields()

        # Finally save the serializers and relate the models to Contract
        self.handle_deferred_serializers(instance, deferred_serializers)

        return instance

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)

        # Prepare the serializers for the created models
        deferred_serializers = self.handle_model_fields()

        # Finally save the serializers and relate the models to Contract
        self.handle_deferred_serializers(instance, deferred_serializers)

        return instance

    def validate(self, attrs):
        unit_price_item_in_attrs = (
            "contract_item_unit_prices" in attrs and attrs["contract_item_unit_prices"]
        )
        administration_item_in_attrs = (
            "contract_item_administration" in attrs
            and attrs["contract_item_administration"]
        )
        performance_item_in_attrs = (
            "contract_item_performance" in attrs and attrs["contract_item_performance"]
        )

        if (
            unit_price_item_in_attrs
            and administration_item_in_attrs
            and performance_item_in_attrs
        ):
            raise serializers.ValidationError(
                "kartado.error.contract_service.only_one_contract_item_type_can_be_filled_per_contract_service"
            )
        elif self.instance:
            if (
                (
                    self.instance.contract_item_unit_prices.exists()
                    and administration_item_in_attrs
                )
                or (
                    self.instance.contract_item_administration.exists()
                    and unit_price_item_in_attrs
                )
                or (
                    self.instance.contract_item_performance.exists()
                    and performance_item_in_attrs
                )
            ):
                raise serializers.ValidationError(
                    "kartado.error.contract_service.contract_service_already_has_other_contract_item_type_field_filled"
                )

        return super().validate(attrs)


class BaseContractItemSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "entity",
        "resource",
        "resource__resource",
        "resource__serviceorderresource_procedures",
        "resource__additional_control_model",
        "resource__contract",
    ]

    uuid = serializers.UUIDField(required=False)

    service_order_resource = SerializerMethodResourceRelatedField(
        model=ServiceOrderResource,
        method_name="get_service_order_resource",
        read_only=True,
        many=False,
    )
    resource = SerializerMethodResourceRelatedField(
        model=Resource, method_name="get_resource", read_only=True, many=False
    )

    # Extra fields
    amount = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()
    creation_date = serializers.SerializerMethodField()
    resource_kind = serializers.SerializerMethodField()
    additional_control = serializers.SerializerMethodField()
    additional_control_model = SerializerMethodResourceRelatedField(
        model=AdditionalControl,
        method_name="get_additional_control_model",
        read_only=True,
        many=False,
    )
    pending_amount = serializers.SerializerMethodField()
    pending_price = serializers.SerializerMethodField()
    used_price = serializers.SerializerMethodField()
    resource_name = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()

    class Meta:
        fields = [
            "uuid",
            "sort_string",
            "entity",
            # Extra relationships
            "service_order_resource",
            "resource",
            # Extra fields
            "amount",
            "unit_price",
            "remaining_amount",
            "creation_date",
            "resource_kind",
            "additional_control",
            "additional_control_model",
            "pending_amount",
            "pending_price",
            "used_price",
            "resource_name",
            "unit",
            "order",
        ]
        extra_kwargs = {"entity": {"required": False}}

    def get_service_order_resource(self, obj):
        return obj.resource if obj.resource else None

    def get_resource(self, obj):
        return obj.resource.resource if obj.resource and obj.resource.resource else None

    def get_amount(self, obj):
        if obj.resource:
            return obj.resource.amount
        else:
            return 0

    def get_remaining_amount(self, obj):
        if obj.resource:
            return obj.resource.remaining_amount
        else:
            return 0

    def get_creation_date(self, obj):
        return obj.resource.creation_date if obj.resource else None

    def get_resource_kind(self, obj):
        return obj.resource.resource_kind if obj.resource else None

    def get_additional_control(self, obj):
        return obj.resource.additional_control if obj.resource else None

    def get_additional_control_model(self, obj):
        return obj.resource.additional_control_model if obj.resource else None

    def get_pending_amount(self, obj):
        board_item_relation_qs = get_board_item_relation_qs(obj)

        if board_item_relation_qs:
            pending_amount = 0
            queryset = board_item_relation_qs
        elif obj.resource:
            pending_amount = 0
            queryset = obj.resource.serviceorderresource_procedures.all()
        else:
            return None

        for instance in queryset:
            try:
                resource_pending_amount = (
                    instance.amount
                    if instance.approval_status
                    == resource_approval_status.WAITING_APPROVAL
                    else 0
                )
                if not isinstance(resource_pending_amount, (int, float)):
                    raise Exception()
                pending_amount += resource_pending_amount
            except Exception:
                continue

        return pending_amount

    def get_pending_price(self, obj):
        board_item_relation_qs = get_board_item_relation_qs(obj)

        if board_item_relation_qs:
            pending_price = 0.0
            queryset = board_item_relation_qs
        elif obj.resource:
            pending_price = 0.0
            queryset = obj.resource.serviceorderresource_procedures.all()
        else:
            return None

        for instance in queryset:
            try:
                if (
                    instance.approval_status
                    == resource_approval_status.WAITING_APPROVAL
                ):
                    if instance.total_price:
                        resource_pending_price = instance.total_price
                    elif isinstance(
                        instance,
                        (DailyReportEquipment, DailyReportWorker, DailyReportVehicle),
                    ):
                        resource_pending_price = (
                            instance.amount * obj.resource.unit_price
                        )
                    elif obj.resource:
                        resource_pending_price = instance.unit_price * instance.amount
                    else:
                        resource_pending_price
                else:
                    resource_pending_price = 0.0

                if not isinstance(resource_pending_price, (int, float)):
                    raise Exception()

                pending_price += resource_pending_price
            except Exception:
                continue

        return pending_price

    def get_unit_price(self, obj):
        return obj.resource.unit_price if obj.resource else 0

    def get_used_price(self, obj):
        board_item_relation_qs = get_board_item_relation_qs(obj)

        if board_item_relation_qs:
            spent_price = 0.0

            board_items_total_prices = board_item_relation_qs.filter(
                Q(measurement_bulletin__isnull=False)
            ).values_list("total_price", flat=True)

            for total_price in board_items_total_prices:
                spent_price += total_price if total_price else 0.0

            return spent_price
        elif obj.resource:
            return obj.resource.used_price
        else:
            return None

    def get_resource_name(self, obj):
        return (
            obj.resource.resource.name
            if obj.resource and obj.resource.resource
            else None
        )

    def get_unit(self, obj):
        return (
            obj.resource.resource.unit
            if obj.resource and obj.resource.resource
            else None
        )

    def handle_service_order_resources(self, contract_item_instance):
        """
        Handles creating and editing ServiceOrderResources.
        """
        # WARN: Since the serializer validation needs all UUIDs to exist, this happens AFTER the main instance is created

        # ServiceOrderResource
        service_order_resource_serializer = None

        if "create_service_order_resource" in self.initial_data:
            item = self.initial_data["create_service_order_resource"]

            # Pass created_by
            if "request" in self.context:
                try:
                    user = self.context["request"].user
                    user_data = OrderedDict({"type": "User", "id": str(user.pk)})
                    item["created_by"] = user_data
                    self.initial_data["created_by"] = user_data
                except Exception:
                    pass
            elif "created_by" in self.initial_data:
                item["created_by"] = self.initial_data["created_by"]

            # Pass contract & company
            if "contract" in self.initial_data:
                item["contract"] = self.initial_data["contract"]
            if "company" in self.initial_data:
                item["company"] = self.initial_data["company"]

            # Pass entity
            if "entity" in self.initial_data:
                item["entity"] = self.initial_data["entity"]

            service_order_resource_serializer = ServiceOrderResourceSerializer(
                data=item
            )
        elif "edit_service_order_resource" in self.initial_data:
            item = self.initial_data["edit_service_order_resource"]

            # Pass contract
            if "contract" in self.initial_data:
                item["contract"] = self.initial_data["contract"]

            if "id" in item:
                item_id = item.pop("id")
            else:
                raise serializers.ValidationError(
                    "kartado.error.contract_service.inform_id_when_using_edit_fields"
                )

            # Determine the model
            model = ServiceOrderResourceSerializer.Meta.model

            # Try to get the instance
            try:
                instance = model.objects.get(pk=item_id)
            except model.DoesNotExist:
                raise serializers.ValidationError(
                    "kartado.error.contract_service.invalid_id_on_edit_resource"
                )

            # Determine if the update is partial
            is_partial = self.partial

            # Add instance and item data to serializer
            service_order_resource_serializer = ServiceOrderResourceSerializer(
                instance=instance, data=item, partial=is_partial
            )

        if (
            service_order_resource_serializer
            and service_order_resource_serializer.is_valid(raise_exception=True)
        ):
            kwargs = {}
            if "created_by" in self.initial_data:
                kwargs["created_by_id"] = self.initial_data["created_by"]["id"]
            if "entity" in self.initial_data:
                kwargs["entity_id"] = self.initial_data["entity"]["id"]

            service_order_resource = service_order_resource_serializer.save(**kwargs)

            contract_item_instance.resource = service_order_resource

            contract_item_instance.save()

    @transaction.atomic
    def create(self, validated_data):
        instance = super().create(validated_data)
        self.handle_service_order_resources(instance)

        return instance

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self.handle_service_order_resources(instance)

        return instance


class FieldSurveyRoadSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["contract", "road"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = FieldSurveyRoad
        fields = ["uuid", "start_km", "end_km", "road", "contract"]


class FieldSurveySerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "measurement_bulletin",
        "contract",
        "contract__performance_services",
        "contract__performance_services__contract_item_performance",
        "created_by",
        "responsibles_hirer",
        "responsibles_hired",
        "added_to_measurement_bulletin_by",
    ]

    average_grade = serializers.SerializerMethodField()
    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = FieldSurvey
        fields = [
            "uuid",
            "created_at",
            "executed_at",
            "created_by",
            "responsibles_hirer",
            "responsibles_hired",
            "contract",
            "grades",
            "name",
            "number",
            "measurement_bulletin",
            "approval_status",
            "approval_date",
            "approved_by",
            "added_to_measurement_bulletin_by",
            "average_grade",
            "status",
            "executed_at",
            "manual",
            "final_grade",
        ]
        read_only_fields = [
            "created_at",
            "approval_date",
            "approved_by",
            "number",
            "added_to_measurement_bulletin_by",
            "average_grade",
        ]

    def cache_field_survey_roads(self):
        if not hasattr(self, "_field_survey_roads_cache"):
            field_survey_list = defaultdict(list)
            company = self.context["request"].query_params.get("company", None)
            if not company:
                self._field_survey_roads_cache = field_survey_list
                return self._field_survey_roads_cache
            field_survey_roads_queryset = list(
                FieldSurveyRoad.objects.filter(
                    contract__subcompany__company=company, contract__isnull=False
                ).prefetch_related("contract")
            )
            for item in field_survey_roads_queryset:
                field_survey_list[item.contract_id].append(item)
            self._field_survey_roads_cache = field_survey_list
        return self._field_survey_roads_cache

    def get_average_grade(self, obj):
        """
        PERFORMS THE CALCULUS "E" FROM THE ISSUE KTD-1156
        """
        total_section = 0.0
        contract_id = obj.contract_id
        survey_roads_cache = self.cache_field_survey_roads()
        survey_roads = survey_roads_cache.get(contract_id, [])
        has_bulletin = obj.measurement_bulletin is not None
        performance_services_list = (
            obj.contract.contract_services_bulletins.filter(
                measurement_bulletins=obj.measurement_bulletin
            ).prefetch_related("contract_item_performance")
            if has_bulletin
            else obj.contract.performance_services.all()
        )
        for contract_service in performance_services_list:
            total_item = 0.0
            for (
                contract_item_performance
            ) in contract_service.contract_item_performance.all():
                field_surveys = [obj]
                contr_item_p_scope = ContractItemPerformanceScope(
                    contract_item_performance,
                    field_surveys,
                    survey_roads=survey_roads,
                    survey_has_bulletin=has_bulletin,
                )
                average = contr_item_p_scope.calculate_field_surveys_average()
                total_item += average * contract_item_performance.weight / 100

            total_section += total_item * contract_service.weight / 100
        return total_section

    def validate(self, data: OrderedDict) -> OrderedDict:
        contract = data.get("contract") or data.get("contract_id")

        all_responsibles = {
            "hired": self._kwargs.get("data").get("responsibles_hired"),
            "hirer": self._kwargs.get("data").get("responsibles_hirer"),
        }
        for type, responsibles_list in all_responsibles.items():
            responsibles_ids = []
            if responsibles_list and contract:
                for responsible in responsibles_list:
                    responsibles_ids.append(responsible["id"])

                # remove duplicated ids
                responsibles_ids = list(set(responsibles_ids))
                if type == "hirer":
                    users = contract.survey_responsibles_hirer.filter(
                        pk__in=responsibles_ids
                    )

                elif type == "hired":
                    users = contract.survey_responsibles_hired.filter(
                        pk__in=responsibles_ids
                    )
                if len(users) != len(responsibles_ids):
                    raise serializers.ValidationError(
                        "Um ou mais responsáveis não são permitidos. Nenhum foi adicionado."
                    )
                else:
                    data["responsibles_" + type] = list(users)

            elif responsibles_list and not contract:
                raise serializers.ValidationError(
                    "Não é possível adicionar responsáveis sem um contrato."
                )

        return data

    def validate_final_grade(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError(
                "kartado.error.field_survey.final_grade_value_must_be_between_0_and_100"
            )
        return value

    def update(self, instance: FieldSurvey, validated_data):

        # We will delete usage items if the instance is being removed from the bulletin
        # and it's the last related FieldSurvey being removed

        if (
            instance.measurement_bulletin
            and instance.measurement_bulletin.bulletin_surveys.count() == 1
            and validated_data.get("measurement_bulletin") is None
        ):
            contract_service_bulletins = (
                instance.contract.contract_services_bulletins.filter(
                    measurement_bulletins=instance.measurement_bulletin
                )
            )
            contract_service_bulletins.delete()

        new_instance = super(FieldSurveySerializer, self).update(
            instance, validated_data
        )
        return new_instance


class ContractItemUnitPriceSerializer(BaseContractItemSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = BaseContractItemSerializer._PREFETCH_RELATED_FIELDS + [
        "contract_item_unit_price_services",
    ]

    contract_item_unit_price_services = ResourceRelatedField(
        queryset=ContractService.objects, many=True, required=False
    )

    contract_service_description = serializers.SerializerMethodField()
    contract = SerializerMethodResourceRelatedField(
        model=Contract, method_name="get_contract", read_only=True, many=False
    )

    balance = serializers.SerializerMethodField(read_only=True)
    was_from_import = serializers.BooleanField(read_only=True)

    def get_contract_service_description(self, obj):
        try:
            return ",".join(
                [a.description for a in obj.contract_item_unit_price_services.all()]
            )
        except Exception:
            return ""

    def get_contract(self, obj):
        try:
            return obj.resource.contract
        except Exception:
            return None

    def get_balance(self, obj):
        try:
            return obj.balance if obj.balance else 0.0
        except Exception:
            return None

    class Meta:
        model = ContractItemUnitPrice
        fields = BaseContractItemSerializer.Meta.fields + [
            "contract_item_unit_price_services",
            "contract_service_description",
            "contract",
            "balance",
            "was_from_import",
        ]
        extra_kwargs = BaseContractItemSerializer.Meta.extra_kwargs


class ContractItemAdministrationSerializer(
    BaseContractItemSerializer, EagerLoadingMixin
):
    _PREFETCH_RELATED_FIELDS = BaseContractItemSerializer._PREFETCH_RELATED_FIELDS + [
        "contract_item_administration_services",
        "contract_item_administration_workers",
        "contract_item_administration_vehicles",
        "contract_item_administration_equipment",
        "contract_item_administration_services__firms",
        "contract_item_administration_services__administration_service_contracts",
        "content_type",
    ]

    descriptions = serializers.SerializerMethodField()

    contract_item_administration_services = ResourceRelatedField(
        queryset=ContractService.objects, many=True, required=False
    )

    content_type_name = serializers.SerializerMethodField()

    firms = SerializerMethodResourceRelatedField(
        model=Firm, method_name="get_firms", read_only=True, many=True
    )
    contract = SerializerMethodResourceRelatedField(
        model=Contract, method_name="get_contract", read_only=True, many=False
    )
    expected_amount = serializers.SerializerMethodField()

    balance = serializers.SerializerMethodField(read_only=True)
    was_from_import = serializers.BooleanField(read_only=True)

    class Meta:
        model = ContractItemAdministration
        fields = BaseContractItemSerializer.Meta.fields + [
            "content_type",
            "contract_item_administration_services",
            "descriptions",
            "firms",
            "content_type_name",
            "contract",
            "balance",
            "expected_amount",
            "was_from_import",
        ]
        extra_kwargs = {
            "entity": {"required": False},
            "content_type": {"required": True},
        }

    def get_contract(self, obj):
        try:
            return obj.resource.contract
        except Exception:
            return None

    def get_descriptions(self, obj):
        try:
            return [obj.contract_item_administration_services.all()[0].description]
        except Exception:
            return ""

    def get_content_type_name(self, obj):
        try:
            return obj.content_type.model
        except Exception:
            return ""

    def get_firms(self, obj):
        firms = []
        for contract_service in obj.contract_item_administration_services.all():
            firms += list(contract_service.firms.all())

        return firms

    def get_balance(self, obj):
        try:
            return obj.balance if obj.balance else 0.0
        except Exception:
            return None

    def get_expected_amount(self, obj):
        try:
            return round(
                obj.resource.amount
                / (
                    obj.contract_item_administration_services.all()[0]
                    .administration_service_contracts.all()[0]
                    .performance_months
                ),
                2,
            )
        except Exception:
            return 0


class ContractItemPerformanceSerializer(BaseContractItemSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = BaseContractItemSerializer._PREFETCH_RELATED_FIELDS + [
        "contract_item_performance_services"
    ]

    contract_item_performance_services = ResourceRelatedField(
        queryset=ContractService.objects, many=True, required=False
    )
    contract = SerializerMethodResourceRelatedField(
        model=Contract, method_name="get_contract", read_only=True, many=False
    )
    contract_service_description = serializers.SerializerMethodField()

    contract_service_weight = serializers.SerializerMethodField()

    class Meta:
        model = ContractItemPerformance
        fields = BaseContractItemSerializer.Meta.fields + [
            "contract_item_performance_services",
            "weight",
            "contract",
            "contract_service_description",
            "contract_service_weight",
        ]
        extra_kwargs = BaseContractItemSerializer.Meta.extra_kwargs

    def get_contract(self, obj):
        try:
            return obj.resource.contract
        except Exception:
            return None

    def get_contract_service_description(self, obj):
        try:
            return getattr(
                obj.contract_item_performance_services.all()[0], "description", None
            )
        except Exception:
            return ""

    def get_contract_service_weight(self, obj):
        try:
            return getattr(
                obj.contract_item_performance_services.all()[0], "weight", None
            )
        except Exception:
            return None


class HumanResourceSerializer(ContractSerializer):
    spent_hours = serializers.SerializerMethodField()
    name = serializers.CharField(required=False, default="", allow_blank=True)

    responsibles_hirer = serializers.ResourceRelatedField(
        many=True, required=False, read_only=True
    )
    responsibles_hired = serializers.ResourceRelatedField(
        many=True, required=False, read_only=True
    )
    responsible = SerializerMethodResourceRelatedField(
        model=User, method_name="get_responsible"
    )

    class Meta(ContractSerializer.Meta):
        model = Contract
        fields = ContractSerializer.Meta.fields + [
            "spent_hours",
            "name",
            "responsible",
        ]

    def get_spent_hours(self, obj):
        total_hours = 0
        for resource in obj.resources.all():
            for usage in resource.serviceorderresource_procedures.all():
                total_hours += usage.amount

        return minutes_to_hour_str(total_hours)

    def get_responsible(self, obj):
        try:
            return obj.responsibles_hirer.all()[0]
        except Exception:
            return None

    def validate(self, data):
        if "get_responsible" not in data:
            raise serializers.ValidationError("É necessário especificar o colaborador")

        data["responsibles_hirer"] = [data["get_responsible"]]
        del data["get_responsible"]

        return super(HumanResourceSerializer, self).validate(data)


class HumanResourceItemSerializer(ServiceOrderResourceSerializer):
    spent_hours = serializers.SerializerMethodField()
    hours = serializers.SerializerMethodField()
    human_resource = ReportingRelatedField(
        source="contract",
        queryset=Contract.objects.filter(
            Q(firm__is_company_team=True) | Q(subcompany__subcompany_type="HIRING")
        ),
        required=False,
        many=False,
        extra_allowed_types=["HumanResource"],
        type_lookup_path="firm.is_company_team",
        type_lookup_map={False: "Contract", True: "HumanResource"},
        display_only="HumanResource",
    )
    firm = SerializerMethodResourceRelatedField(
        model=Firm, method_name="get_firm", read_only=True
    )
    resource_fields = serializers.SerializerMethodField(read_only=True)

    class Meta(ServiceOrderResourceSerializer.Meta):
        model = ServiceOrderResource
        fields = [
            a
            for a in ServiceOrderResourceSerializer.Meta.fields
            + [
                "hours",
                "resource_fields",
                "spent_hours",
                "human_resource",
                "firm",
            ]
            if a != "contract"
        ]

    def get_hours(self, obj):
        return minutes_to_hour_str(obj.amount)

    def get_spent_hours(self, obj):
        total_hours = 0
        for usage in obj.serviceorderresource_procedures.all():
            total_hours += usage.amount
        return minutes_to_hour_str(total_hours)

    def get_resource_fields(self, obj):
        resource_fields = copy.deepcopy(obj.resource.__dict__)
        del resource_fields["_state"]
        return resource_fields

    def get_firm(self, obj):
        if obj.contract:
            return obj.contract.firm
        return None

    def validate(self, data):
        if "hours" in self.initial_data.keys():
            data["amount"] = str_hours_to_int(self.initial_data["hours"])
        return data

    def update(self, instance, validated_data):
        if "resource_fields" in self.initial_data.keys():
            try:
                Resource.objects.filter(pk=instance.resource.pk).update(
                    **self.initial_data["resource_fields"]
                )
            except Exception:
                raise serializers.ValidationError("Não foi possível editar o Recurso.")

        return super(HumanResourceItemSerializer, self).update(instance, validated_data)

    def create(self, validated_data):
        if "resource" not in validated_data.keys():
            if "resource_fields" in self.initial_data.keys():
                try:
                    resource = Resource.objects.create(
                        **self.initial_data["resource_fields"]
                    )
                except Exception:
                    raise serializers.ValidationError(
                        "Não foi possível criar o Recurso."
                    )
            else:
                raise serializers.ValidationError("Recurso não encontrado.")

            validated_data["resource"] = resource

        return super(HumanResourceItemSerializer, self).create(validated_data)


class HumanResourceUsageSerializer(ProcedureResourceSerializer):
    _PREFETCH_RELATED_FIELDS = [
        "service_order_resource__resource",
        "service_order_resource__contract__firm",
    ]

    amount = serializers.FloatField(required=False)
    hours = serializers.SerializerMethodField()
    human_resource_item = ReportingRelatedField(
        source="service_order_resource",
        many=False,
        read_only=False,
        required=False,
        queryset=ServiceOrderResource.objects.filter(
            Q(contract__firm__is_company_team=True)
            | Q(contract__subcompany__subcompany_type="HIRING")
        ),
        extra_allowed_types=["HumanResourceItem"],
        type_lookup_path="contract.firm.is_company_team",
        type_lookup_map={
            False: "ServiceOrderResource",
            True: "HumanResourceItem",
        },
        display_only="HumanResourceItem",
    )
    resource_fields = serializers.SerializerMethodField(read_only=True)

    class Meta(ProcedureResourceSerializer.Meta):
        model = ProcedureResource
        fields = [
            a
            for a in ProcedureResourceSerializer.Meta.fields
            + [
                "hours",
                "resource_fields",
                "service_order_resource",
                "human_resource_item",
            ]
            if a != "service_order_resource"
        ]

    def get_hours(self, obj):
        return minutes_to_hour_str(obj.amount)

    def get_resource_fields(self, obj):
        resource_fields = copy.deepcopy(obj.service_order_resource.resource.__dict__)
        del resource_fields["_state"]
        return resource_fields

    def validate(self, data):
        if "hours" in self.initial_data.keys():
            data["amount"] = str_hours_to_int(self.initial_data["hours"])
        data["approval_status"] = resource_approval_status.APPROVED_APPROVAL

        return super(HumanResourceUsageSerializer, self).validate(data)


class MeasurementBulletinExportSerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    _SELECT_RELATED_FIELDS = ["created_by", "measurement_bulletin"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = MeasurementBulletinExport
        fields = [
            "uuid",
            "created_at",
            "created_by",
            "measurement_bulletin",
            "exported_file",
            "done",
            "error",
        ]

    def create(self, validated_data):
        instance = super().create(validated_data)
        generate_bulletin(str(instance.uuid))
        return instance


class FieldSurveySignatureSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["hirer", "hired", "field_survey"]

    class Meta:
        model = FieldSurveySignature
        fields = ["uuid", "signed_at", "hirer", "hired", "field_survey"]


class FieldSurveyExportSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["created_by", "field_survey"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = FieldSurveyExport
        fields = [
            "uuid",
            "created_at",
            "created_by",
            "field_survey",
            "exported_file",
            "done",
            "error",
        ]

    def create(self, validated_data):
        instance = super().create(validated_data)
        generate_survey(str(instance.uuid))
        return instance


class ContractAdditiveSerializer(serializers.ModelSerializer, EagerLoadingMixin):

    _PREFETCH_RELATED_FIELDS = ["company", "contract", "created_by"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = ContractAdditive
        fields = [
            "uuid",
            "number",
            "description",
            "notes",
            "additional_percentage",
            "old_price",
            "new_price",
            "done",
            "error",
            "created_at",
            "company",
            "created_by",
            "contract",
        ]

    def create(self, validated_data):
        if validated_data.get("new_price") is None:
            validated_data["new_price"] = round(
                validated_data.get("old_price", 0)
                * (1 + validated_data.get("additional_percentage", 0) / 100),
                4,
            )
        instance = super().create(validated_data)
        calculate_contract_additive_values(str(instance.pk))

        return instance


class ContractPeriodSerializer(serializers.ModelSerializer, EagerLoadingMixin):

    _PREFETCH_RELATED_FIELDS = ["company", "contract", "created_by", "firms"]

    uuid = serializers.UUIDField(required=False)
    total_hours = serializers.SerializerMethodField()
    period_count = serializers.SerializerMethodField()
    editable = serializers.SerializerMethodField()

    class Meta:
        model = ContractPeriod
        fields = [
            "uuid",
            "created_at",
            "created_by",
            "contract",
            "company",
            "firms",
            "hours",
            "working_schedules",
            "total_hours",
            "period_count",
            "editable",
        ]

    def get_total_hours(self, obj):
        """Calcula o total de horas baseado nos horários de working_schedules."""
        if not obj.working_schedules:
            return 0.0

        total_minutes = 0
        for item in obj.working_schedules:
            start_time = item.get("start_time", "")
            end_time = item.get("end_time", "")

            if start_time and end_time:
                try:
                    # Converte "HH:MM" para minutos
                    start_hours, start_mins = map(int, start_time.split(":"))
                    end_hours, end_mins = map(int, end_time.split(":"))

                    start_total_mins = start_hours * 60 + start_mins
                    end_total_mins = end_hours * 60 + end_mins

                    # Calcula o delta em minutos (suporta períodos que atravessam meia-noite)
                    delta_minutes = end_total_mins - start_total_mins
                    if delta_minutes < 0:
                        delta_minutes += 24 * 60
                    total_minutes += delta_minutes
                except (ValueError, AttributeError):
                    continue

        return format_minutes_decimal(total_minutes)

    def get_period_count(self, obj):
        """Calcula a quantidade de períodos."""
        if not obj.working_schedules:
            return 0
        return len(obj.working_schedules)

    def get_editable(self, obj):
        """Verifica se o período é editável baseado na existência de relatórios diários."""
        return not MultipleDailyReport.objects.filter(
            contract=obj.contract,
            firm__in=obj.firms.all(),
            created_at__gte=obj.created_at,
        ).exists()
