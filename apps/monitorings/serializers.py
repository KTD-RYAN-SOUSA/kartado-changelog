from django.db.models import Q
from django.utils import timezone
from fnc.mappings import get
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import (
    ResourceRelatedField,
    SerializerMethodResourceRelatedField,
)

from apps.companies.models import Firm
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
from apps.occurrence_records.models import OccurrenceType
from apps.resources.models import Contract
from apps.service_orders.const import status_types
from apps.service_orders.models import Procedure, ServiceOrderActionStatusSpecs
from apps.users.models import User
from helpers.fields import ReportingRelatedField
from helpers.forms import get_form_metadata
from helpers.mixins import EagerLoadingMixin, UUIDMixin

from .notifications import monitoring_cycle_email


class MonitoringPlanSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company", "created_by", "status"]
    _PREFETCH_RELATED_FIELDS = ["responsibles"]

    uuid = serializers.UUIDField(required=False)
    responsibles = ResourceRelatedField(
        queryset=User.objects, required=False, many=True
    )
    status_kind = serializers.SerializerMethodField()
    responsibles_cycle = SerializerMethodResourceRelatedField(
        model=User, method_name="get_responsibles_cycle", read_only=True, many=True
    )

    class Meta:
        model = MonitoringPlan
        fields = [
            "uuid",
            "number",
            "company",
            "responsibles",
            "specificity",
            "description",
            "legal_requirement",
            "created_by",
            "created_at",
            "status",
            "status_kind",
            "responsibles_cycle",
            "is_not_notified",
        ]
        read_only_fields = ["created_by", "created_at"]

    def get_responsibles_cycle(self, obj):
        cycle = obj.cycles_plan.filter(
            start_date__date__lte=timezone.now().date(),
            end_date__date__gte=timezone.now().date(),
        ).first()
        if cycle:
            return cycle.responsibles.all()
        return []

    def get_status_kind(self, obj):
        return get("status.metadata.status", obj, default="")

    def create(self, validated_data):
        # Add initial status
        try:
            status = (
                ServiceOrderActionStatusSpecs.objects.filter(
                    company=validated_data["company"],
                    status__kind=status_types.MONITORING_STATUS,
                )
                .order_by("order")[0]
                .status
            )
        except Exception:
            pass
        else:
            validated_data["status"] = status

        # Remove M2Ms from data
        responsibles = validated_data.pop("responsibles", [])

        # Create object
        monitoring = MonitoringPlan.objects.create(**validated_data)

        # Create responsibles relationships
        monitoring.responsibles.add(*responsibles)

        return monitoring


class MonitoringCycleSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["status", "created_by", "monitoring_plan"]
    _PREFETCH_RELATED_FIELDS = [
        "approvers",
        "executers",
        "evaluators",
        "viewers",
        "contracts",
        "contracts__firm",
        "responsibles",
    ]

    uuid = serializers.UUIDField(required=False)
    executers = ResourceRelatedField(queryset=Firm.objects, required=False, many=True)
    evaluators = ResourceRelatedField(queryset=Firm.objects, required=False, many=True)
    viewers = ResourceRelatedField(queryset=Firm.objects, required=False, many=True)
    approvers = ResourceRelatedField(queryset=Firm.objects, required=False, many=True)
    contracts = ReportingRelatedField(
        queryset=Contract.objects.filter(
            Q(firm__is_company_team=False) | Q(subcompany__subcompany_type="HIRED")
        ),
        required=False,
        many=True,
        extra_allowed_types=["HumanResource"],
        type_lookup_path="firm.is_company_team",
        type_lookup_map={False: "Contract", True: "HumanResource"},
        display_only="Contract",
    )
    human_resources = ReportingRelatedField(
        source="contracts",
        queryset=Contract.objects.filter(
            Q(firm__is_company_team=True) | Q(subcompany__subcompany_type="HIRING")
        ),
        required=False,
        many=True,
        extra_allowed_types=["HumanResource"],
        type_lookup_path="firm.is_company_team",
        type_lookup_map={False: "Contract", True: "HumanResource"},
        display_only="HumanResource",
    )
    responsibles = ResourceRelatedField(
        queryset=User.objects, required=False, many=True
    )

    class Meta:
        model = MonitoringCycle
        fields = [
            "uuid",
            "number",
            "start_date",
            "end_date",
            "status",
            "monitoring_plan",
            "executers",
            "evaluators",
            "viewers",
            "approvers",
            "created_at",
            "created_by",
            "contracts",
            "responsibles",
            "human_resources",
            "email_created",
        ]
        read_only_fields = ["created_by", "created_at"]

    def validate(self, attrs):
        # Validate cycles dates
        try:
            monitoring_plan = attrs["monitoring_plan"]
            start_date = attrs["start_date"]
            end_date = attrs["end_date"]
            edit_uuid = [item for item in [attrs.get("uuid", "")] if item]
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.monitoring_cycle.invalid_data"
            )

        cycles = MonitoringCycle.objects.filter(
            monitoring_plan=monitoring_plan,
            start_date__date__lte=end_date.date(),
            end_date__date__gte=start_date.date(),
        ).exclude(uuid__in=edit_uuid)
        if cycles.exists():
            raise serializers.ValidationError(
                "kartado.error.monitoring_cycle.invalid_dates"
            )

        return super(MonitoringCycleSerializer, self).validate(attrs)

    def create(self, validated_data):
        # Create object
        monitoring_cycle = super(MonitoringCycleSerializer, self).create(validated_data)

        is_active = (
            monitoring_cycle.start_date.date() <= timezone.now().date()
            and monitoring_cycle.end_date.date() >= timezone.now().date()
        )
        if is_active:
            monitoring_cycle_email(monitoring_cycle)
            monitoring_cycle.email_created = True
            monitoring_cycle.save()

        return monitoring_cycle

    def update(self, instance, validated_data):
        # Send email if responsibles have changed
        responsibles_changed = not all(
            [
                item in instance.responsibles.all()
                for item in validated_data.get("responsibles", [])
            ]
        )

        # Update object
        monitoring_cycle = super(MonitoringCycleSerializer, self).update(
            instance, validated_data
        )

        is_active = (
            monitoring_cycle.start_date.date() <= timezone.now().date()
            and monitoring_cycle.end_date.date() >= timezone.now().date()
        )
        if is_active and (responsibles_changed or not monitoring_cycle.email_created):
            monitoring_cycle_email(monitoring_cycle)
            monitoring_cycle.email_created = True
            monitoring_cycle.save()

        return monitoring_cycle


class MonitoringFrequencySerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = [
        "monitoring_plan",
        "parameter_group",
        "created_by",
    ]

    _PREFETCH_RELATED_FIELDS = [
        "monitoring_points",
        "parameter_group__monitoring_plan",
    ]

    uuid = serializers.UUIDField(required=False)

    monitoring_points = ResourceRelatedField(
        queryset=MonitoringPoint.objects, required=False, many=True
    )

    parameter_group = ReportingRelatedField(
        queryset=OccurrenceType.objects.filter(monitoring_plan__isnull=False),
        required=True,
        many=False,
        extra_allowed_types=["ParameterGroup"],
        type_lookup_path="monitoring_plan__isnull",
        type_lookup_map={False: "ParameterGroup", True: "OccurrenceType"},
    )

    class Meta:
        model = MonitoringFrequency
        fields = [
            "uuid",
            "created_by",
            "created_at",
            "updated_at",
            "monitoring_plan",
            "monitoring_points",
            "start_date",
            "end_date",
            "frequency",
            "parameter_group",
            "active",
        ]


class MonitoringPointSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["city", "location", "river", "created_by"]
    _PREFETCH_RELATED_FIELDS = ["monitoring_plan"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = MonitoringPoint
        fields = [
            "uuid",
            "created_by",
            "created_at",
            "updated_at",
            "code",
            "uf_code",
            "city",
            "location",
            "river",
            "place_on_dam",
            "coordinates",
            "monitoring_plan",
            "coverage_area",
            "segment",
            "description",
            "depth",
            "position",
            "stratification",
            "zone",
            "active",
        ]


class MonitoringPointGeoSerializer(GeoFeatureModelSerializer, EagerLoadingMixin):
    class Meta:
        model = MonitoringPoint
        geo_field = "coordinates"
        fields = ["uuid", "code"]


class MonitoringCampaignSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["monitoring_plan", "firm", "status", "created_by"]
    _PREFETCH_RELATED_FIELDS = ["frequencies", "procedures"]

    uuid = serializers.UUIDField(required=False)
    frequencies = ResourceRelatedField(
        queryset=MonitoringFrequency.objects, required=False, many=True
    )
    procedures = ResourceRelatedField(
        queryset=Procedure.objects, required=False, many=True
    )

    class Meta:
        model = MonitoringCampaign
        fields = [
            "uuid",
            "start_date",
            "end_date",
            "monitoring_plan",
            "firm",
            "frequencies",
            "status",
            "procedures",
            "created_by",
        ]

    def validate(self, data):
        """
        Don't allow creating a campaign when there's an existing campaign with
        one of the provided frequencies, in a conflicting date range
        """

        conflict = MonitoringCampaign.objects.filter(
            frequencies__in=data["frequencies"],
            start_date__lte=data["end_date"],
            end_date__gte=data["start_date"],
        )

        if conflict.exists():
            raise serializers.ValidationError(
                "Uma ou mais coletas selecionadas já foram agendadas em uma campanha."
            )

        return data


class MonitoringCollectSerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _SELECT_RELATED_FIELDS = [
        "company",
        "created_by",
        "parameter_group",
        "responsible",
        "monitoring_frequency",
        "monitoring_point",
        "occurrence_record",
    ]

    uuid = serializers.UUIDField(required=False)
    parameter_group = ReportingRelatedField(
        queryset=OccurrenceType.objects.filter(monitoring_plan__isnull=False),
        required=True,
        many=False,
        extra_allowed_types=["ParameterGroup"],
        type_lookup_path="monitoring_plan__isnull",
        type_lookup_map={False: "ParameterGroup", True: "OccurrenceType"},
    )
    form_fields = serializers.SerializerMethodField()
    filled_fields = serializers.SerializerMethodField()

    class Meta:
        model = MonitoringCollect
        fields = [
            "uuid",
            "company",
            "number",
            "datetime",
            "created_at",
            "updated_at",
            "created_by",
            "responsible",
            "parameter_group",
            "dict_form_data",
            "array_form_data",
            "monitoring_frequency",
            "monitoring_point",
            "occurrence_record",
            "form_fields",
            "filled_fields",
        ]
        read_only_fields = ["created_at", "updated_at", "created_by", "number"]

    def get_form_fields(self, obj):
        len_array_form_data = len(obj.array_form_data)
        fields = len(get("parameter_group.form_fields.fields", obj, default=[]))
        extra_fields = len(
            get(
                "parameter_group.repetition.form_fields.extra_fields",
                obj,
                default=[],
            )
        )
        repetition = get("parameter_group.repetition.limit", obj, default=1)
        total = repetition * fields + extra_fields
        if len_array_form_data > 0:
            return len_array_form_data * total
        return total

    def get_filled_fields(self, obj):
        num = 0
        if obj.array_form_data:
            for item in obj.array_form_data:
                fields = get("fields", item, default=[])
                num += sum([len(a.keys()) for a in fields if isinstance(a, dict)])
            return num
        elif obj.dict_form_data:
            return len(obj.dict_form_data.keys())
        return num


class MonitoringRecordSerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _SELECT_RELATED_FIELDS = [
        "created_by",
        "parameter_group",
        "monitoring_campaign",
        "monitoring_frequency",
        "monitoring_point",
    ]

    _PREFETCH_RELATED_FIELDS = [
        "procedures",
        "parameter_group__monitoring_plan",
        "company",
        "file",
    ]

    uuid = serializers.UUIDField(required=False)
    file = ResourceRelatedField(many=True, required=False, read_only=True)
    parameter_group = ReportingRelatedField(
        queryset=OccurrenceType.objects.filter(monitoring_plan__isnull=False),
        required=True,
        many=False,
        extra_allowed_types=["ParameterGroup"],
        type_lookup_path="monitoring_plan__isnull",
        type_lookup_map={False: "ParameterGroup", True: "OccurrenceType"},
    )
    form_fields = serializers.SerializerMethodField()
    filled_fields = serializers.SerializerMethodField()
    procedures = ResourceRelatedField(
        queryset=Procedure.objects, required=False, many=True
    )

    class Meta:
        model = MonitoringRecord
        fields = [
            "uuid",
            "company",
            "datetime",
            "created_at",
            "updated_at",
            "editable",
            "created_by",
            "number",
            "parameter_group",
            "form_data",
            "form_metadata",
            "monitoring_campaign",
            "monitoring_frequency",
            "monitoring_point",
            "form_fields",
            "filled_fields",
            "procedures",
            "file",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
            "editable",
            "created_by",
            "number",
            "file",
        ]

    def get_form_fields(self, obj):
        try:
            return len(obj.parameter_group.form_fields["fields"])
        except Exception:
            return 0

    def get_filled_fields(self, obj):
        try:
            return len(obj.form_data.keys())
        except Exception:
            return 0

    def create(self, validated_data):
        # Auto fill form_metadata
        if (
            "parameter_group" in validated_data
            and validated_data["parameter_group"] is not None
        ):
            form_data = validated_data.get("form_data", {})
            validated_data["form_metadata"] = get_form_metadata(
                form_data,
                validated_data["parameter_group"],
                validated_data.get("form_metadata", {}),
            )

        return super(MonitoringRecordSerializer, self).create(validated_data)

    def update(self, instance, validated_data):
        # Auto fill form_metadata
        parameter_group = (
            validated_data.get("parameter_group", False) or instance.parameter_group
        )
        form_metadata = (
            validated_data.get("form_metadata", {}) or instance.form_metadata
        )
        if parameter_group:
            validated_data["form_metadata"] = get_form_metadata(
                validated_data.get("form_data", {}),
                parameter_group,
                form_metadata,
                instance.form_data,
            )

        return super(MonitoringRecordSerializer, self).update(instance, validated_data)

    def validate(self, data):
        """
        When a monitoring_campaign is provided, check that the datetime is within
        the campaign's start and end range
        """
        if not data["datetime"]:
            raise serializers.ValidationError(
                "É necessário especificar uma data para a coleta"
            )

        if data["monitoring_campaign"]:
            campaign = data["monitoring_campaign"]
            if (
                data["datetime"] < campaign.start_date
                or data["datetime"] > campaign.end_date
            ):
                raise serializers.ValidationError(
                    "A data da coleta deve estar contida no período da campanha"
                )

        return data


class MonitoringScheduleSerializer(serializers.Serializer):

    uuid = serializers.UUIDField(required=False)
    datetime = serializers.DateTimeField(required=False)
    created_at = serializers.DateTimeField(required=False)
    updated_at = serializers.DateTimeField(required=False)
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    frequency = serializers.CharField(required=False)
    editable = serializers.BooleanField(required=False)
    created_by = serializers.ResourceRelatedField(
        required=False, read_only=True, model=User
    )
    number = serializers.CharField(required=False)
    parameter_group = ReportingRelatedField(
        required=False,
        read_only=True,
        model=OccurrenceType,
        many=False,
        extra_allowed_types=["ParameterGroup"],
        type_lookup_path="monitoring_plan__isnull",
        type_lookup_map={False: "ParameterGroup", True: "OccurrenceType"},
    )
    form_data = serializers.JSONField(required=False)
    monitoring_campaign = serializers.ResourceRelatedField(
        required=False, read_only=True, model=MonitoringCampaign
    )
    monitoring_frequency = serializers.ResourceRelatedField(
        required=False, read_only=True, model=MonitoringFrequency
    )
    monitoring_point = serializers.ResourceRelatedField(
        required=False, read_only=True, model=MonitoringPoint
    )
    form_fields = serializers.IntegerField(required=False)
    filled_fields = serializers.IntegerField(required=False)


class OperationalControlSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["contract", "firm", "responsible"]
    _PREFETCH_RELATED_FIELDS = [
        "operational_control_cycles",
        "files",
        "config_occurrence_types",
    ]

    uuid = serializers.UUIDField(required=False)
    files = ResourceRelatedField(many=True, required=False, read_only=True)
    operational_control_cycles = ResourceRelatedField(
        queryset=OperationalCycle.objects, required=False, many=True
    )
    records_amount = serializers.SerializerMethodField()
    company_id = serializers.SerializerMethodField()

    class Meta:
        model = OperationalControl
        fields = [
            "uuid",
            "contract",
            "firm",
            "responsible",
            "kind",
            "metadata",
            "show_map",
            "map_default_filters",
            "show_materials",
            "files",
            "records_amount",
            "company_id",
            "operational_control_cycles",
            "config_occurrence_types",
        ]

    def get_records_amount(self, obj):
        return obj.op_control_records.count()

    def get_company_id(self, obj):
        return obj.get_company_id

    def validate(self, attrs):
        # Validate cycles
        if "cycles" in self.initial_data:
            dates = [
                (item.get("start_date"), item.get("end_date"))
                for item in self.initial_data["cycles"]
            ]
            for start_date, end_date in dates:
                if not start_date or not end_date:
                    raise serializers.ValidationError(
                        "kartado.error.operational_cycle.has_no_date"
                    )
                if start_date >= end_date:
                    raise serializers.ValidationError(
                        "kartado.error.operational_cycle.start_date_greater"
                    )

            dates.sort(key=lambda date: date[0])
            for i in range(len(dates) - 1):
                # if end_date is greater than next start_date
                if dates[i][1] > dates[i + 1][0]:
                    raise serializers.ValidationError(
                        "kartado.error.operational_cycle.invalid_dates"
                    )

        return super(OperationalControlSerializer, self).validate(attrs)

    def update(self, instance, validated_data):
        # Update cycles
        if "cycles" in self.initial_data:
            all_cycles = instance.operational_control_cycles.all()
            current_objs = all_cycles.values_list("uuid", flat=True)
            current_objs_ids = [str(item) for item in current_objs if item]
            objects = self.initial_data.pop("cycles", [])
            keep_objects_ids = [item["uuid"] for item in objects if "uuid" in item]
            delete_ids = list(set(current_objs_ids) - set(keep_objects_ids))

            # Remove cycles
            if delete_ids:
                OperationalCycle.objects.filter(pk__in=delete_ids).delete()

            for obj in objects:
                creators = get("relationships.creators.data", obj, default=[])
                viewers = get("relationships.viewers.data", obj, default=[])
                if "uuid" not in obj:
                    # Create cycles
                    add_obj = {
                        "start_date": obj.get("start_date"),
                        "end_date": obj.get("end_date"),
                        "operational_control": instance,
                        "created_by": self.context["request"].user,
                    }
                    cycle = OperationalCycle.objects.create(**add_obj)
                    if creators:
                        cycle.creators.add(*creators)
                    if viewers:
                        cycle.viewers.add(*viewers)
                else:
                    # Update cycles
                    cycle = OperationalCycle.objects.filter(pk=obj.get("uuid")).first()
                    if cycle:
                        cycle.start_date = obj.get("start_date")
                        cycle.end_date = obj.get("end_date")
                        cycle.save()
                        cycle.creators.set(creators, clear=True)
                        cycle.viewers.set(viewers, clear=True)

        return super(OperationalControlSerializer, self).update(
            instance, validated_data
        )

    def create(self, validated_data):
        # Remove cycles from data
        cycles = self.initial_data.pop("cycles", [])

        config_occ_types = validated_data.pop("config_occurrence_types", [])

        # Create object
        operational = OperationalControl.objects.create(**validated_data)

        # Add config OccurrenceTypes
        operational.config_occurrence_types.set(config_occ_types)

        # Create cycles
        for obj in cycles:
            creators = get("relationships.creators.data", obj, default=[])
            viewers = get("relationships.viewers.data", obj, default=[])
            filter_add = {
                "start_date": obj.get("start_date"),
                "end_date": obj.get("end_date"),
                "operational_control": operational,
                "created_by": self.context["request"].user,
            }
            cycle = OperationalCycle.objects.create(**filter_add)
            if creators:
                cycle.creators.add(*creators)
            if viewers:
                cycle.viewers.add(*viewers)

        return operational


class OperationalCycleSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["created_by", "operational_control"]
    _PREFETCH_RELATED_FIELDS = ["creators", "viewers"]

    uuid = serializers.UUIDField(required=False)
    creators = ResourceRelatedField(queryset=Firm.objects, required=False, many=True)
    viewers = ResourceRelatedField(queryset=Firm.objects, required=False, many=True)

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
        read_only_fields = ["created_by", "created_at"]


class MaterialItemSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = [
        "company",
        "operational_control",
        "created_by",
        "entity",
    ]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = MaterialItem
        fields = [
            "uuid",
            "company",
            "operational_control",
            "created_by",
            "name",
            "amount",
            "unit_price",
            "used_price",
            "remaining_amount",
            "creation_date",
            "effective_date",
            "unit",
            "is_extra",
            "resource_kind",
            "entity",
            "additional_control",
        ]
        read_only_fields = ["created_by"]


class MaterialUsageSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = [
        "material_item",
        "occurrence_record",
        "firm",
        "created_by",
        "approved_by",
    ]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = MaterialUsage
        fields = [
            "uuid",
            "material_item",
            "occurrence_record",
            "firm",
            "created_by",
            "approved_by",
            "amount",
            "unit_price",
            "total_price",
            "creation_date",
            "approval_status",
            "approval_date",
        ]
        read_only_fields = ["created_by"]

    def validate(self, data):
        if "material_item" not in data.keys():
            raise serializers.ValidationError(
                "É necessário especificar um insumo a ser consumido"
            )
        material_item = data["material_item"]

        if material_item:
            data["unit_price"] = material_item.unit_price
            data["total_price"] = data["amount"] * data["unit_price"]

        return data

    def update(self, instance, validated_data):
        if "amount" in validated_data and validated_data["amount"] != instance.amount:
            changed_amount = validated_data["amount"] - instance.amount
            changed_total_price = changed_amount * instance.material_item.unit_price

            material_item = instance.material_item
            material_item.remaining_amount -= changed_amount
            material_item.used_price += changed_total_price
            material_item.save()

        instance_updated = super(MaterialUsageSerializer, self).update(
            instance, validated_data
        )

        return instance_updated

    def create(self, validated_data):
        instance = super(MaterialUsageSerializer, self).create(validated_data)

        material_item = instance.material_item
        material_item.remaining_amount -= instance.amount
        material_item.used_price += instance.total_price
        material_item.save()

        return instance
