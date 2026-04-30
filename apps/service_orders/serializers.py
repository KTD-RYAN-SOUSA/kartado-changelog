from collections import defaultdict
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Prefetch, Q
from django.db.models.signals import post_save, pre_save
from fieldsignals.signals import post_save_changed, pre_save_changed
from fnc.mappings import get
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import (
    ResourceRelatedField,
    SerializerMethodResourceRelatedField,
)
from simple_history.utils import bulk_create_with_history

from apps.approval_flows.models import ApprovalStep
from apps.locations.models import City, Location, River
from apps.monitorings.models import (
    MonitoringCampaign,
    MonitoringPlan,
    MonitoringRecord,
    OperationalControl,
)
from apps.resources.helpers.create_contract_items import create_contract_bulletin_items
from apps.resources.models import (
    Contract,
    ContractItemPerformance,
    ContractService,
    ContractServiceBulletin,
    FieldSurvey,
)
from apps.service_orders.const.occupancy_type import OCCUPANCY_TYPE
from apps.service_orders.helpers.remove import remove_attribute_occupancy
from helpers.apps.companies import is_energy_company
from helpers.apps.contract_utils import (
    calculate_contract_prices,
    recalculate_total_price_based_on_work_day,
    set_related_firms,
)
from helpers.apps.occurrence_records import (
    add_occurrence_record_changes_debounce_data,
    validate_records,
)
from helpers.apps.performance_calculations import MeasurementBulletinScope
from helpers.apps.service_orders import (
    generate_pending_procedures_excel_file,
    handle_resources,
)
from helpers.fields import EmptyFileField, HistoricalRecordField
from helpers.files import get_url
from helpers.histories import add_history_change_reason
from helpers.mixins import EagerLoadingMixin, UUIDMixin
from helpers.permissions import PermissionManager
from helpers.signals import DisableSignals
from helpers.strings import check_image_file, minutes_to_hour_str

from ..companies.models import Company, Entity, Firm
from ..daily_reports.models import (
    DailyReportContractUsage,
    DailyReportEquipment,
    DailyReportVehicle,
    DailyReportWorker,
)
from ..occurrence_records.models import OccurrenceRecord, OccurrenceType
from ..reportings.models import Reporting
from ..users.models import User
from .const import kind_types, resource_approval_status
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
from .permissions import can_create_or_edit_action, can_edit_service_order


class ServiceOrderActionStatusSerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    _PREFETCH_RELATED_FIELDS = [
        Prefetch("companies", queryset=Company.objects.all().only("uuid")),
        "status_specs__company",
    ]

    color = serializers.CharField(read_only=True)
    order = serializers.CharField(read_only=True)

    class Meta:
        model = ServiceOrderActionStatus
        fields = [
            "uuid",
            "kind",
            "companies",
            "name",
            "order",
            "metadata",
            "color",
            "is_final",
        ]

    def create(self, validated_data):
        if "companies" not in self.initial_data:
            raise serializers.ValidationError("É necessário enviar Unidade(s)")

        companies = self.initial_data["companies"]

        # Create ServiceOrderActionStatusSpecs objects
        if not isinstance(companies, list):
            companies = [companies]

        if "order" not in self.initial_data:
            raise serializers.ValidationError("É necessário enviar Ordem")
        else:
            order = self.initial_data["order"]

        for company in companies:
            if ServiceOrderActionStatusSpecs.objects.filter(
                order=order, company_id=company["id"]
            ):
                raise serializers.ValidationError(
                    "Tipo de Status com essa Ordem e Unidade já existe"
                )

        kind_value = self.initial_data.get("kind", None)
        # Sets is_final to True for these service status types
        if kind_value in [
            "LAND_SERVICE_CONCLUSION",
            "ENVIRONMENTAL_SERVICE_CONCLUSION",
        ]:
            validated_data["is_final"] = True

        # Create object
        status = ServiceOrderActionStatus.objects.create(**validated_data)

        extra_args = {}
        if "color" in self.initial_data:
            extra_args["color"] = self.initial_data["color"]
        extra_args["order"] = order

        status_specs = [
            ServiceOrderActionStatusSpecs(
                status=status, company_id=company.get("id"), **extra_args
            )
            for company in companies
        ]

        bulk_create_with_history(status_specs, ServiceOrderActionStatusSpecs)

        return status

    def update(self, instance, validated_data):
        if "companies" in validated_data:
            validated_data.pop("companies")

        if "company_color" in self.initial_data and "color" in self.initial_data:
            company_color = self.initial_data["company_color"]
            color = self.initial_data["color"]

            try:
                status_specs = ServiceOrderActionStatusSpecs.objects.get(
                    company_id=company_color["id"], status=instance
                )
            except Exception:
                raise serializers.ValidationError(
                    "Não existe cor associada a esse Tipo e Unidade"
                )

            status_specs.color = color
            status_specs.save()

        if "company_color" in self.initial_data and "order" in self.initial_data:
            company_color = self.initial_data["company_color"]
            order = self.initial_data["order"]

            try:
                status_specs = ServiceOrderActionStatusSpecs.objects.get(
                    company_id=company_color["id"], status=instance
                )
            except Exception:
                raise serializers.ValidationError(
                    "Não existe cor associada a esse Tipo e Unidade"
                )

            status_specs.order = order
            status_specs.save()

        return super(ServiceOrderActionStatusSerializer, self).update(
            instance, validated_data
        )


class ServiceOrderActionStatusSpecsSerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    _SELECT_RELATED_FIELDS = ["company", "status"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = ServiceOrderActionStatusSpecs
        fields = ["uuid", "status", "company", "color", "order"]


class ServiceOrderWithoutMoneySerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    _PREFETCH_RELATED_FIELDS = [
        "company",
        "created_by",
        "closed_by",
        "actions",
        "actions__procedures__firm",
        "so_records",
        "so_records__operational_control",
        "so_records__monitoring_plan",
        "so_records__status__status_specs__company",
        "actions__procedures__procedure_resources",
        "actions__procedures__occurrence_records",
        "actions__procedures__occurrence_records__operational_control",
        "actions__procedures__occurrence_records__monitoring_plan",
        "administrative_informations",
        "administrative_informations__contract__firm",
        "administrative_informations__contract__unit_price_services__firms",
        "administrative_informations__contract__administration_services__firms",
        "administrative_informations__contract__performance_services__firms",
        "serviceorder_watchers",
        "serviceorder_watchers__user",
        "serviceorder_watchers__firm",
        "managers",
        "responsibles",
        "entity",
        "city",
        "location",
        "river",
        "contracts",
    ]

    uuid = serializers.UUIDField(required=False)
    actions = ResourceRelatedField(read_only=True, many=True)
    managers = ResourceRelatedField(
        read_only=False, required=False, many=True, queryset=User.objects
    )
    responsibles = ResourceRelatedField(
        read_only=False, required=False, many=True, queryset=User.objects
    )
    city = ResourceRelatedField(
        queryset=City.objects, read_only=False, many=True, required=False
    )
    location = ResourceRelatedField(
        queryset=Location.objects, read_only=False, many=True, required=False
    )
    river = ResourceRelatedField(
        queryset=River.objects, read_only=False, many=True, required=False
    )
    monitoring_plans = SerializerMethodResourceRelatedField(
        model=MonitoringPlan,
        method_name="get_monitoring_plans",
        read_only=True,
        many=True,
    )
    occurrence_record = SerializerMethodResourceRelatedField(
        model=OccurrenceRecord,
        method_name="get_occurrence_record",
        read_only=True,
        many=True,
    )
    operational_controls = SerializerMethodResourceRelatedField(
        model=OperationalControl,
        method_name="get_operational_controls",
        read_only=True,
        many=True,
    )
    firms = SerializerMethodResourceRelatedField(
        model=Firm, method_name="get_firms", read_only=True, many=True
    )
    record_status = serializers.SerializerMethodField()

    watcher_users = SerializerMethodResourceRelatedField(
        model=User, method_name="get_watcher_users", read_only=True, many=True
    )
    watcher_firms = SerializerMethodResourceRelatedField(
        model=Firm, method_name="get_watcher_firms", read_only=True, many=True
    )
    can_you_edit = serializers.SerializerMethodField(read_only=True)
    can_you_create_actions = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ServiceOrder
        fields = [
            "uuid",
            "company",
            "number",
            "actions",
            "created_by",
            "opened_at",
            "updated_at",
            "closed_at",
            "is_closed",
            "closed_description",
            "closed_by",
            "priority",
            "description",
            "occurrence_record",
            "canvas_layout",
            "monitoring_plans",
            "record_status",
            "watcher_users",
            "watcher_firms",
            "managers",
            "responsibles",
            "entity",
            "can_you_edit",
            "can_you_create_actions",
            "uf_code",
            "city",
            "location",
            "place_on_dam",
            "river",
            "other_reference",
            "kind",
            "process_type",
            "shape_file_property",
            "firms",
            "operational_controls",
            "contracts",
            "obra",
            "sequencial",
            "identificador",
            "offender_name",
            "status",
        ]
        read_only_fields = [
            "created_by",
            "number",
            "updated_at",
            "closed_by",
            "closed_at",
            "monitoring_plans",
            "operational_controls",
            "record_status",
        ]

    def get_record_status(self, obj):
        counts = {}
        specs = {}
        for record in obj.so_records.all():
            if record.status:
                counts[record.status.name] = counts.get(record.status.name, 0) + 1
                spec = next(
                    a
                    for a in list(record.status.status_specs.all())
                    if a.company == obj.company
                )
                specs[record.status.name] = {
                    "color": spec.color,
                    "order": spec.order,
                }

        final = [
            {
                "name": key,
                "color": specs[key]["color"],
                "count": value,
                "order": specs[key]["order"],
            }
            for key, value in counts.items()
        ]
        return sorted(final, key=lambda k: k["order"])

    def get_occurrence_record(self, obj):
        return list(
            set(
                [
                    a
                    for c in obj.actions.all()
                    for b in c.procedures.all()
                    for a in b.occurrence_records.all()
                ]
                + [a for a in obj.so_records.all()]
            )
        )

    def get_monitoring_plans(self, obj):
        return list(
            set(
                [
                    a.monitoring_plan
                    for c in obj.actions.all()
                    for b in c.procedures.all()
                    for a in b.occurrence_records.all()
                    if a.monitoring_plan
                ]
                + [a.monitoring_plan for a in obj.so_records.all() if a.monitoring_plan]
            )
        )

    def get_operational_controls(self, obj):
        return list(
            set(
                [
                    a.operational_control
                    for c in obj.actions.all()
                    for b in c.procedures.all()
                    for a in b.occurrence_records.all()
                    if a.operational_control
                ]
                + [
                    a.operational_control
                    for a in obj.so_records.all()
                    if a.operational_control
                ]
            )
        )

    def get_watcher_users(self, obj):
        users = [item.user for item in obj.serviceorder_watchers.all() if item.user]
        return list(set(users))

    def get_watcher_firms(self, obj):
        firms = [item.firm for item in obj.serviceorder_watchers.all() if item.firm]
        return list(set(firms))

    def get_firms(self, obj):
        return list(
            set(
                [a.firm for b in obj.actions.all() for a in b.procedures.all()]
                + [
                    a.contract.firm
                    for a in obj.administrative_informations.all()
                    if a.contract.firm
                ]
            )
        )

    def get_can_you_edit(self, obj):
        user_permissions = self.context["view"].permissions
        user_entity = self.context.get("user_entity", [])

        return can_edit_service_order(
            obj,
            self.context["request"].user,
            user_permissions,
            "ServiceOrder",
            user_entity,
        )

    def get_can_you_create_actions(self, obj):
        user_permissions = self.context["view"].permissions
        user_entity = self.context.get("user_entity", [])

        return can_create_or_edit_action(
            obj,
            self.context["request"].user,
            user_permissions,
            "ServiceOrderAction",
            "can_create",
            user_entity,
        )

    def create(self, validated_data):
        # Add entity
        if "entity" not in validated_data:
            first_firm = (
                validated_data["created_by"]
                .user_firms.filter(company=validated_data["company"])
                .first()
            )
            if first_firm:
                validated_data["entity"] = first_firm.entity

        # Check update of OccurrenceRecords
        kind_is_land = validated_data.get("kind", "") == kind_types.LAND
        can_update_records = False

        records = []
        if "add_occurrence_records" in self.initial_data:
            ids = [a["id"] for a in self.initial_data["add_occurrence_records"]]

            records = (
                OccurrenceRecord.objects.filter(pk__in=ids)
                .prefetch_related("service_orders")
                .distinct()
            )

            if all(records.values_list("is_approved")):
                validated_data = validate_records(validated_data, records, "create")

                can_update_records = True
            else:
                raise serializers.ValidationError(
                    "O serviço não pode ser criado com registros não homologados."
                )
        else:
            if kind_is_land:
                raise serializers.ValidationError(
                    "O serviço não pode ser criado sem registro."
                )

        # Create ServiceOrder
        instance = super(ServiceOrderWithoutMoneySerializer, self).create(
            validated_data
        )

        # Update records
        if can_update_records:
            for record in records:
                record.service_orders.add(instance)
                add_occurrence_record_changes_debounce_data(
                    instance=record, added_services_ids=[instance.pk]
                )

        # Create ServiceOrderActions
        request_user = self.context["request"].user
        process_type_is_land_used = get(
            "metadata.land_used_value", validated_data["company"]
        ) == validated_data.get("process_type")

        if (
            kind_is_land
            and get("get_process_type_option", validated_data["company"])(
                validated_data.get("process_type")
            )["name"]
            == OCCUPANCY_TYPE
        ):
            pass
        else:
            validated_data = remove_attribute_occupancy(validated_data)

        if kind_is_land and process_type_is_land_used:
            action_names = instance.company.metadata.get("land_action_names", [])
            if action_names:
                actions = [
                    ServiceOrderAction(
                        service_order=instance,
                        name=item.get("name", ""),
                        estimated_end_date=datetime.now()
                        + timedelta(**item.get("timedelta", {})),
                        created_by=request_user,
                        allow_forwarding=item.get("can_forward_emails", False),
                    )
                    for item in action_names
                ]
                bulk_create_with_history(actions, ServiceOrderAction)

        # Remove watcher_users and watcher_firms from data.
        watcher_users = self.initial_data.pop("watcher_users", [])
        watcher_firms = self.initial_data.pop("watcher_firms", [])

        # Create Watcher objects
        for user in watcher_users:
            ServiceOrderWatcher.objects.create(
                service_order=instance,
                user_id=user["id"],
                created_by=request_user,
            )

        for firm in watcher_firms:
            ServiceOrderWatcher.objects.create(
                service_order=instance,
                firm_id=firm["id"],
                created_by=request_user,
            )

        return instance

    def update(self, instance, validated_data):
        # Create watcher objects
        fields = ["watcher_users", "watcher_firms"]
        fields_and_names = [
            ("watcher_users", "user_id"),
            ("watcher_firms", "firm_id"),
        ]

        if set(fields).issubset(self.initial_data.keys()):
            for field, name_id in fields_and_names:
                current_watchers = instance.serviceorder_watchers.all()
                current_watchers_ids = [
                    str(item)
                    for item in current_watchers.values_list(name_id, flat=True)
                    if item
                ]

                watcher_objects = self.initial_data.pop(field, [])
                watcher_objects_ids = [item["id"] for item in watcher_objects]

                delete_ids = list(set(current_watchers_ids) - set(watcher_objects_ids))
                add_ids = list(set(watcher_objects_ids) - set(current_watchers_ids))

                name_field = name_id + "__in"
                filter_delete = {
                    name_field: delete_ids,
                    "service_order": instance,
                }

                ServiceOrderWatcher.objects.filter(**filter_delete).delete()

                for item in add_ids:
                    filter_add = {
                        name_id: item,
                        "service_order": instance,
                        "created_by": self.context["request"].user,
                    }
                    ServiceOrderWatcher.objects.create(**filter_add)

        # Check update of OccurrenceRecords
        if "add_occurrence_records" in self.initial_data:
            ids = [a["id"] for a in self.initial_data["add_occurrence_records"]]

            records = (
                OccurrenceRecord.objects.filter(pk__in=ids)
                .prefetch_related("service_orders")
                .distinct()
            )

            if all(records.values_list("is_approved")):
                # validated_data = validate_records(
                #     validated_data, records,
                # )

                for record in records:
                    record.service_orders.add(instance)
                    add_occurrence_record_changes_debounce_data(
                        instance=record, added_services_ids=[instance.pk]
                    )
            else:
                raise serializers.ValidationError("Os registros não estão homologados.")

        # Close Service Order
        if "is_closed" in validated_data:
            if validated_data["is_closed"]:
                validated_data["closed_by"] = self.context["request"].user
                instance.closed_by = validated_data["closed_by"]
                validated_data["closed_at"] = datetime.now()
                instance.closed_at = validated_data["closed_at"]
                instance.save()

        return super(ServiceOrderWithoutMoneySerializer, self).update(
            instance, validated_data
        )


class ServiceOrderSerializer(ServiceOrderWithoutMoneySerializer, EagerLoadingMixin):
    spent_price = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()

    class Meta(ServiceOrderWithoutMoneySerializer.Meta):
        fields = ServiceOrderWithoutMoneySerializer.Meta.fields + [
            "total_price",
            "spent_price",
        ]
        read_only_fields = ServiceOrderWithoutMoneySerializer.Meta.read_only_fields + [
            "total_price",
            "spent_price",
        ]

    def get_spent_price(self, obj):
        spent_price = 0
        for action in obj.actions.all():
            for procedure in action.procedures.all():
                for procedure_resource in procedure.procedure_resources.all():
                    try:
                        resource_spent_price = (
                            (procedure_resource.unit_price * procedure_resource.amount)
                            if procedure_resource.measurement_bulletin
                            else 0
                        )
                        if not isinstance(resource_spent_price, (int, float)):
                            raise Exception()
                        spent_price += resource_spent_price
                    except Exception:
                        continue

        return spent_price

    def get_total_price(self, obj):
        total_price = 0
        for administrative_information in obj.administrative_informations.all():
            try:
                total_price += administrative_information.spend_limit
            except Exception:
                continue

        return total_price


class ServiceOrderWatcherSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = [
        "service_order",
        "user",
        "firm",
        "created_by",
        "updated_by",
    ]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = ServiceOrderWatcher
        fields = [
            "uuid",
            "notification_frequency",
            "service_order",
            "user",
            "firm",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "status_email",
        ]


class ProcedureSimpleSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    uuid = serializers.UUIDField(required=False)
    responsible = ResourceRelatedField(read_only=True)

    class Meta:
        model = Procedure
        fields = [
            "uuid",
            "service_order_action_status",
            "responsible",
            "deadline",
            "done_at",
        ]


class ServiceOrderActionSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "service_order",
        "created_by",
        "firm",
        "service_order_action_status",
        "responsible",
        "parent_record",
        "service_order__entity",
        "procedures",
        "procedures__firm",
        "procedures__service_order_action_status",
        "procedures__responsible",
        "procedures__procedure_files",
        "service_order__responsibles",
        "service_order__managers",
    ]

    uuid = serializers.UUIDField(required=False)
    procedures = ResourceRelatedField(read_only=True, many=True)
    is_closed_service_order = serializers.SerializerMethodField(
        method_name="is_closed_so"
    )
    last_firm = SerializerMethodResourceRelatedField(
        model=Procedure, method_name="get_last_firm", read_only=True
    )
    last_responsible = SerializerMethodResourceRelatedField(
        model=Procedure, method_name="get_last_responsible", read_only=True
    )
    last_status = SerializerMethodResourceRelatedField(
        model=Procedure, method_name="get_last_status", read_only=True
    )
    last_procedure_description = serializers.SerializerMethodField()
    can_you_edit = serializers.SerializerMethodField(read_only=True)
    image_count = serializers.SerializerMethodField()
    file_count = serializers.SerializerMethodField()

    class Meta:
        model = ServiceOrderAction
        fields = [
            "uuid",
            "service_order",
            "name",
            "procedures",
            "service_order_action_status",
            "firm",
            "responsible",
            "created_by",
            "opened_at",
            "closed_at",
            "estimated_end_date",
            "is_closed_service_order",
            "parent_record",
            "last_firm",
            "last_responsible",
            "last_status",
            "last_procedure_description",
            "can_you_edit",
            "allow_forwarding",
            "image_count",
            "file_count",
        ]
        read_only_fields = [
            "service_order_action_status",
            "responsible",
            "created_by",
            "opened_at",
            "is_closed_service_order",
            "last_firm",
            "last_responsible",
            "last_status",
            "last_procedure_description",
            "image_count",
            "file_count",
        ]
        extra_kwargs = {"service_order": {"required": False}}

    def get_last_firm(self, obj):
        try:
            result = next(a for a in obj.procedures.all()).firm
        except Exception:
            return None
        return result

    def get_last_responsible(self, obj):
        try:
            result = next(a for a in obj.procedures.all()).responsible
        except Exception:
            return None
        return result

    def get_last_status(self, obj):
        try:
            result = next(a for a in obj.procedures.all()).service_order_action_status
        except Exception:
            return None
        return result

    def get_last_procedure_description(self, obj):
        try:
            result = next(a for a in obj.procedures.all()).to_do
        except Exception:
            return None
        return result

    def get_can_you_edit(self, obj):
        user_permissions = self.context["view"].permissions
        user_entity = self.context.get("user_entity", [])

        return can_create_or_edit_action(
            obj.service_order,
            self.context["request"].user,
            user_permissions,
            "ServiceOrderAction",
            "can_edit",
            user_entity,
        )

    def is_closed_so(self, obj):
        return obj.service_order.is_closed

    def get_file_names(self, obj):
        files = []
        for item in obj.procedures.all():
            for file in item.procedure_files.all():
                files.append(str(file.upload))
        return files

    def get_image_count(self, obj):
        image_file_names = [
            file_name
            for file_name in self.get_file_names(obj)
            if check_image_file(file_name)
        ]
        return len(image_file_names)

    def get_file_count(self, obj):
        image_file_names = [
            file_name
            for file_name in self.get_file_names(obj)
            if not check_image_file(file_name)
        ]
        return len(set(image_file_names))

    def update(self, instance, validated_data):
        procedure_count = Procedure.objects.filter(action=instance.uuid).count()
        allow_forwarding = validated_data.get("allow_forwarding", False)
        kind_is_land = (
            validated_data.get("service_order", instance.service_order).kind
            == kind_types.LAND
        )

        if procedure_count > 1:
            raise serializers.ValidationError(
                "Não é possível editar uma ação que já possui tarefas"
            )

        if allow_forwarding and not kind_is_land:
            raise serializers.ValidationError(
                "kartado.error.service_order_kind_is_not_land"
            )

        return super(ServiceOrderActionSerializer, self).update(
            instance, validated_data
        )


class ServiceOrderActionCreateSerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    uuid = serializers.UUIDField(required=False)
    occurrence_kind = serializers.CharField(required=False, write_only=True)
    occurrence_type = serializers.PrimaryKeyRelatedField(
        required=False, queryset=OccurrenceType.objects.all(), write_only=True
    )
    form_data = serializers.JSONField(required=False, write_only=True)
    to_do = serializers.CharField(required=False, write_only=True)
    deadline = serializers.DateTimeField(required=False, write_only=True)

    class Meta:
        model = ServiceOrderAction
        fields = [
            "uuid",
            "service_order",
            "name",
            "service_order_action_status",
            "firm",
            "responsible",
            "created_by",
            "opened_at",
            "closed_at",
            "estimated_end_date",
            "occurrence_kind",
            "occurrence_type",
            "form_data",
            "to_do",
            "deadline",
            "allow_forwarding",
        ]
        extra_kwargs = {"service_order": {"required": True}}

    def create(self, validated_data):
        uuid = None
        responsible = None
        status = None
        firm = None
        create_procedure = False
        fields = ["service_order_action_status", "firm"]

        if set(fields).issubset(validated_data.keys()):
            create_procedure = True

        if "firm" in validated_data.keys():
            firm = validated_data.pop("firm")

        if "service_order_action_status" in validated_data.keys():
            status = validated_data.pop("service_order_action_status")

        if "uuid" in validated_data.keys():
            uuid = validated_data.pop("uuid")

        if "responsible" in validated_data.keys():
            responsible = validated_data.pop("responsible")
        else:
            responsible = None

        if "estimated_end_date" in validated_data.keys():
            estimated_end_date = validated_data.pop("estimated_end_date")
        else:
            estimated_end_date = None

        if "allow_forwarding" in validated_data.keys():
            allow_forwarding = validated_data.pop("allow_forwarding")

        action = ServiceOrderAction.objects.create(
            uuid=uuid,
            service_order=validated_data.pop("service_order"),
            name=validated_data.pop("name"),
            service_order_action_status=status,
            firm=firm,
            responsible=responsible,
            created_by=validated_data.pop("created_by"),
            estimated_end_date=estimated_end_date,
            allow_forwarding=allow_forwarding,
        )

        if create_procedure:
            Procedure.objects.create(
                action=action,
                service_order_action_status=status,
                firm=firm,
                responsible=responsible,
                **validated_data,
            )

        return action


class ProcedureSerializer(serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin):
    _SELECT_RELATED_FIELDS = [
        "firm",
        "action",
        "action__service_order",
        "service_order_action_status",
        "responsible",
        "procedure_previous",
        "procedure_next",
        "created_by",
        "occurrence_type",
    ]
    _PREFETCH_RELATED_FIELDS = [
        "resources",
        "procedure_files",
        "occurrence_records",
        "occurrence_type",
        "monitoring_records",
        "monitoring_campaigns",
    ]

    uuid = serializers.UUIDField(required=False)
    resources = ResourceRelatedField(
        read_only=True,
        many=True,  # necessary for M2M fields & reverse FK fields
    )
    procedure_files = ResourceRelatedField(
        read_only=False,
        queryset=ProcedureFile.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        required=False,
    )
    occurrence_records = ResourceRelatedField(
        many=True,
        read_only=False,
        required=False,
        queryset=OccurrenceRecord.objects,
    )
    is_closed_service_order = serializers.SerializerMethodField(
        method_name="is_closed_so"
    )
    service_order = SerializerMethodResourceRelatedField(
        model=ServiceOrder, method_name="get_service_order", read_only=True
    )
    monitoring_records = ResourceRelatedField(
        read_only=False,
        many=True,
        queryset=MonitoringRecord.objects,
        required=False,
    )
    monitoring_campaigns = ResourceRelatedField(
        read_only=False,
        many=True,
        queryset=MonitoringCampaign.objects,
        required=False,
    )
    new_service_order_status = ResourceRelatedField(
        queryset=ServiceOrderActionStatus.objects,
        required=False,
        write_only=True,
    )

    class Meta:
        model = Procedure
        fields = [
            "uuid",
            "action",
            "occurrence_kind",
            "occurrence_type",
            "service_order_action_status",
            "firm",
            "responsible",
            "procedure_previous",
            "form_data",
            "to_do",
            "occurrence_records",
            "resources",
            "created_by",
            "created_at",
            "deadline",
            "done_at",
            "procedure_files",
            "procedure_next",
            "is_closed_service_order",
            "service_order",
            "monitoring_records",
            "monitoring_campaigns",
            "forward_to_judiciary",
            "new_service_order_status",
        ]
        read_only_fields = [
            "created_by",
            "created_at",
            "updated_at",
            "procedure_files",
            "is_closed_service_order",
            "procedure_previous",
            "procedure_next",
            "service_order",
            "monitoring_records",
            "monitoring_campaigns",
        ]

    def is_closed_so(self, obj):
        return obj.action.service_order.is_closed

    def get_service_order(self, obj):
        return obj.action.service_order

    def update(self, instance, validated_data):

        record_ids = []

        if "occurrence_records" in self.initial_data:
            record_ids = [
                item["id"] for item in self.initial_data["occurrence_records"]
            ]
        else:
            record_ids = [
                str(a)
                for a in instance.occurrence_records.all().values_list(
                    "uuid", flat=True
                )
            ]

        if record_ids:
            instance.occurrence_records.set(record_ids)

        return super(ProcedureSerializer, self).update(instance, validated_data)

    def validate(self, attrs):
        action = attrs.get("action", None)
        if (
            action
            and attrs.get("forward_to_judiciary", None)
            and not action.allow_forwarding
        ):
            raise serializers.ValidationError(
                "kartado.error.forward_to_judiciary.required"
            )
        return super().validate(attrs)

    def create(self, validated_data):
        # Auto-fill firm
        responsible = validated_data.get("responsible", None)
        firm = validated_data.get("firm", None)
        if responsible and not firm:
            try:
                validated_data["firm"] = Firm.objects.filter(
                    users=responsible,
                    company=validated_data["action"].service_order.company,
                ).first()
                if not validated_data["firm"]:
                    raise Exception()
            except Exception:
                raise serializers.ValidationError(
                    "O responsável especificado não está associado a nenhuma Equipe."
                )
        if not responsible and not firm:
            raise serializers.ValidationError(
                "É necessário uma Equipe ou um Responsável."
            )

        record_ids = []
        if "occurrence_records" in self.initial_data:
            record_ids = [
                item["id"] for item in self.initial_data["occurrence_records"]
            ]

        if record_ids:
            validated_data["occurrence_records"] = OccurrenceRecord.objects.filter(
                pk__in=record_ids
            ).distinct()

        new_service_order_status = validated_data.get("new_service_order_status", None)

        if new_service_order_status:
            user = self.context["request"].user
            new_service_order_status = validated_data.pop("new_service_order_status")
            service_order = validated_data["action"].service_order
            company_ids = service_order.company.uuid

            # Permission - Homologadores
            permission_homologator = PermissionManager(
                user=user,
                company_ids=company_ids,
                model="OccurrenceRecord",
            )
            permission_homologator = permission_homologator.has_permission(
                "can_approve"
            )
            # Permission - Gestores de Entrega e Tarefa de um Serviço OR Para Responsáveis Técnicos do Serviço
            permission_manager = (
                user in service_order.responsibles.all()
                or user in service_order.managers.all()
            )

            if validated_data["action"].procedures.exists():
                raise serializers.ValidationError(
                    "Só é possível manipular status de serviço na criação das primeiras tarefas dentro de uma entrega."
                )
            if not permission_homologator and not permission_manager:
                raise serializers.ValidationError(
                    "Usuário não tem permissão para manipular status de serviço dentro de uma entrega."
                )

            # Gets the path that relates the procedure to the serviceOrder
            # serviço (serviceOrder) --> entrega (action) --> tarefa (procedure)
            service_order.status = new_service_order_status
            service_order.save()

        return super(ProcedureSerializer, self).create(validated_data)


class ProcedureFileSerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _SELECT_RELATED_FIELDS = ["created_by"]
    _PREFETCH_RELATED_FIELDS = ["procedures"]

    uuid = serializers.UUIDField(required=False)
    upload = EmptyFileField()
    upload_url = serializers.SerializerMethodField()
    file_type = serializers.SerializerMethodField()

    procedure = SerializerMethodResourceRelatedField(
        model=Procedure, method_name="get_procedure", read_only=True
    )

    class Meta:
        model = ProcedureFile
        fields = [
            "uuid",
            "procedures",
            "procedure",
            "description",
            "upload",
            "upload_url",
            "uploaded_at",
            "datetime",
            "created_by",
            "md5",
            "file_type",
        ]
        read_only_fields = ["uploaded_at", "created_by"]

    def get_upload_url(self, obj):
        return {}
        # kept this field here to maintain compatibility

    def get_file_type(self, obj):
        if check_image_file(obj.upload.name):
            return "image"
        return "file"

    def get_procedure(self, obj):
        if len(obj.procedures.all()):
            return obj.procedures.all()[0]
        else:
            return None

    def validate(self, data):
        if "procedures" not in data and "procedure" in self.initial_data:
            try:
                procedure = Procedure.objects.get(
                    uuid=self.initial_data["procedure"]["id"]
                )
            except Exception:
                raise serializers.ValidationError("Tarefa não encontrada")

            data["procedures"] = [procedure]

        return data


class ProcedureFileObjectSerializer(ProcedureFileSerializer):
    def get_upload_url(self, obj):
        return get_url(obj)


class ProcedureResourceWithoutMoneySerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _PREFETCH_RELATED_FIELDS = [
        "procedure",
        "procedure__action",
        "procedure__action__service_order",
        "service_order_resource",
        "service_order_resource__contract",
        "service_order_resource__entity",
        "resource",
        "created_by",
        "firm",
        "measurement_bulletin",
        "approved_by",
        "service_order",
        "reporting",
        "history_procedure_resources",
    ]

    amount = serializers.FloatField()
    uuid = serializers.UUIDField(required=False)
    is_closed_service_order = serializers.SerializerMethodField(
        method_name="is_closed_so"
    )
    reporting = ResourceRelatedField(
        queryset=Reporting.objects,
        many=False,
        required=False,
        error_messages={
            "required": "This field is required.",
            "does_not_exist": "kartado.error.reporting.not_found",
            "incorrect_type": "Incorrect type. Expected pk value, received {data_type}.",
        },
    )
    contract = SerializerMethodResourceRelatedField(
        model=Contract, method_name="get_contract", read_only=True
    )
    entity = SerializerMethodResourceRelatedField(
        model=Entity, method_name="get_entity", read_only=True
    )

    history_change_reason = serializers.SerializerMethodField()

    executed_at = serializers.SerializerMethodField()

    class Meta:
        model = ProcedureResource
        fields = [
            "uuid",
            "procedure",
            "amount",
            "creation_date",
            "approval_status",
            "approval_date",
            "approved_by",
            "service_order_resource",
            "firm",
            "resource",
            "measurement_bulletin",
            "created_by",
            "service_order",
            "is_closed_service_order",
            "reporting",
            "contract",
            "entity",
            "history_change_reason",
            "executed_at",
        ]
        read_only_fields = [
            "approval_status",
            "approval_date",
            "approved_by",
            "firm",
            "created_by",
            "is_closed_service_order",
            "executed_at",
        ]
        # Add service_order_resource here to use serializer is_valid
        # method when passing just service_order_resource_id
        extra_kwargs = {"service_order_resource": {"required": False}}

    def is_closed_so(self, obj):
        if obj.service_order:
            return obj.service_order.is_closed
        else:
            return None

    def get_contract(self, obj):
        return obj.service_order_resource.contract

    def get_entity(self, obj):
        if obj.service_order_resource:
            return obj.service_order_resource.entity
        return None

    def validate(self, data):
        # Use if "row" to use excel_import validation
        if "service_order_resource_id" in self.initial_data.keys():
            return data

        if "service_order_resource" not in data.keys():
            raise serializers.ValidationError(
                "É necessário especificar um ServiceOrderResource"
            )
        service_order_resource = data["service_order_resource"]

        if service_order_resource is not None:
            data["service_order_resource"] = service_order_resource
            data["resource"] = service_order_resource.resource
            data["unit_price"] = service_order_resource.unit_price
            data["total_price"] = data["amount"] * data["unit_price"]

        return data

    def create(self, validated_data):
        instance = super().create(validated_data)
        add_history_change_reason(instance, self.initial_data)
        return instance

    def update(self, instance, validated_data):
        if (
            instance.approval_status == resource_approval_status.APPROVED_APPROVAL
            or instance.approval_status == resource_approval_status.DENIED_APPROVAL
        ) and (instance.amount != validated_data.get("amount", instance.amount)):
            raise serializers.ValidationError(
                "Não é possível alterar um recurso que já tenha sido aprovado ou reprovado"
            )

        new_instance = super(ProcedureResourceWithoutMoneySerializer, self).update(
            instance, validated_data
        )

        add_history_change_reason(new_instance, self.initial_data)

        return new_instance

    def get_history_change_reason(self, obj):
        try:
            return obj.history_procedure_resources.first().history_change_reason
        except Exception:
            return None

    def get_executed_at(self, obj):
        return obj.reporting.executed_at if obj.reporting else None


class ProcedureResourceSerializer(ProcedureResourceWithoutMoneySerializer):
    history = serializers.SerializerMethodField()

    class Meta(ProcedureResourceWithoutMoneySerializer.Meta):
        fields = ProcedureResourceWithoutMoneySerializer.Meta.fields + [
            "unit_price",
            "total_price",
            "history",
        ]

    def get_history(self, obj):
        history_list = []
        for history in obj.history_procedure_resources.all():
            history_dict = {
                field_name: field_value
                for field_name, field_value in history.__dict__.items()
                if field_name != "_state"
            }
            history_list.append(history_dict)
        return history_list


class ServiceOrderResourceWithoutMoneySerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    _PREFETCH_RELATED_FIELDS = [
        "serviceorderresource_procedures",
        "additional_control_model",
        "resource_contract_unit_price_items__contract_item_unit_price_services__firms",
        "resource_contract_administration_items__contract_item_administration_services__firms",
        "contract",
        "created_by",
        "resource",
        "contract__firm",
        "entity",
    ]

    uuid = serializers.UUIDField(required=False)
    additional_control_model = ResourceRelatedField(
        queryset=AdditionalControl.objects,
        many=False,
        required=False,
        allow_null=False,
    )

    contract_service_firms = SerializerMethodResourceRelatedField(
        model=Firm, method_name="get_contract_service_firms", read_only=True, many=True
    )
    name = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()

    class Meta:
        model = ServiceOrderResource
        fields = [
            "uuid",
            "contract",
            "resource",
            "amount",
            "remaining_amount",
            "creation_date",
            "created_by",
            "resource_kind",
            "entity",
            "additional_control",
            "additional_control_model",
            "effective_date",
            "contract_service_firms",
            "name",
            "unit",
        ]
        read_only_fields = ["creation_date", "created_by"]
        extra_kwargs = {"firm": {"required": True}}

    def get_contract_service_firms(self, obj):
        firms = []
        for contract_item_unit_price in obj.resource_contract_unit_price_items.all():
            for (
                contract_service
            ) in contract_item_unit_price.contract_item_unit_price_services.all():
                firms += list(contract_service.firms.all())
        for (
            contract_item_administration
        ) in obj.resource_contract_administration_items.all():
            for (
                contract_service
            ) in (
                contract_item_administration.contract_item_administration_services.all()
            ):
                firms += list(contract_service.firms.all())

        return list(set(firms))

    def get_name(self, obj):
        if obj.resource:
            return obj.resource.name
        return ""

    def get_unit(self, obj):
        if obj.resource:
            return obj.resource.unit
        return ""


class ServiceOrderResourceSerializer(
    ServiceOrderResourceWithoutMoneySerializer, EagerLoadingMixin
):
    reason = serializers.CharField(required=False, write_only=True)
    pending_amount = serializers.SerializerMethodField()
    pending_price = serializers.SerializerMethodField()

    class Meta(ServiceOrderResourceWithoutMoneySerializer.Meta):
        fields = ServiceOrderResourceWithoutMoneySerializer.Meta.fields + [
            "reason",
            "pending_amount",
            "pending_price",
            "unit_price",
            "used_price",
        ]

    def get_pending_amount(self, obj):
        pending_amount = 0

        for procedure_resource in obj.serviceorderresource_procedures.all():
            try:
                resource_pending_amount = (
                    procedure_resource.amount
                    if procedure_resource.approval_status
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
        pending_price = 0

        for procedure_resource in obj.serviceorderresource_procedures.all():
            try:
                resource_pending_price = (
                    (procedure_resource.unit_price * procedure_resource.amount)
                    if procedure_resource.approval_status
                    == resource_approval_status.WAITING_APPROVAL
                    else 0
                )
                if not isinstance(resource_pending_price, (int, float)):
                    raise Exception()
                pending_price += resource_pending_price
            except Exception:
                continue

        return pending_price

    @transaction.atomic
    def create(self, validated_data):
        instance = super().create(validated_data)
        handle_resources(self, instance)

        return instance

    @transaction.atomic
    def update(self, instance, validated_data):
        change_procedure_resource_fields = False

        if instance.unit_price != validated_data.get("unit_price", instance.unit_price):
            change_procedure_resource_fields = True

        if instance.amount != validated_data.get("amount", instance.amount):
            if "remaining_amount" not in validated_data:
                validated_data["remaining_amount"] = instance.remaining_amount
            validated_data["remaining_amount"] += (
                validated_data.get("amount", instance.amount) - instance.amount
            )

        # Change reason update
        reason = ""
        if "reason" in validated_data.keys():
            reason = validated_data.pop("reason")
        instance._change_reason = reason

        instance = super(ServiceOrderResourceSerializer, self).update(
            instance, validated_data
        )

        handle_resources(self, instance)

        if change_procedure_resource_fields:
            procedure_resources = ProcedureResource.objects.filter(
                creation_date__gte=instance.effective_date,
                measurement_bulletin=None,
                service_order_resource=instance,
            ).select_related("measurement_bulletin")

            """
            Removed re-serialization and added the changes
            used in validate function of ProcedureResource
            """
            for item in procedure_resources:
                item.resource = instance.resource
                item.save()

        return instance


class ServiceOrderResourceObjectSerializer(ServiceOrderResourceSerializer):
    history = HistoricalRecordField(read_only=True)
    performance_total_price = 0.0

    class Meta(ServiceOrderResourceSerializer.Meta):
        model = ServiceOrderResource
        fields = ServiceOrderResourceSerializer.Meta.fields + ["history"]


class MeasurementBulletinSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        Prefetch("bulletin_workers", queryset=DailyReportWorker.objects.all()),
        Prefetch("bulletin_equipments", queryset=DailyReportEquipment.objects.all()),
        Prefetch("bulletin_vehicles", queryset=DailyReportVehicle.objects.all()),
        "bulletin_surveys",
        "firm",
        "firm_manager",
        "created_by",
        "contract",
        "approval_step",
        "contract__firm",
        "contract__subcompany",
        Prefetch(
            "contract__performance_services",
            queryset=ContractService.objects.all().prefetch_related(
                Prefetch(
                    "contract_item_performance",
                    queryset=ContractItemPerformance.objects.all(),
                )
            ),
        ),
        Prefetch(
            "contract__contract_services_bulletins",
            queryset=ContractServiceBulletin.objects.all(),
        ),
        "contract__surveys_roads",
        "contract__performance_services__contract_item_performance",
        # "contract__contract_services_bulletins__contract_item_performance",
        "bulletin_resources",
        Prefetch("related_firms", queryset=Firm.objects.all().only("uuid", "name")),
    ]

    uuid = serializers.UUIDField(required=False)
    bulletin_resources = ResourceRelatedField(
        queryset=ProcedureResource.objects, many=True, required=False
    )
    bulletin_workers = ResourceRelatedField(
        queryset=DailyReportWorker.objects, many=True, required=False
    )
    bulletin_equipments = ResourceRelatedField(
        queryset=DailyReportEquipment.objects, many=True, required=False
    )
    bulletin_vehicles = ResourceRelatedField(
        queryset=DailyReportVehicle.objects, many=True, required=False
    )
    bulletin_surveys = ResourceRelatedField(
        queryset=FieldSurvey.objects, many=True, required=False
    )

    contract = ResourceRelatedField(
        queryset=Contract.objects, many=False, read_only=False, required=False
    )

    related_firms = ResourceRelatedField(many=True, read_only=True, required=False)

    average_grade_percent = serializers.SerializerMethodField()
    performance_total_price = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()
    performance_provisioned_price = serializers.SerializerMethodField()
    hired_name = serializers.SerializerMethodField()
    hired_address = serializers.SerializerMethodField()

    class Meta:
        performance_total_price = 0.0
        average_grade_percent = 0.0
        model = MeasurementBulletin
        fields = [
            "uuid",
            "number",
            "identification_bulletin",
            "firm",
            "firm_manager",
            "creation_date",
            "measurement_date",
            "created_by",
            "bulletin_resources",
            "contract",
            "extra_info",
            "description",
            "approval_step",
            "editable",
            "period_starts_at",
            "period_ends_at",
            "work_day",
            "bulletin_workers",
            "bulletin_vehicles",
            "bulletin_equipments",
            "bulletin_surveys",
            "average_grade_percent",
            "performance_total_price",
            "performance_provisioned_price",
            "total_price",
            "hired_name",
            "hired_address",
            "is_processing",
            "related_firms",
        ]
        read_only_fields = [
            "creation_date",
            "created_by",
            "number",
            "firm_manager",
            "average_grade_percent",
            "performance_total_price",
            "performance_provisioned_price",
            "is_processing",
            "related_firms",
        ]
        extra_kwargs = {"firm": {"required": False}}

    def _cache_performance_items_retrieve(self):
        if not hasattr(self, "_cache_performance_items"):
            calculation_list = defaultdict(list)
            request = self.context.get("request", None)
            if not request:
                self._cache_performance_items = calculation_list
                return self._cache_performance_items
            company = request.query_params.get("company", None)
            if not company:
                self._cache_performance_items = calculation_list
                return self._cache_performance_items

            middle_queryset = list(
                ContractServiceBulletin.objects.filter(
                    (
                        Q(contract__firm__company_id=company)
                        | Q(contract__subcompany__company_id=company)
                    ),
                    contract_item_performance__isnull=False,
                )
                .prefetch_related("contract_item_performance", "measurement_bulletins")
                .distinct()
            )
            for item in middle_queryset:
                calculation_list[item].extend(
                    (
                        item.contract_item_performance.all(),
                        item.measurement_bulletins.all(),
                    ),
                )
            self._cache_performance_items = calculation_list
        return self._cache_performance_items

    def get_performance_provisioned_price(self, obj):
        item_list = self._cache_performance_items_retrieve()
        try:
            sum_value = (
                sum([k.price for k, (_, v) in item_list.items() if obj in v])
                / obj.contract.performance_months
            )
            return sum_value
        except Exception:
            return 0.0

    def get_average_grade_percent(self, obj):
        """
        PERFORMS THE CALCULUS "D" FROM THE ISSUE KTD-1156
        """
        item_list = self._cache_performance_items_retrieve()
        measurement_bulletin_scope = MeasurementBulletinScope(
            obj.contract, measurement_bulletin=obj, item_list=item_list
        )
        measurement_bulletin_scope.calculate_mb_average_grade_percent()
        self.Meta.average_grade_percent = (
            measurement_bulletin_scope.average_grade_percent
        )
        return measurement_bulletin_scope.average_grade_percent

    def get_performance_total_price(self, obj):
        """
        PERFORMS THE CALCULUS "H" FROM THE ISSUE KTD-1156
        """
        performance_total_price = 0.0
        item_list = self._cache_performance_items_retrieve()
        for contract_service, (_, mb_objects) in item_list.items():
            if obj not in mb_objects:
                continue
            try:
                performance_total_price += (
                    contract_service.price / obj.contract.performance_months
                ) * self.Meta.average_grade_percent
            except Exception:
                pass
        self.Meta.performance_total_price = performance_total_price
        return performance_total_price

    def get_total_price(self, obj):
        """
        PERFORMS THE CALCULUS "I" FROM THE ISSUE KTD-1156
        """
        if not obj.total_price:
            obj.total_price = 0.0
        return obj.total_price + self.Meta.performance_total_price

    def get_hired_name(self, obj):
        if obj.contract and obj.contract.subcompany:
            return obj.contract.subcompany.name
        elif obj.contract and obj.contract.firm:
            return obj.contract.firm.name
        else:
            return ""

    def get_hired_address(self, obj):
        if obj.contract and obj.contract.subcompany:
            return obj.contract.subcompany.office
        elif obj.contract and obj.contract.firm:
            return obj.contract.firm.street_address
        else:
            return "Não informado"

    def validate(self, data):
        # save the original data to check which fields has been changed
        if self.instance:
            self.instance.original_bulletin_surveys = (
                self.instance.bulletin_surveys.all()
            )
            self.instance.original_bulletin_resources = (
                self.instance.bulletin_resources.all()
            )
        relations_to_check = [
            "bulletin_resources",
            "bulletin_workers",
            "bulletin_equipments",
            "bulletin_vehicles",
            # "bulletin_surveys",
        ]

        model_list = {
            "bulletin_resources": (ProcedureResource, ["measurement_bulletin"]),
            "bulletin_workers": (
                DailyReportWorker,
                [
                    "measurement_bulletin",
                    "contract_item_administration",
                    "contract_item_administration__resource",
                ],
            ),
            "bulletin_equipments": (
                DailyReportEquipment,
                [
                    "measurement_bulletin",
                    "contract_item_administration",
                    "contract_item_administration__resource",
                ],
            ),
            "bulletin_vehicles": (
                DailyReportVehicle,
                [
                    "measurement_bulletin",
                    "contract_item_administration",
                    "contract_item_administration__resource",
                ],
            ),
        }
        request_method = self.context["request"].method
        total_price = 0
        for relation in relations_to_check:
            if relation in data:
                if isinstance(data[relation], list):
                    (model_class, prefetch_kwargs) = model_list.get(relation)

                    if model_class:
                        ids = [item.uuid for item in data[relation]]
                        resources = model_class.objects.filter(
                            uuid__in=ids
                        ).prefetch_related(*prefetch_kwargs)
                else:
                    resources = data[relation]
                for resource in resources:
                    if (
                        resource.measurement_bulletin_id is not None
                        and self.instance
                        and str(resource.measurement_bulletin_id)
                        != str(self.instance.uuid)
                    ):
                        raise serializers.ValidationError(
                            "Um ou mais recursos já fazem parte de um boletim de medição"
                        )
                    if (
                        resource.approval_status
                        == resource_approval_status.WAITING_APPROVAL
                    ):
                        raise serializers.ValidationError(
                            "Recursos pendentes não podem ser adicionados a um boletim de medição"
                        )
                    if request_method == "POST":
                        if (
                            isinstance(resource, ProcedureResource)
                            and resource.approval_status
                            == resource_approval_status.APPROVED_APPROVAL
                        ):
                            total_price += resource.total_price
                        elif (
                            not isinstance(resource, (FieldSurvey, ProcedureResource))
                            and resource.approval_status
                            == resource_approval_status.APPROVED_APPROVAL
                        ):
                            unit_price = (
                                resource.unit_price
                                if resource.unit_price is not None
                                else resource.contract_item_administration.resource.unit_price
                            )
                            total_price += (resource.amount * unit_price) / data[
                                "work_day"
                            ]
        if request_method == "POST":
            data["total_price"] = total_price

        return data

    def update(self, instance, validated_data):
        contract = instance.contract
        if contract.firm and contract.firm.company:
            company = contract.firm.company
        elif contract.subcompany and contract.subcompany.company:
            company = contract.subcompany.company
        editable = validated_data.get("editable", instance.editable)
        if not editable:
            raise serializers.ValidationError(
                "Esse Boletim de Medição não pode ser editado."
            )
        has_to_create_contract_items = bool(
            validated_data.get("bulletin_surveys", [])
            and not instance.bulletin_surveys.exists()
        )
        validated_data["is_processing"] = True
        removed_resources = self.initial_data.get("removed_resources", [])
        removed_workers = self.initial_data.get("removed_workers", [])
        removed_vehicles = self.initial_data.get("removed_vehicles", [])
        removed_equipments = self.initial_data.get("removed_equipments", [])

        if removed_resources:
            if is_energy_company(company):
                for item in removed_resources:
                    resource = ProcedureResource.objects.filter(uuid=item["id"]).first()
                    if resource:
                        resource.measurement_bulletin = None
                        with DisableSignals(
                            disabled_signals=[
                                pre_save_changed,
                                pre_save,
                                post_save_changed,
                            ]
                        ):
                            resource.save()
            else:
                resources = ProcedureResource.objects.filter(
                    uuid__in=[item["id"] for item in removed_resources]
                )
                resources.update(measurement_bulletin=None)

        removed_workers_instances = None
        if removed_workers:
            removed_workers_instances = DailyReportWorker.objects.filter(
                uuid__in=[item["id"] for item in removed_workers]
            )
            removed_workers_instances.update(measurement_bulletin=None, total_price=0)

        removed_vehicles_instances = None
        if removed_vehicles:
            removed_vehicles_instances = DailyReportVehicle.objects.filter(
                uuid__in=[item["id"] for item in removed_vehicles]
            )
            removed_vehicles_instances.update(measurement_bulletin=None, total_price=0)

        removed_equipments_instances = None
        if removed_equipments:
            removed_equipments_instances = DailyReportEquipment.objects.filter(
                uuid__in=[item["id"] for item in removed_equipments]
            )
            removed_equipments_instances.update(
                measurement_bulletin=None, total_price=0
            )

        # Bulk update DailyReportContractUsage to clear measurement_bulletin for removed items
        if removed_workers or removed_vehicles or removed_equipments:
            q_filters = Q()
            if removed_workers_instances:
                q_filters |= Q(worker__in=removed_workers_instances)
            if removed_vehicles_instances:
                q_filters |= Q(vehicle__in=removed_vehicles_instances)
            if removed_equipments_instances:
                q_filters |= Q(equipment__in=removed_equipments_instances)

            if q_filters:
                DailyReportContractUsage.objects.filter(q_filters).update(
                    measurement_bulletin=None
                )

        relations_to_check = [
            "bulletin_resources",
            "bulletin_workers",
            "bulletin_equipments",
            "bulletin_vehicles",
        ]
        model_list = {
            "bulletin_resources": (ProcedureResource, ["measurement_bulletin"]),
            "bulletin_workers": (
                DailyReportWorker,
                [
                    "measurement_bulletin",
                    "contract_item_administration",
                    "contract_item_administration__resource",
                ],
            ),
            "bulletin_equipments": (
                DailyReportEquipment,
                [
                    "measurement_bulletin",
                    "contract_item_administration",
                    "contract_item_administration__resource",
                ],
            ),
            "bulletin_vehicles": (
                DailyReportVehicle,
                [
                    "measurement_bulletin",
                    "contract_item_administration",
                    "contract_item_administration__resource",
                ],
            ),
        }
        original_work_day = instance.work_day
        total_price = 0

        # Lists to collect resources that need measurement_bulletin update
        workers_to_update = []
        vehicles_to_update = []
        equipments_to_update = []

        for relation in relations_to_check:
            if relation in validated_data:
                if isinstance(validated_data[relation], list):
                    (model_class, prefetch_kwargs) = model_list.get(relation)

                    if model_class:
                        ids = [item.uuid for item in validated_data[relation]]
                        resources = model_class.objects.filter(
                            uuid__in=ids
                        ).prefetch_related(*prefetch_kwargs)
                else:
                    resources = validated_data[relation]
                for resource in resources:
                    if not isinstance(resource, (FieldSurvey, ProcedureResource)):
                        if (
                            resource.approval_status
                            == resource_approval_status.APPROVED_APPROVAL
                        ):
                            unit_price = (
                                resource.unit_price
                                if resource.unit_price is not None
                                else resource.contract_item_administration.resource.unit_price
                            )
                            total_price += (
                                resource.amount * unit_price
                            ) / validated_data["work_day"]
                            if str(resource.measurement_bulletin_id) != str(
                                instance.uuid
                            ):
                                resource.measurement_bulletin = instance

                                if isinstance(resource, DailyReportWorker):
                                    workers_to_update.append(resource)
                                elif isinstance(resource, DailyReportVehicle):
                                    vehicles_to_update.append(resource)
                                elif isinstance(resource, DailyReportEquipment):
                                    equipments_to_update.append(resource)

                                with DisableSignals(disabled_signals=[post_save]):
                                    resource.save()
                    elif (
                        isinstance(resource, ProcedureResource)
                        and resource.approval_status
                        == resource_approval_status.APPROVED_APPROVAL
                    ):
                        total_price += resource.total_price
                        if str(resource.measurement_bulletin_id) != str(instance.uuid):
                            resource.measurement_bulletin = instance
                            if is_energy_company(company):
                                with DisableSignals(
                                    disabled_signals=[
                                        pre_save,
                                        post_save_changed,
                                    ]
                                ):
                                    resource.save()
                            else:
                                with DisableSignals(
                                    disabled_signals=[
                                        post_save,
                                        pre_save,
                                        post_save_changed,
                                    ]
                                ):
                                    resource.save()

        # Bulk update DailyReportContractUsage for updated resources
        if workers_to_update or vehicles_to_update or equipments_to_update:
            q_filters = Q()
            if workers_to_update:
                q_filters |= Q(worker__in=workers_to_update)
            if vehicles_to_update:
                q_filters |= Q(vehicle__in=vehicles_to_update)
            if equipments_to_update:
                q_filters |= Q(equipment__in=equipments_to_update)

            if q_filters:
                DailyReportContractUsage.objects.filter(q_filters).update(
                    measurement_bulletin=instance
                )

        validated_data["total_price"] = total_price

        instance = super(MeasurementBulletinSerializer, self).update(
            instance, validated_data
        )

        if has_to_create_contract_items:
            performance_services = contract.performance_services.all().prefetch_related(
                "contract_item_performance"
            )
            for contract_service in performance_services:
                create_contract_bulletin_items(
                    contract_service, contract, measurement_bulletins=[instance]
                )

        if (
            "work_day" in validated_data
            and original_work_day != validated_data["work_day"]
        ):
            recalculate_total_price_based_on_work_day(
                instance, resource_approval_status
            )

        contract_uuid = str(contract.uuid)
        calculate_contract_prices(contract_uuid)

        set_related_firms(str(instance.uuid))

        return instance

    def create(self, validated_data):
        bulletin_resources = validated_data.pop("bulletin_resources", [])
        bulletin_workers = validated_data.pop("bulletin_workers", [])
        bulletin_vehicles = validated_data.pop("bulletin_vehicles", [])
        bulletin_equipments = validated_data.pop("bulletin_equipments", [])
        bulletin_surveys = validated_data.pop("bulletin_surveys", [])

        contract = validated_data["contract"]

        try:
            if contract.firm and contract.firm.company:
                company = contract.firm.company
            elif contract.subcompany and contract.subcompany.company:
                company = contract.subcompany.company
            approval_step = ApprovalStep.objects.filter(
                approval_flow__company=company,
                approval_flow__target_model="service_orders.MeasurementBulletin",
                previous_steps__isnull=True,
            ).first()
            validated_data["approval_step"] = approval_step
        except Exception:
            pass

        validated_data["extra_info"] = {
            "accounting_classification": contract.extra_info.get(
                "accounting_classification", ""
            )
        }
        validated_data["is_processing"] = True

        extra_fields = {}
        if contract.firm is not None:
            extra_fields["firm"] = contract.firm
            extra_fields["firm_manager"] = contract.firm.manager

        bulletin = MeasurementBulletin.objects.create(**extra_fields, **validated_data)

        for resource in bulletin_resources:
            resource.measurement_bulletin = bulletin
            resource.save()

        workers_list = []
        for worker in bulletin_workers:
            worker.measurement_bulletin = bulletin
            worker.save()
            workers_list.append(worker)

        vehicles_list = []
        for vehicle in bulletin_vehicles:
            vehicle.measurement_bulletin = bulletin
            vehicle.save()
            vehicles_list.append(vehicle)

        equipments_list = []
        for equipment in bulletin_equipments:
            equipment.measurement_bulletin = bulletin
            equipment.save()
            equipments_list.append(equipment)

        # Bulk update DailyReportContractUsage for all workers, vehicles and equipment
        if workers_list or vehicles_list or equipments_list:
            q_filters = Q()
            if workers_list:
                q_filters |= Q(worker__in=workers_list)
            if vehicles_list:
                q_filters |= Q(vehicle__in=vehicles_list)
            if equipments_list:
                q_filters |= Q(equipment__in=equipments_list)

            if q_filters:
                DailyReportContractUsage.objects.filter(q_filters).update(
                    measurement_bulletin=bulletin
                )

        for survey in bulletin_surveys:
            survey.measurement_bulletin = bulletin
            survey.save()

        if bulletin_surveys:
            performance_services = contract.performance_services.all().prefetch_related(
                "contract_item_performance"
            )
            for contract_service in performance_services:
                create_contract_bulletin_items(
                    contract_service, contract, measurement_bulletins=[bulletin]
                )

        calculate_contract_prices(str(contract.uuid))

        set_related_firms(str(bulletin.uuid))

        return bulletin


class MeasurementBulletinObjectSerializer(MeasurementBulletinSerializer):
    history = HistoricalRecordField(read_only=True)

    class Meta(MeasurementBulletinSerializer.Meta):
        fields = MeasurementBulletinSerializer.Meta.fields + ["history"]


class AdministrativeInformationWithoutMoneySerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    _SELECT_RELATED_FIELDS = [
        "service_order",
        "contract",
        "responsible",
        "created_by",
    ]

    _PREFETCH_RELATED_FIELDS = [
        "contract__resources__serviceorderresource_procedures__procedure__action__service_order",
        "contract__resources__serviceorderresource_procedures__service_order",
        "contract__firm",
        "contract__subcompany",
    ]

    uuid = serializers.UUIDField(required=False)

    is_closed_service_order = serializers.SerializerMethodField(
        method_name="is_closed_so"
    )

    spent_hours = serializers.SerializerMethodField()
    contract = ResourceRelatedField(
        many=False,
        read_only=False,
        required=False,
        queryset=Contract.objects.filter(
            Q(firm__is_company_team=False) | Q(subcompany__subcompany_type="HIRED")
        ),
    )
    human_resource = ResourceRelatedField(
        source="contract",
        many=False,
        read_only=False,
        required=False,
        queryset=Contract.objects.filter(
            Q(firm__is_company_team=True) | Q(subcompany__subcompany_type="HIRING")
        ),
    )

    class Meta:
        model = AdministrativeInformation
        fields = [
            "uuid",
            "created_at",
            "created_by",
            "service_order",
            "contract",
            "human_resource",
            "responsible",
            "spend_limit",
            "is_closed_service_order",
            "spent_hours",
        ]
        read_only_fields = [
            "created_at",
            "created_by",
            "is_closed_service_order",
        ]
        extra_kwargs = {"firm": {"required": True}}

    def is_closed_so(self, obj):
        return obj.service_order.is_closed

    def get_spent_hours(self, obj):
        total_hours = 0

        firms = []

        for contract_service in obj.contract.unit_price_services.all():
            for firm in contract_service.firms.all():
                firms.append(firm)
        for contract_service in obj.contract.administration_services.all():
            for firm in contract_service.firms.all():
                firms.append(firm)
        for contract_service in obj.contract.performance_services.all():
            for firm in contract_service.firms.all():
                firms.append(firm)

        if not any([a.is_company_team for a in firms]):
            return None

        for resource in obj.contract.resources.all():
            for usage in [
                a
                for a in resource.serviceorderresource_procedures.all()
                if a.service_order == obj.service_order
            ]:
                total_hours += usage.amount

        return minutes_to_hour_str(total_hours)

    def validate(self, data):
        if ("service_order" not in data.keys()) and (
            ("contract" not in data.keys()) or ("human_resource" not in data.keys())
        ):
            raise serializers.ValidationError(
                "É necessário especificar um Contract/Human Resource e uma Ordem de Serviço"
            )

        return data

    def create(self, validated_data):
        if "contract" in validated_data.keys():
            contract = validated_data["contract"]
        else:
            contract = validated_data["human_resource"]

        already_exists = AdministrativeInformation.objects.filter(
            contract=contract, service_order=validated_data["service_order"]
        )

        if already_exists.exists():
            raise serializers.ValidationError(
                "É permitido apenas uma entrada de Informações Administrativas por Ordem de Serviço por Contrato"
            )

        return super(AdministrativeInformationWithoutMoneySerializer, self).create(
            validated_data
        )


class AdministrativeInformationSerializer(
    AdministrativeInformationWithoutMoneySerializer
):
    spent_price = serializers.SerializerMethodField()

    class Meta(AdministrativeInformationWithoutMoneySerializer.Meta):
        fields = AdministrativeInformationWithoutMoneySerializer.Meta.fields + [
            "spent_price"
        ]

    def get_spent_price(self, obj):
        spent_price = 0
        # this is a bit ugly but it's the way I found to avoid query explosion
        for resource in obj.contract.resources.all():
            for procedure_resource in resource.serviceorderresource_procedures.all():
                if procedure_resource.service_order == obj.service_order:
                    try:
                        resource_spent_price = (
                            (procedure_resource.unit_price * procedure_resource.amount)
                            if procedure_resource.measurement_bulletin
                            else 0
                        )
                        if not isinstance(resource_spent_price, (int, float)):
                            raise Exception()
                        spent_price += resource_spent_price
                    except Exception:
                        continue

        return spent_price


class AdditionalControlSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "company",
        "created_by",
        "service_order_resources",
    ]
    uuid = serializers.UUIDField(required=False)
    has_service_order_resource = serializers.SerializerMethodField(read_only=True)

    def get_has_service_order_resource(self, obj):
        return obj.service_order_resources.count() > 0

    class Meta:
        model = AdditionalControl
        fields = [
            "uuid",
            "company",
            "name",
            "is_active",
            "created_at",
            "created_by",
            "has_service_order_resource",
        ]


class PendingProceduresExportSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["created_by", "company"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = PendingProceduresExport
        fields = [
            "uuid",
            "created_at",
            "created_by",
            "exported_file",
            "company",
            "filters",
            "done",
            "error",
        ]

    def create(self, validated_data):
        instance = super().create(validated_data)

        try:
            permissions = self.context.get("view").permissions.get_permission(
                "can_view_pending_procedures"
            )[0]
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.pending_procedures.permission_not_found"
            )

        generate_pending_procedures_excel_file(
            str(instance.pk),
            str(instance.created_by.uuid),
            permissions,
        )
        return instance

    def validate(self, attrs):
        filters_is_filled = "filters" in attrs or (
            self.instance and self.instance.filters
        )
        if not filters_is_filled:
            raise serializers.ValidationError(
                "kartado.error.pending_procedures_export.cannot_apply_malformed_filters"
            )

        return super().validate(attrs)
