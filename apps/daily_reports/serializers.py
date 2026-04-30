import logging
from collections import OrderedDict
from datetime import timedelta

import sentry_sdk
from dateutil.relativedelta import relativedelta
from django.contrib.admin.utils import flatten
from django.db import IntegrityError, transaction
from django.db.models import F, Prefetch, Q, Sum
from django.db.models.signals import post_init, post_save, pre_init
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import (
    ResourceRelatedField,
    SerializerMethodResourceRelatedField,
)
from simple_history.utils import bulk_create_with_history

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Entity, SubCompany
from apps.daily_reports.asynchronous import process_contract_usage_for_report
from apps.daily_reports.const import export_formats
from apps.daily_reports.services import (
    send_daily_report_same_db_to_n8n,
    send_daily_report_to_n8n,
)
from apps.reportings.models import Reporting
from apps.reportings.serializers import ReportingFileSerializer
from apps.service_orders.models import MeasurementBulletin, ProcedureResource
from apps.services.models import ServiceUsage
from apps.users.models import User, UserSignature
from apps.users.serializers import UserSignatureSerializer
from helpers.apps.approval_flow import is_currently_responsible
from helpers.apps.daily_reports import (
    ActiveFieldModelSerializer,
    days_with_progress,
    determine_report_type_and_field,
    generate_exported_file,
    get_km_intervals_field,
)
from helpers.fields import (
    EmptyFileField,
    ForgivingTimeField,
    OptimizedSerializerMethodResourceRelatedField,
)
from helpers.files import get_rdo_file_url
from helpers.histories import add_history_change_reason
from helpers.mixins import EagerLoadingMixin, UUIDMixin
from helpers.serializers import get_field_if_provided_or_present
from helpers.signals import DisableSignals
from helpers.strings import get_obj_from_path, to_snake_case

from .helpers import get_board_item_name, get_reporting_date_lookup
from .models import (
    DailyReport,
    DailyReportContractUsage,
    DailyReportEquipment,
    DailyReportExport,
    DailyReportExternalTeam,
    DailyReportOccurrence,
    DailyReportRelation,
    DailyReportResource,
    DailyReportSignaling,
    DailyReportVehicle,
    DailyReportWorker,
    MultipleDailyReport,
    MultipleDailyReportFile,
    MultipleDailyReportSignature,
    ProductionGoal,
)
from .signals import (
    auto_create_contract_usage_and_fill_contract_prices_for_equipment,
    auto_create_contract_usage_and_fill_contract_prices_for_vehicle,
    auto_create_contract_usage_and_fill_contract_prices_for_worker,
)


class BaseDailyReportSerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _PREFETCH_RELATED_FIELDS = [
        "reporting_files",
        "company",
        "created_by",
        "responsible",
        "approval_step",
        "inspector",
        "contract",
    ]

    CONDITIONAL_FIELDS = (
        "morning_weather",
        "afternoon_weather",
        "night_weather",
        "morning_conditions",
        "afternoon_conditions",
        "night_conditions",
        "morning_start",
        "morning_end",
        "afternoon_start",
        "afternoon_end",
        "night_start",
        "night_end",
    )

    uuid = serializers.UUIDField(required=False)

    class Meta:
        fields = [
            "uuid",
            "company",
            "date",
            "day_without_work",
            "created_by",
            "responsible",
            "created_at",
            "inspector",
            "notes",
            "number",
            "use_reporting_resources",
            "editable",
            # Weather
            "morning_weather",
            "afternoon_weather",
            "night_weather",
            # Conditions
            "morning_conditions",
            "afternoon_conditions",
            "night_conditions",
            # Duration
            "morning_start",
            "morning_end",
            "afternoon_start",
            "afternoon_end",
            "night_start",
            "night_end",
            # Approval
            "approval_step",
            # M2M
            "reporting_files",
            # Header data
            "header_info",
            "contract",
        ]
        read_only_fields = ["created_by", "created_at", "number"]

    def handle_model_fields(self, validated_data):
        """
        Handles manipulation of models related to DailyReport
        """

        FIELD_SERIALIZERS = [
            ("daily_report_workers", DailyReportWorkerSerializer),
            ("daily_report_external_teams", DailyReportExternalTeamSerializer),
            ("daily_report_equipment", DailyReportEquipmentSerializer),
            ("daily_report_vehicles", DailyReportVehicleSerializer),
            ("daily_report_signaling", DailyReportSignalingSerializer),
            ("daily_report_occurrences", DailyReportOccurrenceSerializer),
            ("reporting_files", ReportingFileSerializer),
            ("production_goals", ProductionGoalSerializer),
        ]

        # If set to use Reporting resources, ignore that model field
        if not validated_data.get("use_reporting_resources", False):
            FIELD_SERIALIZERS.append(
                ("daily_report_resources", DailyReportResourceSerializer)
            )

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

        for model_field, model_serializer in possible_fields:
            if model_field in self.initial_data:
                for item in self.initial_data[model_field]:
                    # Inject company into item (from relationships)
                    item["company"] = self.initial_data["company"]

                    # Inject firm if not provided for item
                    if "firm" not in item and "firm" in self.initial_data:
                        item["firm"] = self.initial_data["firm"]

                    # Relationship status check
                    active = None
                    if "active" in item:
                        active = item.pop("active")

                        if type(active) is not bool:
                            raise serializers.ValidationError(
                                "kartado.error.base_daily_report.active_field_of_{}_needs_to_be_a_boolean".format(
                                    model_field
                                )
                            )

                    daily_planned_amount = None
                    if (
                        "daily_planned_amount" in item
                        and "production_goals" in model_field
                    ):
                        daily_planned_amount = item.pop("daily_planned_amount")

                        try:
                            daily_planned_amount = float(daily_planned_amount)
                        except ValueError:
                            raise serializers.ValidationError(
                                "kartado.error.base_daily_report.daily_planned_amount_field_of_{}_needs_to_be_a_float".format(
                                    model_field
                                )
                            )

                    # If editing require an id
                    is_editing = model_field.split("_")[0] == "edit"
                    if is_editing and "id" in item:
                        item_id = item.pop("id")
                    elif is_editing and "id" not in item:
                        raise serializers.ValidationError(
                            "kartado.error.base_daily_report.inform_id_when_using_edit_fields"
                        )
                    else:
                        item_id = None

                    if is_editing:
                        # Determine the model
                        model = model_serializer.Meta.model

                        # Try to get the instance
                        try:
                            instance = model.objects.get(pk=item_id)
                        except model.DoesNotExist:
                            raise serializers.ValidationError(
                                "kartado.error.base_daily_report.invalid_id_on_{}".format(
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
                        serializer = model_serializer(data=item)

                    # If valid, defer the save until everything else is valid
                    # If not valid, errors are returned normally as JSON
                    if serializer.is_valid(raise_exception=True):
                        deferred_serializers.append(
                            (serializer, active, item_id, daily_planned_amount)
                        )

        return deferred_serializers

    def handle_deferred_serializers(self, report, deferred_serializers):
        """
        Receives the deferred model field serializers, creates or updates
        each instance and relate them to the provided instance if the "item_id"
        in deferred_serializers is None
        """

        # Serializers that should be ignored when defining DailyReportRelation
        DAILY_REPORT_RELATION_EXEMPT = [ReportingFileSerializer]

        MODEL_MAPPING = {
            DailyReportWorker: ("worker", "DailyReportWorker"),
            DailyReportExternalTeam: ("external_team", "DailyReportExternalTeam"),
            DailyReportEquipment: ("equipment", "DailyReportEquipment"),
            DailyReportVehicle: ("vehicle", "DailyReportVehicle"),
            DailyReportSignaling: ("signaling", "DailyReportSignaling"),
            DailyReportOccurrence: ("occurrence", "DailyReportOccurrence"),
            DailyReportResource: ("resource", "DailyReportResource"),
            ProductionGoal: ("production_goal", "ProductionGoal"),
        }
        # Get report relation field and report type
        report_field, report_type = determine_report_type_and_field(report)
        relations_to_create = []

        # Temporarily disconnect post_save signals that create DailyReportContractUsage
        # since we handle it manually in bulk after all saves
        post_save.disconnect(
            auto_create_contract_usage_and_fill_contract_prices_for_worker,
            sender=DailyReportWorker,
        )
        post_save.disconnect(
            auto_create_contract_usage_and_fill_contract_prices_for_equipment,
            sender=DailyReportEquipment,
        )
        post_save.disconnect(
            auto_create_contract_usage_and_fill_contract_prices_for_vehicle,
            sender=DailyReportVehicle,
        )

        try:
            for (
                serializer,
                active,
                item_id,
                daily_planned_amount,
            ) in deferred_serializers:
                # Save the serializer
                try:
                    related_instance = serializer.save()
                except IntegrityError as e:
                    logging.warning(str(e))
                    continue

                # If relation is not defined by DailyReportRelation, handle here
                if (
                    isinstance(serializer, tuple(DAILY_REPORT_RELATION_EXEMPT))
                    and item_id is None
                ):
                    if isinstance(serializer, ReportingFileSerializer):
                        report.reporting_files.add(related_instance)
                else:
                    # Determine DailyReportRelation target field & model name
                    target_field, model_name = MODEL_MAPPING.get(type(related_instance))
                    # Create relationship to instance if it was created just now
                    if item_id is None:
                        # Prepare relationship data
                        data = {
                            report_field: report,
                            target_field: related_instance,
                            "active": active if active is not None else True,
                        }

                        if daily_planned_amount is not None:
                            data["daily_planned_amount"] = daily_planned_amount

                        relations_to_create.append(DailyReportRelation(**data))

                    # Existing relationship is being altered
                    elif active is not None or daily_planned_amount is not None:
                        try:
                            kwargs = {
                                report_field: report,
                                target_field: related_instance,
                            }
                            relation = DailyReportRelation.objects.get(**kwargs)
                        except DailyReportRelation.DoesNotExist:
                            raise serializers.ValidationError(
                                "kartado.error.base_daily_report.relationship_between_report_and_{}_doesnt_exists".format(
                                    to_snake_case(model_name)
                                )
                            )
                        else:
                            data = {}
                            # Relationship status is being changed
                            if active is not None:
                                data["active"] = active

                            # Daily planned amount is being changed
                            if daily_planned_amount is not None:
                                data["daily_planned_amount"] = daily_planned_amount

                            is_partial = self.partial
                            serializer = DailyReportRelationSerializer(
                                instance=relation, data=data, partial=is_partial
                            )
                            if serializer.is_valid(raise_exception=True):
                                related_instance = serializer.save()
        finally:
            # Reconnect the signals
            post_save.connect(
                auto_create_contract_usage_and_fill_contract_prices_for_worker,
                sender=DailyReportWorker,
            )
            post_save.connect(
                auto_create_contract_usage_and_fill_contract_prices_for_equipment,
                sender=DailyReportEquipment,
            )
            post_save.connect(
                auto_create_contract_usage_and_fill_contract_prices_for_vehicle,
                sender=DailyReportVehicle,
            )

        # Bulk create new relations
        if relations_to_create:
            bulk_create_with_history(
                relations_to_create,
                DailyReportRelation,
                batch_size=100,
                default_user=report.created_by,
                ignore_conflicts=True,
            )

    def extract_relationships(self, validated_data):
        """
        Extracts the M2M relationships from validated_data
        """

        RELATIONSHIPS = [
            ("daily_report_workers", DailyReportWorker),
            ("daily_report_external_teams", DailyReportExternalTeam),
            ("daily_report_equipment", DailyReportEquipment),
            ("daily_report_vehicles", DailyReportVehicle),
            ("daily_report_signaling", DailyReportSignaling),
            ("daily_report_occurrences", DailyReportOccurrence),
            ("daily_report_production_goals", ProductionGoal),
        ]

        # If set to use Reporting resources, ignore that relationship
        if not validated_data.get("use_reporting_resources", False):
            RELATIONSHIPS.append(("daily_report_resources", DailyReportResource))

        possible_relationship_fields = []

        # Add extra possible relationship fields for other types of report
        for relationship in RELATIONSHIPS:
            relationship_field, model_class = relationship

            # DailyReport
            possible_relationship_fields.append(relationship)

            # MultipleDailyReport
            relationship = ("multiple_" + relationship_field, model_class)
            possible_relationship_fields.append(relationship)

        # Strucuture:
        # key = name of the field
        # value = tuple of model class and array of instances
        # value == [] means "delete relationships"
        # value == None means "don't do anything"
        extracted_relationships = {}

        # Extract the validated relationships and their models
        for field, model_class in possible_relationship_fields:
            if field in validated_data:
                rel_instances = validated_data.pop(field)
            else:
                rel_instances = None

            extracted_relationships[field] = (model_class, rel_instances)

        return extracted_relationships

    def handle_m2m_relationships(self, report, extracted_relationships):
        """
        Handles the logic for relationships with already existing models
        """
        # Get report relation field and report type
        report_field, report_type = determine_report_type_and_field(report)

        # Mapping de model_class para target_field e model_name
        MODEL_MAPPING = {
            DailyReportWorker: ("worker", "DailyReportWorker"),
            DailyReportExternalTeam: ("external_team", "DailyReportExternalTeam"),
            DailyReportEquipment: ("equipment", "DailyReportEquipment"),
            DailyReportVehicle: ("vehicle", "DailyReportVehicle"),
            DailyReportSignaling: ("signaling", "DailyReportSignaling"),
            DailyReportOccurrence: ("occurrence", "DailyReportOccurrence"),
            DailyReportResource: ("resource", "DailyReportResource"),
            ProductionGoal: ("production_goal", "ProductionGoal"),
        }

        # Check which relationships already exist and can be ignored
        for field, (model_class, rel_instances) in extracted_relationships.items():
            # If rel_instances is None, there's nothing to do
            # Skip to the next field
            if rel_instances is None:
                continue

            # Determine target field and model name
            target_field, model_name = MODEL_MAPPING.get(model_class, (None, None))
            if not target_field:
                continue

            relations_to_create = []

            if rel_instances:
                existing_relations = set(
                    DailyReportRelation.objects.filter(
                        **{report_field: report}
                    ).values_list(f"{target_field}__uuid", flat=True)
                )

                # Create non existing relations to rel_instances
                for rel_instance in rel_instances:
                    if rel_instance.uuid not in existing_relations:
                        relations_to_create.append(
                            DailyReportRelation(
                                **{
                                    report_field: report,
                                    target_field: rel_instance,
                                    "active": True,
                                }
                            )
                        )

                # Check which relationships were not included and can be removed
                instance_uuids = {inst.uuid for inst in rel_instances}
                items_to_remove = existing_relations - instance_uuids

            else:
                # There are no rel_instances, so remove all relationships
                items_to_remove = set(
                    DailyReportRelation.objects.filter(
                        **{report_field: report, f"{target_field}__isnull": False}
                    ).values_list(f"{target_field}__uuid", flat=True)
                )

            # Bulk create new relations
            if relations_to_create:
                bulk_create_with_history(
                    relations_to_create,
                    DailyReportRelation,
                    batch_size=100,
                    default_user=report.created_by,
                    ignore_conflicts=True,
                )

            # Bulk delete removed items
            if items_to_remove:
                model_class.objects.filter(uuid__in=items_to_remove).delete()

    def create(self, validated_data):
        # Prepare the serializers for the created models
        deferred_serializers = self.handle_model_fields(validated_data)

        # Extract M2M relationships
        extracted_relationships = self.extract_relationships(validated_data)

        # Ignore conditional fields if it's a day without work
        day_without_work = (
            validated_data["day_without_work"]
            if "day_without_work" in validated_data
            else False  # Since there's no instance to check the field
        )
        if day_without_work:
            for field in self.CONDITIONAL_FIELDS:
                # If the field is present, pop it out
                if field in validated_data:
                    validated_data.pop(field)

        # Creates the DailyReport
        instance = super().create(validated_data)

        # Add relationships to existing models
        self.handle_m2m_relationships(instance, extracted_relationships)

        # Finally save the serializers and relate the models to DailyReport
        self.handle_deferred_serializers(instance, deferred_serializers)

        # Trigger async task to process contract usage for all related board items
        # This is done after DailyReportRelation objects are created
        report_type = (
            "multiple" if isinstance(instance, MultipleDailyReport) else "single"
        )
        process_contract_usage_for_report(str(instance.uuid), report_type)

        return instance

    def update(self, instance, validated_data):
        if validated_data.get("day_without_work", False):
            validated_data["reportings"] = []
            validated_data["reporting_files"] = []

        # Prepare the serializers for the created models
        deferred_serializers = self.handle_model_fields(validated_data)

        # Extract M2M relationships
        extracted_relationships = self.extract_relationships(validated_data)

        # Update the DailyReport
        instance = super().update(instance, validated_data)

        # Add relationships to existing models
        self.handle_m2m_relationships(instance, extracted_relationships)

        # Finally save the serializers and relate the models to DailyReport
        self.handle_deferred_serializers(instance, deferred_serializers)

        # Trigger async task to process contract usage for all related board items
        # This is done after DailyReportRelation objects are created
        report_type = (
            "multiple" if isinstance(instance, MultipleDailyReport) else "single"
        )
        process_contract_usage_for_report(str(instance.uuid), report_type)

        return instance

    def validate(self, attrs):
        # Determines whether or not some validations are executed
        if "day_without_work" in attrs:  # Value is provided
            day_without_work = attrs["day_without_work"]
        elif self.instance:  # Value is not provided but present in instance
            day_without_work = self.instance.day_without_work
        else:  # Value is not provided and instance doesn't exists
            day_without_work = False

        # Validate durations
        if not day_without_work:
            period_names = ["morning", "afternoon"]
            error_template = "{}_should_be_after_{}"

            for name in period_names:
                start_key = name + "_start"
                end_key = name + "_end"

                if start_key in attrs:
                    start_time = attrs[start_key]
                elif self.instance:
                    start_time = getattr(self.instance, start_key)
                else:
                    start_time = None

                if end_key in attrs:
                    end_time = attrs[end_key]
                elif self.instance:
                    end_time = getattr(self.instance, end_key)
                else:
                    end_time = None

                start_and_end_present = start_time and end_time

                if start_and_end_present and start_time > end_time:
                    raise serializers.ValidationError(
                        "kartado.error.base_daily_report."
                        + error_template.format(end_key, start_key)
                    )

        return super().validate(attrs)


class DailyReportSerializer(BaseDailyReportSerializer, EagerLoadingMixin, UUIDMixin):
    _PREFETCH_RELATED_FIELDS = BaseDailyReportSerializer._PREFETCH_RELATED_FIELDS + [
        "daily_report_workers",
        "daily_report_external_teams",
        "daily_report_equipment",
        "daily_report_vehicles",
        "daily_report_signaling",
        "daily_report_occurrences",
        "daily_report_resources",
        "daily_report_production_goals",
        "history_historicaldailyreports",
    ]

    history_change_reason = serializers.SerializerMethodField()

    # Related models
    daily_report_workers = serializers.ResourceRelatedField(
        queryset=DailyReportWorker.objects, required=False, many=True
    )
    daily_report_external_teams = serializers.ResourceRelatedField(
        queryset=DailyReportExternalTeam.objects, required=False, many=True
    )
    daily_report_equipment = serializers.ResourceRelatedField(
        queryset=DailyReportEquipment.objects, required=False, many=True
    )
    daily_report_vehicles = serializers.ResourceRelatedField(
        queryset=DailyReportVehicle.objects, required=False, many=True
    )
    daily_report_signaling = serializers.ResourceRelatedField(
        queryset=DailyReportSignaling.objects, required=False, many=True
    )
    daily_report_occurrences = serializers.ResourceRelatedField(
        queryset=DailyReportOccurrence.objects, required=False, many=True
    )
    daily_report_resources = serializers.ResourceRelatedField(
        queryset=DailyReportResource.objects, required=False, many=True
    )
    daily_report_production_goals = serializers.ResourceRelatedField(
        queryset=ProductionGoal.objects, required=False, many=True
    )

    # Method fields
    day_before = serializers.SerializerMethodField()
    day_after = serializers.SerializerMethodField()

    class Meta(BaseDailyReportSerializer.Meta):
        model = DailyReport
        fields = BaseDailyReportSerializer.Meta.fields + [
            "identification",
            # Related models
            "daily_report_workers",
            "daily_report_external_teams",
            "daily_report_equipment",
            "daily_report_vehicles",
            "daily_report_signaling",
            "daily_report_occurrences",
            "daily_report_resources",
            "daily_report_production_goals",
            # Method fields
            "day_before",
            "day_after",
            "history_change_reason",
        ]
        read_only_fields = BaseDailyReportSerializer.Meta.read_only_fields + [
            "daily_report_workers",
            "daily_report_external_teams",
            "daily_report_equipment",
            "daily_report_vehicles",
            "daily_report_signaling",
            "daily_report_occurrences",
            "daily_report_resources",
            "daily_report_production_goals",
        ]

    def get_day_before(self, obj):
        day_before_date = obj.date - timedelta(days=1)
        try:
            report = DailyReport.objects.get(date=day_before_date, company=obj.company)
            return report.uuid
        except DailyReport.DoesNotExist:
            return None

    def get_day_after(self, obj):
        day_after_date = obj.date + timedelta(days=1)
        try:
            report = DailyReport.objects.get(date=day_after_date, company=obj.company)
            return report.uuid
        except DailyReport.DoesNotExist:
            return None

    def get_history_change_reason(self, obj):
        try:
            return obj.history_historicaldailyreports.first().history_change_reason
        except Exception:
            return None

    def create(self, validated_data):
        # Auto fill ApprovalStep
        try:
            approval_step = ApprovalStep.objects.filter(
                approval_flow__company=validated_data["company"],
                approval_flow__target_model="daily_reports.DailyReport",
                previous_steps__isnull=True,
            ).first()
            validated_data["approval_step"] = approval_step
        except Exception:
            pass

        return super().create(validated_data)


class MultipleDailyReportSerializer(
    BaseDailyReportSerializer, EagerLoadingMixin, UUIDMixin
):
    _PREFETCH_RELATED_FIELDS = BaseDailyReportSerializer._PREFETCH_RELATED_FIELDS + [
        Prefetch(
            "reportings",
            queryset=Reporting.objects.order_by("road_name", "km").only(
                "road_name", "km", "end_km"
            ),
        ),
        Prefetch(
            "reportings__reporting_resources",
            queryset=ProcedureResource.objects.only(
                "uuid", "total_price", "reporting_id"
            ),
        ),
        "history_historicalmultipledailyreports",
        "multiple_daily_report_workers",
        "multiple_daily_report_external_teams",
        "multiple_daily_report_equipment",
        "multiple_daily_report_vehicles",
        "multiple_daily_report_signaling",
        "multiple_daily_report_occurrences",
        "multiple_daily_report_resources",
        "multiple_daily_report_production_goals",
        "approval_step__responsible_users",
        "approval_step__responsible_firms",
        "approval_step__responsible_firms__manager",
        "approval_step__responsible_firms__users",
        "firm",
        "firm__users",
        "firm__inspectors",
        "firm__subcompany",
        "firm__manager",
    ]

    history_change_reason = serializers.SerializerMethodField()

    subcompany = SerializerMethodResourceRelatedField(
        model=SubCompany, method_name="get_subcompany", read_only=True, many=False
    )

    # Related models
    multiple_daily_report_workers = serializers.ResourceRelatedField(
        queryset=DailyReportWorker.objects, required=False, many=True
    )
    multiple_daily_report_external_teams = serializers.ResourceRelatedField(
        queryset=DailyReportExternalTeam.objects, required=False, many=True
    )
    multiple_daily_report_equipment = serializers.ResourceRelatedField(
        queryset=DailyReportEquipment.objects, required=False, many=True
    )
    multiple_daily_report_vehicles = serializers.ResourceRelatedField(
        queryset=DailyReportVehicle.objects, required=False, many=True
    )
    multiple_daily_report_signaling = serializers.ResourceRelatedField(
        queryset=DailyReportSignaling.objects, required=False, many=True
    )
    multiple_daily_report_occurrences = serializers.ResourceRelatedField(
        queryset=DailyReportOccurrence.objects, required=False, many=True
    )
    multiple_daily_report_resources = serializers.ResourceRelatedField(
        queryset=DailyReportResource.objects, required=False, many=True
    )
    multiple_daily_report_production_goals = serializers.ResourceRelatedField(
        queryset=DailyReportSignaling.objects, required=False, many=True
    )

    # Method fields
    km_intervals = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    is_currently_responsible = serializers.SerializerMethodField()
    can_you_edit = serializers.SerializerMethodField()

    morning_start = ForgivingTimeField(required=False, allow_null=True)
    morning_end = ForgivingTimeField(required=False, allow_null=True)
    afternoon_start = ForgivingTimeField(required=False, allow_null=True)
    afternoon_end = ForgivingTimeField(required=False, allow_null=True)
    night_start = ForgivingTimeField(required=False, allow_null=True)
    night_end = ForgivingTimeField(required=False, allow_null=True)
    created_by = serializers.ResourceRelatedField(
        queryset=User.objects.all(),
        required=False,
        default=serializers.CurrentUserDefault(),
    )

    class Meta(BaseDailyReportSerializer.Meta):
        model = MultipleDailyReport
        fields = BaseDailyReportSerializer.Meta.fields + [
            "firm",
            "reportings",
            "km_intervals",
            "price",
            "subcompany",
            "history_change_reason",
            "is_currently_responsible",
            # Related models
            "multiple_daily_report_workers",
            "multiple_daily_report_external_teams",
            "multiple_daily_report_equipment",
            "multiple_daily_report_vehicles",
            "multiple_daily_report_signaling",
            "multiple_daily_report_occurrences",
            "multiple_daily_report_resources",
            "multiple_daily_report_production_goals",
            "can_you_edit",
            "created_by",
            "legacy_number",
            "compensation",
        ]
        read_only_fields = [
            field
            for field in BaseDailyReportSerializer.Meta.read_only_fields
            if field != "created_by"
        ] + [
            "multiple_daily_report_workers",
            "multiple_daily_report_external_teams",
            "multiple_daily_report_equipment",
            "multiple_daily_report_vehicles",
            "multiple_daily_report_signaling",
            "multiple_daily_report_occurrences",
            "multiple_daily_report_resources",
            "multiple_daily_report_production_goals",
            "is_currently_responsible",
            "can_you_edit",
        ]

    def to_internal_value(self, attrs):
        if "compensation" in attrs and attrs.get("compensation", "") is None:
            attrs["compensation"] = False
        return super().to_internal_value(attrs)

    def create(self, validated_data):
        if validated_data.get("day_without_work", False):
            validated_data["reportings"] = []
            validated_data["reporting_files"] = []

        # Auto fill ApprovalStep
        try:
            approval_step = ApprovalStep.objects.filter(
                approval_flow__company=validated_data["company"],
                approval_flow__target_model="daily_reports.MultipleDailyReport",
                previous_steps__isnull=True,
            ).first()
            validated_data["approval_step"] = approval_step
        except Exception:
            pass

        firm_uuids_for_webhook = (
            get_obj_from_path(
                validated_data["company"].metadata,
                "firm_uuids_that_should_call_daily_report_webhook",
            )
            or []
        )
        firm = validated_data.get("firm")
        should_call_daily_report_webhook = (
            firm and str(firm.uuid) in firm_uuids_for_webhook
        )

        if validated_data.get("day_without_work", False):
            with DisableSignals(disabled_signals=[pre_init, post_init]):
                instance = super().create(validated_data)
            if hasattr(self, "context") and "request" in self.context:
                target_company_id = get_obj_from_path(
                    instance.company.metadata, "n8n_target_company_id"
                )
                if target_company_id:
                    send_daily_report_same_db_to_n8n(
                        self.context["request"].raw_body,
                        instance.number,
                        instance.company,
                        source_uuid=str(instance.uuid),
                        source_firm=instance.firm,
                    )
                elif should_call_daily_report_webhook:
                    send_daily_report_to_n8n(
                        self.context["request"].raw_body,
                        instance.number,
                        instance.company,
                    )
            return instance
        # Automatically assign Reportings
        possible_path = "field_to_automatically_link_reportings_to_rdo"
        field_to_link_rdo = get_obj_from_path(
            validated_data["company"].metadata, possible_path
        )

        if not field_to_link_rdo:
            field_to_link_rdo = "found_at"

        no_reportings_provided = validated_data.get("reportings", []) == []
        if no_reportings_provided:
            reportings_executed_at_date = Reporting.objects.filter(
                get_reporting_date_lookup(field_to_link_rdo, validated_data["date"]),
                company=validated_data["company"],
                firm=validated_data["firm"],
            )
            if reportings_executed_at_date:
                validated_data["reportings"] = list(reportings_executed_at_date)
        with DisableSignals(disabled_signals=[pre_init, post_init]):
            instance = super().create(validated_data)
        if hasattr(self, "context") and "request" in self.context:
            target_company_id = get_obj_from_path(
                instance.company.metadata, "n8n_target_company_id"
            )
            if target_company_id:
                send_daily_report_same_db_to_n8n(
                    self.context["request"].raw_body,
                    instance.number,
                    instance.company,
                    source_uuid=str(instance.uuid),
                    source_firm=instance.firm,
                )
            elif should_call_daily_report_webhook:
                send_daily_report_to_n8n(
                    self.context["request"].raw_body,
                    instance.number,
                    instance.company,
                )
        return instance

    def update(self, instance, validated_data):
        # Check if frontend requested reporting links update
        update_reportings_on_date_change = self.initial_data.get(
            "update_reportings_on_date_change", False
        )

        old_date = instance.date
        new_date = validated_data.get("date", old_date)
        date_changed = old_date != new_date

        # Prevent duplicate M2M set by DRF ModelSerializer
        if date_changed and update_reportings_on_date_change:
            validated_data.pop("reportings", None)

        instance = super().update(instance, validated_data)

        # Update reporting links based on new date
        if date_changed and update_reportings_on_date_change:
            field_to_link_rdo = (
                get_obj_from_path(
                    instance.company.metadata,
                    "field_to_automatically_link_reportings_to_rdo",
                )
                or "found_at"
            )

            with transaction.atomic():
                new_reportings = Reporting.objects.filter(
                    get_reporting_date_lookup(field_to_link_rdo, new_date),
                    company=instance.company,
                    firm=instance.firm,
                )
                instance.reportings.set(new_reportings)

        firm_uuids_for_webhook = (
            get_obj_from_path(
                instance.company.metadata,
                "firm_uuids_that_should_call_daily_report_webhook",
            )
            or []
        )
        firm = validated_data.get("firm", instance.firm)
        should_call_webhook = firm and str(firm.uuid) in firm_uuids_for_webhook

        if hasattr(self, "context") and "request" in self.context:
            if should_call_webhook:
                from .services import send_edited_daily_report_to_n8n

                send_edited_daily_report_to_n8n(
                    self.context["request"].raw_body,
                    str(instance.uuid),
                    instance.company,
                )

        return instance

    def validate_created_by(self, value):
        if not value.is_active:
            raise serializers.ValidationError(
                "O usuário especificado em created_by não está ativo."
            )
        return value

    def validate(self, attrs):
        if self.instance:
            created_by = self.instance.created_by
        else:
            created_by = attrs.get("created_by", self.context["request"].user)

        firm = attrs.get("firm", getattr(self.instance, "firm", None))
        date = attrs.get("date", getattr(self.instance, "date", None))

        if MultipleDailyReport.objects.filter(
            created_by=created_by, firm=firm, date=date
        ).exists():
            report = MultipleDailyReport.objects.get(
                created_by=created_by, firm=firm, date=date
            )
            if "id" in self.initial_data and self.initial_data["id"] == str(
                report.uuid
            ):
                return super().validate(attrs)
            else:
                raise serializers.ValidationError(
                    "kartado.error.multiple_daily_report.created_by_firm_and_date_should_create_unique_set"
                )

        return super().validate(attrs)

    def get_km_intervals(self, obj):
        return get_km_intervals_field(obj, only_query=False)

    def get_price(self, obj):
        request_method = self.context["request"].method

        if request_method in ["POST", "PATCH"]:
            total = obj.reportings.aggregate(
                total=Sum("reporting_resources__total_price")
            )["total"]
            return total or 0.0
        else:
            price = 0.0

            if obj.reportings.count() > 0:
                reportings = obj.reportings.all()
                for reporting in reportings:
                    for item in reporting.reporting_resources.all():
                        price += item.total_price

            return price

    def get_subcompany(self, obj):
        return obj.firm.subcompany

    def get_history_change_reason(self, obj):
        try:
            return (
                obj.history_historicalmultipledailyreports.first().history_change_reason
            )
        except Exception:
            return None

    def get_is_currently_responsible(self, obj):
        try:
            user_firms = (
                self.context["user_firms"]
                if "user_firms" in self.context
                else self.context["request"].user.user_firms.filter(
                    company_id=obj.company_id
                )
            )
            user_permissions = self.context["view"].permissions.all_permissions
        except KeyError:
            return False

        return is_currently_responsible(
            obj, self.context["request"].user, user_firms, user_permissions
        )

    def get_can_you_edit(self, obj):
        try:
            can_you_edit = self.context.get("can_you_edit")
            if not can_you_edit:
                user = self.context["request"].user
                return bool(
                    user.pk == obj.firm.manager.pk
                    or user in obj.firm.users.all()
                    or user in obj.firm.inspectors.all()
                )
            else:
                return can_you_edit
        except Exception as err:
            sentry_sdk.capture_exception(err)
            return None

    def validate_firm(self, firm):
        user = self.context.get("request").user
        if firm is None:
            return firm
        if self.context.get("can_create_and_edit_all_firms") is True:
            return firm

        elif not bool(
            user in firm.users.all()
            or user in firm.inspectors.all()
            or user.pk == firm.manager.pk
        ):
            if self.context["request"].method == "POST":
                raise serializers.ValidationError(
                    "kartado.error.multiple_daily_report.create_user_is_not_part_of_the_firm"
                )
            else:
                raise serializers.ValidationError(
                    "kartado.error.multiple_daily_report.edit_user_is_not_part_of_the_firm"
                )

        else:
            return firm


class DailyReportWorkerSerializer(ActiveFieldModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "firm",
        "company",
        "contract_item_administration",
        "approved_by",
        "created_by",
        "daily_reports",
        Prefetch(
            "multiple_daily_reports",
            queryset=MultipleDailyReport.objects.all().only("uuid", "created_by"),
        ),
        "history_workers",
        "multiple_daily_reports__created_by",
        "measurement_bulletin",
        "contract_item_administration__resource__resource",
    ]

    uuid = serializers.UUIDField(required=False)
    daily_reports = ResourceRelatedField(
        queryset=DailyReport.objects, required=False, many=True
    )
    multiple_daily_reports = ResourceRelatedField(
        queryset=MultipleDailyReport.objects, required=False, many=True
    )

    history_change_reason = serializers.SerializerMethodField()
    created_by = SerializerMethodResourceRelatedField(
        model=User, method_name="get_created_by", read_only=True
    )
    measurement_bulletin = ResourceRelatedField(
        queryset=MeasurementBulletin.objects,
        required=False,
        many=False,
        allow_null=True,
    )
    name = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()

    class Meta:
        model = DailyReportWorker
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "firm",
            "company",
            "members",
            "amount",
            "role",
            "creation_date",
            "total_price",
            "contract_item_administration",
            "active",
            "approval_status",
            "approval_date",
            "approved_by",
            "history_change_reason",
            "created_by",
            "measurement_bulletin",
            "name",
            "unit_price",
            "extra_hours",
        ]

    def get_history_change_reason(self, obj):
        try:
            return obj.history_workers.first().history_change_reason
        except Exception:
            return None

    def get_unit_price(self, obj):
        if obj.unit_price is not None:
            return obj.unit_price
        if (
            obj.contract_item_administration
            and obj.contract_item_administration.resource
        ):
            return obj.contract_item_administration.resource.unit_price
        return None

    def get_name(self, obj):
        return get_board_item_name(obj, self.Meta.model._meta.model_name, "role")

    def validate(self, attrs):
        firm_is_filled = "firm" in attrs or (self.instance and self.instance.firm)
        company_is_filled = "company" in attrs or (
            self.instance and self.instance.company
        )

        if not firm_is_filled and not company_is_filled:
            raise serializers.ValidationError(
                "kartado.error.daily_report_worker.either_company_or_firm_needs_to_be_filled"
            )

        return super().validate(attrs)

    def get_created_by(self, obj):
        if obj.created_by:
            return obj.created_by
        return (
            obj.multiple_daily_reports.first().created_by
            if obj.multiple_daily_reports.exists()
            else None
        )

    def create(self, validated_data):
        instance = super().create(validated_data)
        add_history_change_reason(instance, self.initial_data)
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        add_history_change_reason(instance, self.initial_data)
        return instance


class DailyReportExternalTeamSerializer(ActiveFieldModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["daily_reports", "multiple_daily_reports", "company"]

    uuid = serializers.UUIDField(required=False)
    daily_reports = ResourceRelatedField(
        queryset=DailyReport.objects, required=False, many=True
    )
    multiple_daily_reports = ResourceRelatedField(
        queryset=MultipleDailyReport.objects, required=False, many=True
    )

    class Meta:
        model = DailyReportExternalTeam
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "company",
            "contract_number",
            "contractor_name",
            "amount",
            "contract_description",
            "active",
        ]


class DailyReportEquipmentSerializer(ActiveFieldModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "company",
        "contract_item_administration",
        "approved_by",
        "created_by",
        "daily_reports",
        Prefetch(
            "multiple_daily_reports",
            queryset=MultipleDailyReport.objects.all().only("uuid", "created_by"),
        ),
        "history_equipment",
        "multiple_daily_reports__created_by",
        "measurement_bulletin",
        "contract_item_administration__resource__resource",
    ]

    uuid = serializers.UUIDField(required=False)
    daily_reports = ResourceRelatedField(
        queryset=DailyReport.objects, required=False, many=True
    )
    multiple_daily_reports = ResourceRelatedField(
        queryset=MultipleDailyReport.objects, required=False, many=True
    )

    history_change_reason = serializers.SerializerMethodField()
    created_by = SerializerMethodResourceRelatedField(
        model=User, method_name="get_created_by", read_only=True
    )
    measurement_bulletin = ResourceRelatedField(
        queryset=MeasurementBulletin.objects,
        required=False,
        many=False,
        allow_null=True,
    )
    name = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()

    class Meta:
        model = DailyReportEquipment
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "company",
            "kind",
            "description",
            "amount",
            "creation_date",
            "total_price",
            "contract_item_administration",
            "active",
            "approval_status",
            "approval_date",
            "approved_by",
            "history_change_reason",
            "created_by",
            "measurement_bulletin",
            "name",
            "unit_price",
            "extra_hours",
        ]

    def get_created_by(self, obj):
        if obj.created_by:
            return obj.created_by
        return (
            obj.multiple_daily_reports.first().created_by
            if obj.multiple_daily_reports.exists()
            else None
        )

    def get_unit_price(self, obj):
        if obj.unit_price is not None:
            return obj.unit_price
        if (
            obj.contract_item_administration
            and obj.contract_item_administration.resource
        ):
            return obj.contract_item_administration.resource.unit_price
        return None

    def get_history_change_reason(self, obj):
        try:
            return obj.history_equipment.first().history_change_reason
        except Exception:
            return None

    def get_name(self, obj):
        return get_board_item_name(obj, self.Meta.model._meta.model_name, "description")

    def create(self, validated_data):
        instance = super().create(validated_data)
        add_history_change_reason(instance, self.initial_data)
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        add_history_change_reason(instance, self.initial_data)
        return instance


class DailyReportVehicleSerializer(ActiveFieldModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "company",
        "contract_item_administration",
        "approved_by",
        "created_by",
        "daily_reports",
        Prefetch(
            "multiple_daily_reports",
            queryset=MultipleDailyReport.objects.all().only("uuid", "created_by"),
        ),
        "history_vehicles",
        "multiple_daily_reports__created_by",
        "measurement_bulletin",
        "contract_item_administration__resource__resource",
    ]

    uuid = serializers.UUIDField(required=False)
    daily_reports = ResourceRelatedField(
        queryset=DailyReport.objects, required=False, many=True
    )
    multiple_daily_reports = ResourceRelatedField(
        queryset=MultipleDailyReport.objects, required=False, many=True
    )

    history_change_reason = serializers.SerializerMethodField()
    created_by = SerializerMethodResourceRelatedField(
        model=User, method_name="get_created_by", read_only=True
    )
    measurement_bulletin = ResourceRelatedField(
        queryset=MeasurementBulletin.objects,
        required=False,
        many=False,
        allow_null=True,
    )
    name = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()

    class Meta:
        model = DailyReportVehicle
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "company",
            "kind",
            "description",
            "amount",
            "creation_date",
            "total_price",
            "contract_item_administration",
            "active",
            "approval_status",
            "approval_date",
            "approved_by",
            "history_change_reason",
            "created_by",
            "measurement_bulletin",
            "name",
            "unit_price",
            "extra_hours",
        ]

    def get_created_by(self, obj):
        if obj.created_by:
            return obj.created_by
        return (
            obj.multiple_daily_reports.all()[0].created_by
            if obj.multiple_daily_reports.count()
            else None
        )

    def get_unit_price(self, obj):
        if obj.unit_price is not None:
            return obj.unit_price
        if (
            obj.contract_item_administration
            and obj.contract_item_administration.resource
        ):
            return obj.contract_item_administration.resource.unit_price
        return None

    def get_history_change_reason(self, obj):
        try:
            return obj.history_vehicles.first().history_change_reason
        except Exception:
            return None

    def get_name(self, obj):
        return get_board_item_name(obj, self.Meta.model._meta.model_name, "description")

    def create(self, validated_data):
        instance = super().create(validated_data)
        add_history_change_reason(instance, self.initial_data)
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        add_history_change_reason(instance, self.initial_data)
        return instance


class DailyReportSignalingSerializer(ActiveFieldModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "daily_reports",
        Prefetch(
            "multiple_daily_reports",
            queryset=MultipleDailyReport.objects.all().only("uuid", "created_by"),
        ),
        "company",
    ]

    uuid = serializers.UUIDField(required=False)
    daily_reports = ResourceRelatedField(
        queryset=DailyReport.objects, required=False, many=True
    )
    multiple_daily_reports = ResourceRelatedField(
        queryset=MultipleDailyReport.objects, required=False, many=True
    )

    class Meta:
        model = DailyReportSignaling
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "company",
            "kind",
            "active",
        ]


class DailyReportOccurrenceSerializer(ActiveFieldModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "daily_reports",
        Prefetch(
            "multiple_daily_reports",
            queryset=MultipleDailyReport.objects.all().only("uuid", "created_by"),
        ),
        "firm",
    ]

    uuid = serializers.UUIDField(required=False)
    daily_reports = ResourceRelatedField(
        queryset=DailyReport.objects, required=False, many=True
    )
    multiple_daily_reports = ResourceRelatedField(
        queryset=MultipleDailyReport.objects, required=False, many=True
    )

    class Meta:
        model = DailyReportOccurrence
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "firm",
            "starts_at",
            "ends_at",
            "impact_duration",
            "description",
            "extra_info",
            "active",
            "origin",
        ]


class DailyReportResourceSerializer(ActiveFieldModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "daily_reports",
        "resource",
        Prefetch(
            "multiple_daily_reports",
            queryset=MultipleDailyReport.objects.all().only("uuid", "created_by"),
        ),
    ]

    uuid = serializers.UUIDField(required=False)
    daily_reports = ResourceRelatedField(
        queryset=DailyReport.objects, required=False, many=True
    )
    multiple_daily_reports = ResourceRelatedField(
        queryset=MultipleDailyReport.objects, required=False, many=True
    )

    class Meta:
        model = DailyReportResource
        fields = [
            "uuid",
            "daily_reports",
            "multiple_daily_reports",
            "kind",
            "amount",
            "resource",
            "active",
        ]


class ProductionGoalSerializer(ActiveFieldModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "daily_reports",
        "multiple_daily_reports",
        "service__occurrence_types",
        "service",
    ]

    uuid = serializers.UUIDField(required=False)
    daily_reports = ResourceRelatedField(
        queryset=DailyReport.objects, required=False, many=True
    )
    multiple_daily_reports = ResourceRelatedField(
        queryset=MultipleDailyReport.objects, required=False, many=True
    )
    name = serializers.SerializerMethodField()

    # Filter dependant fields
    daily_amount = serializers.SerializerMethodField()
    amount_to_date = serializers.SerializerMethodField()
    percent_done = serializers.SerializerMethodField()
    remaining_days = serializers.SerializerMethodField()
    occurrence_types = serializers.SerializerMethodField()
    daily_planned_amount = serializers.SerializerMethodField()

    class Meta:
        model = ProductionGoal
        filter_dependant_fields = [
            "active",
            "daily_amount",
            "amount_to_date",
            "percent_done",
            "daily_planned_amount",
        ]
        fields = [
            "uuid",
            "name",
            "daily_reports",
            "multiple_daily_reports",
            "service",
            "starts_at",
            "ends_at",
            "days_of_work",
            "remaining_days",
            "amount",
            "occurrence_types",
        ] + filter_dependant_fields

    def extract_reports(self, validated_data):
        """
        Extracts all relationships to DailyReport from validated_data and
        returns it. None is returned if no relationships are present.
        """
        if "daily_reports" in validated_data:
            reports = validated_data.pop("daily_reports")
        else:
            reports = None

        return reports

    def handle_report_relationships(self, instance, reports):
        """
        Handles adding and removing relationships to DailyReport
        """
        if reports is not None:
            if len(reports) > 0:
                # Create non existing relationships
                for report in reports:
                    if not DailyReportRelation.objects.filter(
                        daily_report=report, production_goal=instance
                    ).exists():
                        data = {
                            "daily_report": {
                                "type": "DailyReport",
                                "id": str(report.uuid),
                            },
                            "production_goal": {
                                "type": "ProductionGoal",
                                "id": str(instance.uuid),
                            },
                            "active": True,  # New relationships are active
                        }
                        rel_serializer = DailyReportRelationSerializer(data=data)
                        if rel_serializer.is_valid(raise_exception=True):
                            rel_serializer.save()

                # Check which relationships were not included and can be removed
                kwargs_in = {"daily_report__in": reports}
                kwargs_is_null = {"daily_report__isnull": True}

                # Delete relations
                relations_to_remove = DailyReportRelation.objects.filter(
                    production_goal=instance
                ).exclude(Q(**kwargs_in) | Q(**kwargs_is_null))
                relations_to_remove.delete()

            # There are no reports, so remove all relationships
            elif len(reports) == 0:
                relations_to_remove = DailyReportRelation.objects.filter(
                    production_goal=instance, daily_report__isnull=False
                )
                relations_to_remove.delete()

    def handle_automatic_relationships(self, instance):
        """
        Automatically adds DailyReport instances within the time span
        of ProductionGoal when creating.
        """
        reports = DailyReport.objects.filter(
            date__gte=instance.starts_at, date__lte=instance.ends_at
        ).exclude(daily_report_production_goals__in=[instance])
        instance.daily_reports.add(*list(reports))

    def create(self, validated_data):
        reports = self.extract_reports(validated_data)
        instance = super().create(validated_data)
        self.handle_report_relationships(instance, reports)
        self.handle_automatic_relationships(instance)

        return instance

    def update(self, instance, validated_data):
        reports = self.extract_reports(validated_data)
        updated_instance = super().update(instance, validated_data)
        self.handle_report_relationships(updated_instance, reports)

        return updated_instance

    def get_name(self, obj):
        return obj.service.name

    # ActiveFieldModelSerializer method override
    def pop_fields(self):
        for field in self.Meta.filter_dependant_fields:
            self.fields.pop(field)

    def get_daily_amount(self, obj):
        report_info = self.get_report_id_and_field()
        total_amount = 0.0

        if report_info is not None:
            report_id, report_kind = report_info
            if report_kind == "daily_report":
                report = obj.daily_reports.get(uuid=report_id)
            elif report_kind == "multiple_daily_report":
                report = obj.multiple_daily_reports.get(uuid=report_id)

            kwargs = {
                "executed_at__date__gte": obj.starts_at,
                "executed_at__date__lte": obj.ends_at,
                "executed_at__date": report.date,
                "company": obj.service.company,
            }

            # If firm filter is provided, use only reportings of that firm
            firm_id = self.get_firm_id()
            if firm_id:
                kwargs["firm"] = firm_id

            reportings = Reporting.objects.filter(**kwargs)

            service_usages = ServiceUsage.objects.filter(
                reporting__in=reportings, service=obj.service
            )
            total_amount = sum(service_usages.values_list("amount", flat=True))
            total_amount = float(total_amount)

        return total_amount

    def get_amount_to_date(self, obj):
        report_info = self.get_report_id_and_field()
        total_amount = 0.0

        if report_info is not None:
            report_id, report_kind = report_info
            if report_kind == "daily_report":
                limit_date = obj.daily_reports.get(uuid=report_id).date
                reports = obj.daily_reports.filter(
                    date__gte=obj.starts_at, date__lte=limit_date
                )
            elif report_kind == "multiple_daily_report":
                limit_date = obj.multiple_daily_reports.get(uuid=report_id).date
                reports = obj.multiple_daily_reports.filter(
                    date__gte=obj.starts_at, date__lte=limit_date
                )
            report_dates = reports.values_list("date", flat=True)

            kwargs = {
                "executed_at__date__gte": obj.starts_at,
                "executed_at__date__lte": obj.ends_at,
                "executed_at__date__in": report_dates,
                "company": obj.service.company,
            }

            # If firm filter is provided, use only reportings of that firm
            firm_id = self.get_firm_id()
            if firm_id:
                kwargs["firm"] = firm_id

            reportings = Reporting.objects.filter(**kwargs)

            service_usages = ServiceUsage.objects.filter(
                reporting__in=reportings, service=obj.service
            )
            total_amount = sum(service_usages.values_list("amount", flat=True))
            total_amount = float(total_amount)

        return total_amount

    def get_percent_done(self, obj):
        try:
            amount_to_date = self.get_amount_to_date(obj)
            percent = amount_to_date / obj.amount
            return round(percent, 2)
        except ZeroDivisionError:
            return 0.0

    def get_remaining_days(self, obj):
        # Reports related to the ProductionGoal
        daily_reports = obj.daily_reports.all()
        multiple_daily_reports = obj.multiple_daily_reports.all()

        # Get firm_id if the filter is provided
        firm_id = self.get_firm_id()

        # Get days with progress
        daily_report_days = days_with_progress(daily_reports, obj, firm_id)
        multiple_daily_report_days = days_with_progress(
            multiple_daily_reports, obj, firm_id
        )
        total_days = daily_report_days + multiple_daily_report_days

        return obj.days_of_work - total_days

    def get_occurrence_types(self, obj):
        uuids = obj.service.occurrence_types.all().values_list("uuid", flat=True)
        return list(uuids)

    def get_daily_planned_amount(self, obj):
        report_info = self.get_report_id_and_field()

        if report_info is not None:
            report_id, report_kind = report_info

            if report_kind == "daily_report":
                relation = DailyReportRelation.objects.get(
                    daily_report=report_id, production_goal=obj
                )
            elif report_kind == "multiple_daily_report":
                relation = DailyReportRelation.objects.get(
                    multiple_daily_report=report_id, production_goal=obj
                )

            return relation.daily_planned_amount

        return None

    def validate(self, attrs):
        starts_at = (
            attrs["starts_at"] if "starts_at" in attrs else self.instance.starts_at
        )
        ends_at = attrs["ends_at"] if "ends_at" in attrs else self.instance.ends_at

        if starts_at > ends_at:
            raise serializers.ValidationError(
                "kartado.error.production_goal.ends_at_should_be_after_starts_at"
            )

        return super().validate(attrs)


class DailyReportRelationSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "daily_report",
        Prefetch(
            "multiple_daily_report",
            queryset=MultipleDailyReport.objects.all().only("uuid"),
        ),
        "worker",
        "external_team",
        "equipment",
        "vehicle",
        "signaling",
        "occurrence",
        "resource",
        "production_goal",
    ]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = DailyReportRelation
        fields = [
            "uuid",
            "active",
            "daily_planned_amount",
            "daily_report",
            "multiple_daily_report",
            "worker",
            "external_team",
            "equipment",
            "vehicle",
            "signaling",
            "occurrence",
            "resource",
            "production_goal",
        ]


def get_contract_usage_prefetch_object(relation_name, model):
    history_relation = (
        "history_" + relation_name + ("" if relation_name == "equipment" else "s")
    )

    return Prefetch(
        relation_name,
        queryset=model.objects.all()
        .annotate(
            resource_name=F("contract_item_administration__resource__resource__name"),
            resource_unit=F("contract_item_administration__resource__resource__unit"),
            entity_id=F("contract_item_administration__entity_id"),
        )
        .prefetch_related(
            "contract_item_administration__resource",  # For unit_price access
            history_relation,  # For history_change_reason
        ),
    )


class DailyReportContractUsageSerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    # OPTIMIZED: Prefetch only what is actually used by serializer methods
    _PREFETCH_RELATED_FIELDS = [
        get_contract_usage_prefetch_object("worker", DailyReportWorker),
        get_contract_usage_prefetch_object("equipment", DailyReportEquipment),
        get_contract_usage_prefetch_object("vehicle", DailyReportVehicle),
        "contract_item_administration",
        "contract_item_administration__resource",  # For annotations in get_contract_usage_prefetch_object
        "contract_item_administration__contract_item_administration_services",  # For get_amount_per_period
        "contract_item_administration__contract_item_administration_services__administration_service_contracts",  # For get_amount_per_period
        "measurement_bulletin",  # For get_measurement_bulletin
        "multiple_daily_reports",  # For get_multiple_daily_report_date, get_created_by, get_multiple_daily_reports
    ]

    uuid = serializers.UUIDField(required=False)

    board_item_type = serializers.SerializerMethodField()
    resource_name = serializers.SerializerMethodField()
    amount_per_period = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()
    approval_date = serializers.SerializerMethodField()
    approval_status = serializers.SerializerMethodField()
    multiple_daily_report_date = serializers.SerializerMethodField()

    entity = OptimizedSerializerMethodResourceRelatedField(
        model=Entity, read_only=True, many=False, method_name="get_entity"
    )
    created_by = OptimizedSerializerMethodResourceRelatedField(
        model=User, read_only=True, many=False, method_name="get_created_by"
    )
    approved_by = OptimizedSerializerMethodResourceRelatedField(
        model=User, read_only=True, many=False, method_name="get_approved_by"
    )
    multiple_daily_reports = SerializerMethodResourceRelatedField(
        model=MultipleDailyReport,
        read_only=True,
        many=True,
        method_name="get_multiple_daily_reports",
    )
    measurement_bulletin = SerializerMethodResourceRelatedField(
        model=MeasurementBulletin,
        read_only=True,
        many=False,
        method_name="get_measurement_bulletin",
    )

    history_change_reason = serializers.SerializerMethodField()

    class Meta:
        model = DailyReportContractUsage
        fields = [
            "uuid",
            "worker",
            "equipment",
            "vehicle",
            "board_item_type",
            "resource_name",
            "amount",
            "amount_per_period",
            "unit",
            "created_at",
            "unit_price",
            "total_price",
            "approval_date",
            "approval_status",
            "multiple_daily_report_date",
            "entity",
            "created_by",
            "approved_by",
            "history_change_reason",
            "multiple_daily_reports",
            "measurement_bulletin",
        ]

    def calculate_board_instance(self, obj):
        if obj.worker:
            return obj.worker
        elif obj.equipment:
            return obj.equipment
        elif obj.vehicle:
            return obj.vehicle
        else:
            return None

    def get_board_instance(self, obj):
        if not hasattr(self, "_board_instance"):
            self._board_instance = {}
        if obj.pk not in self._board_instance:
            self._board_instance[obj.pk] = self.calculate_board_instance(obj)
        return self._board_instance[obj.pk]

    def get_board_item_type(self, obj):
        board_instance = self.get_board_instance(obj)
        return type(board_instance).__name__ if board_instance else None

    def get_resource_name(self, obj):
        board_instance = self.get_board_instance(obj)
        try:
            return board_instance.resource_name
        except Exception:
            return None

    def get_amount_per_period(self, obj):
        # OPTIMIZED: Use prefetched relations instead of .all()[0]
        board_instance = self.get_board_instance(obj)
        try:
            amount = board_instance.amount
            if not obj.contract_item_administration:
                return None

            # Use prefetched contract_item_administration_services
            contract_services = list(
                obj.contract_item_administration.contract_item_administration_services.all()
            )
            if not contract_services:
                return None

            contract_service = contract_services[0]
            # Use prefetched administration_service_contracts
            contracts = list(contract_service.administration_service_contracts.all())
            if not contracts:
                return None

            contract = contracts[0]
            months = relativedelta(
                contract.contract_end, contract.contract_start
            ).months

            return amount / months if months > 0 else None
        except Exception:
            return None

    def get_amount(self, obj):
        board_instance = self.get_board_instance(obj)
        return board_instance.amount if board_instance else None

    def get_unit(self, obj):
        board_instance = self.get_board_instance(obj)
        try:
            return board_instance.resource_unit
        except Exception:
            return None

    def get_created_at(self, obj):
        board_instance = self.get_board_instance(obj)
        return board_instance.creation_date if board_instance else None

    def get_unit_price(self, obj):
        board_instance = self.get_board_instance(obj)
        try:
            if board_instance.unit_price is None:
                return board_instance.contract_item_administration.resource.unit_price
            return board_instance.unit_price
        except Exception:
            return None

    def get_total_price(self, obj):
        board_instance = self.get_board_instance(obj)
        return board_instance.total_price if board_instance.total_price else None

    def get_approval_date(self, obj):
        board_instance = self.get_board_instance(obj)
        return board_instance.approval_date if board_instance else None

    def get_approval_status(self, obj):
        board_instance = self.get_board_instance(obj)
        return board_instance.approval_status if board_instance else None

    def get_multiple_daily_report_date(self, obj):
        try:
            # OPTIMIZED: Use denormalized field obj.multiple_daily_reports instead of board_instance
            reports = list(obj.multiple_daily_reports.all())
            if reports:
                return reports[0].date
            return None
        except Exception:
            return None

    def get_entity(self, obj):
        board_instance = self.get_board_instance(obj)
        try:
            return board_instance.entity_id
        except Exception:
            return None

    def get_created_by(self, obj):
        # OPTIMIZED: Use denormalized field obj.multiple_daily_reports
        board_instance = self.get_board_instance(obj)
        try:
            if board_instance.created_by_id:
                return board_instance.created_by_id
            # Use prefetched obj.multiple_daily_reports
            reports = list(obj.multiple_daily_reports.all())
            if reports:
                return reports[0].created_by_id
            return None
        except Exception:
            return None

    def get_approved_by(self, obj):
        board_instance = self.get_board_instance(obj)
        return board_instance.approved_by_id if board_instance else None

    def get_history_change_reason(self, obj):
        # OPTIMIZED: Use list()[:1] instead of .first() to leverage prefetch cache
        try:
            if obj.worker:
                history_list = list(obj.worker.history_workers.all()[:1])
                if history_list:
                    return history_list[0].history_change_reason
            elif obj.equipment:
                history_list = list(obj.equipment.history_equipment.all()[:1])
                if history_list:
                    return history_list[0].history_change_reason
            elif obj.vehicle:
                history_list = list(obj.vehicle.history_vehicles.all()[:1])
                if history_list:
                    return history_list[0].history_change_reason
        except Exception:
            pass
        return None

    def get_multiple_daily_reports(self, obj):
        # OPTIMIZED: Use denormalized field obj.multiple_daily_reports directly
        return obj.multiple_daily_reports.all()

    def get_measurement_bulletin(self, obj):
        # OPTIMIZED: Use denormalized field obj.measurement_bulletin directly
        return obj.measurement_bulletin


class DailyReportExportSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["daily_reports", "multiple_daily_reports", "created_by"]

    uuid = serializers.UUIDField(required=False)
    daily_reports = ResourceRelatedField(
        queryset=DailyReport.objects, required=False, many=True
    )
    multiple_daily_reports = ResourceRelatedField(
        queryset=MultipleDailyReport.objects, required=False, many=True
    )
    measurement_bulletins = ResourceRelatedField(
        queryset=MeasurementBulletin.objects,
        required=False,
        many=True,
        write_only=True,
    )

    class Meta:
        model = DailyReportExport
        fields = [
            "uuid",
            "created_at",
            "created_by",
            "is_compiled",
            "daily_reports",
            "multiple_daily_reports",
            "measurement_bulletins",
            "exported_file",
            "done",
            "error",
            "sort",
            "order",
            "format",
            "export_photos",
        ]

    def validate(self, attrs):
        is_compiled = get_field_if_provided_or_present(
            "is_compiled", attrs, self.instance
        )
        format = get_field_if_provided_or_present("format", attrs, self.instance)
        if is_compiled and format == export_formats.PDF:
            raise serializers.ValidationError(
                "kartado.error.daily_reports.pdf_export_of_compiled_rdo_is_not_supported_yet"
            )

        return super().validate(attrs)

    def create(self, validated_data):
        if (
            "measurement_bulletins" in validated_data
            and validated_data["measurement_bulletins"] != []
        ):
            workers = []
            vehicles = []
            equipments = []
            for bulletin in validated_data["measurement_bulletins"]:
                if bulletin.bulletin_workers.exists():
                    workers.append(
                        list(
                            bulletin.bulletin_workers.values_list(
                                "multiple_daily_reports__uuid", flat=True
                            )
                        )
                    )
                if bulletin.bulletin_vehicles.exists():
                    vehicles.append(
                        list(
                            bulletin.bulletin_vehicles.values_list(
                                "multiple_daily_reports__uuid", flat=True
                            )
                        )
                    )
                if bulletin.bulletin_equipments.exists():
                    equipments.append(
                        list(
                            bulletin.bulletin_equipments.values_list(
                                "multiple_daily_reports__uuid", flat=True
                            )
                        )
                    )
            multiple_daily_reports_uuids = list(
                set(
                    filter(
                        None,
                        flatten(workers) + flatten(vehicles) + flatten(equipments),
                    )
                )
            )
            multiple_daily_reports_bulletins = list(
                MultipleDailyReport.objects.filter(
                    uuid__in=multiple_daily_reports_uuids
                ).distinct()
            )
            if multiple_daily_reports_bulletins == []:
                raise serializers.ValidationError(
                    "kartado.error.daily_report_export.measurement_bulletins_have_no_associated_multiple_daily_reports"
                )
            validated_data["multiple_daily_reports"] = multiple_daily_reports_bulletins
            del validated_data["measurement_bulletins"]
        else:
            try:
                del validated_data["measurement_bulletins"]
            except Exception:
                pass

        instance = super().create(validated_data)
        generate_exported_file(str(instance.uuid))
        return instance


class MultipleDailyReportFileSerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _PREFETCH_RELATED_FIELDS = ["created_by", "multiple_daily_report"]

    uuid = serializers.UUIDField(required=False)
    upload = EmptyFileField()
    upload_url = serializers.SerializerMethodField()

    class Meta:
        model = MultipleDailyReportFile
        fields = [
            "uuid",
            "description",
            "upload",
            "upload_url",
            "uploaded_at",
            "datetime",
            "created_by",
            "md5",
            "kind",
            "multiple_daily_report",
            "legacy_uuid",
        ]
        read_only_fields = ["uploaded_at", "created_by"]
        extra_kwargs = {
            "multiple_daily_report": {
                "required": True,
                "error_messages": {
                    "required": "kartado.error.multiple_daily_report_file.multiple_daily_report_not_found"
                },
            }
        }

    def get_upload_url(self, obj):
        return {}
        # kept this field here to maintain compatibility

    def validate_multiple_daily_report(self, value):
        if value.editable is False:
            raise serializers.ValidationError(
                "kartado.error.multiple_daily_report_file.multiple_daily_report_not_editable"
            )
        return value


class MultipleDailyReportFileObjectSerializer(MultipleDailyReportFileSerializer):
    def get_upload_url(self, obj):
        return get_rdo_file_url(obj)


class MultipleDailyReportSignatureSerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _PREFETCH_RELATED_FIELDS = ["created_by", "multiple_daily_report", "user_signature"]

    uuid = serializers.UUIDField(required=False)
    upload = EmptyFileField()
    upload_url = serializers.SerializerMethodField()

    class Meta:
        model = MultipleDailyReportSignature
        fields = [
            "uuid",
            "signature_name",
            "upload",
            "upload_url",
            "uploaded_at",
            "signature_date",
            "created_by",
            "md5",
            "multiple_daily_report",
            "user_signature",
        ]
        read_only_fields = ["uploaded_at", "created_by"]

    def get_upload_url(self, obj):
        return {}
        # kept this field here to maintain compatibility

    def validate_multiple_daily_report(self, value):
        if value.editable is False:
            raise serializers.ValidationError(
                "kartado.error.multiple_daily_report_signature.multiple_daily_report_not_editable"
            )
        return value

    def handle_user_signature(self, validated_data):
        """
        Handle manipulation of possible non-existent UserSignature while creating
        a new MultipleDailyReportSignature
        """
        FIELD_SERIALIZERS = [("user_signature", UserSignatureSerializer)]

        possible_fields = []
        for field in FIELD_SERIALIZERS:
            (field_name, field_serializer) = field
            field_create_name = "create_" + field_name
            field_edit_name = "edit_" + field_name

            possible_fields.append((field_create_name, field_serializer))
            possible_fields.append((field_edit_name, field_serializer))
        for model_field, model_serializer in possible_fields:
            if model_field in self.initial_data:
                company = validated_data["multiple_daily_report"].company
                item = self.initial_data[model_field]

                if "company" not in self.initial_data and "company" not in item:
                    # Inject company into item
                    item["company"] = OrderedDict(
                        {"type": "Company", "id": str(company.pk)}
                    )
                if "user" not in item:
                    request_user = self.context["request"].user
                    item["user"] = OrderedDict(
                        {"type": "User", "id": str(request_user.pk)}
                    )
                else:
                    request_user = User.objects.get(pk=item["user"]["id"])
                serializer = model_serializer(data=item)
                try:
                    serializer.is_valid(raise_exception=True)
                    related_instance = serializer.save()
                except Exception as e:
                    logging.warning(str(e))
                    sentry_sdk.capture_message(str(e), "warning")

                    related_instance = UserSignature.objects.get(
                        user=request_user, company=company
                    )
                finally:
                    validated_data["user_signature"] = related_instance
        return validated_data

    def create(self, validated_data):
        signature_count = MultipleDailyReportSignature.objects.filter(
            multiple_daily_report=validated_data["multiple_daily_report"]
        ).count()

        if signature_count >= 5:
            raise serializers.ValidationError(
                "kartado.error.multiple_daily_report_signature.max_limit_exceeded"
            )

        uploaded_file_name = validated_data["upload"].name
        is_photo = uploaded_file_name.split(".")[-1].lower() in ["png", "jpeg", "jpg"]

        if not is_photo:
            raise serializers.ValidationError(
                "kartado.error.multiple_daily_report_signature.uploaded_file_is_not_a_photo"
            )
        validated_data = self.handle_user_signature(validated_data)

        return super().create(validated_data)


class MultipleDailyReportSignatureObjectSerializer(
    MultipleDailyReportSignatureSerializer
):
    def get_upload_url(self, obj):
        return get_rdo_file_url(obj)
