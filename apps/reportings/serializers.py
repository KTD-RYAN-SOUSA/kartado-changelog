import uuid
from collections import OrderedDict
from os.path import splitext

import sentry_sdk
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Max, Prefetch
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import (
    ResourceRelatedField,
    SerializerMethodResourceRelatedField,
)

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Company, Firm, SubCompany
from apps.constructions.models import ConstructionProgress
from apps.daily_reports.models import MultipleDailyReport
from apps.maps.models import ShapeFile
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.helpers.default_menus import (
    create_users_record_menu,
    get_user_max_order,
)
from apps.service_orders.models import ServiceOrderActionStatus
from apps.services.models import Measurement
from apps.templates.models import MobileSync
from apps.users.models import User
from helpers.apps.approval_flow import is_currently_responsible
from helpers.apps.services import create_using_resources
from helpers.fields import EmptyFileField, FeatureCollectionField, ReportingRelatedField
from helpers.files import get_url
from helpers.forms import get_form_metadata
from helpers.mixins import EagerLoadingMixin, UUIDMixin
from helpers.serializers import UUIDSerializerMethodResourceRelatedField
from helpers.strings import (
    COMMON_IMAGE_TYPE,
    check_image_file,
    clean_invalid_characters,
    get_obj_from_path,
)

from .models import (
    RecordMenu,
    RecordMenuRelation,
    Reporting,
    ReportingFile,
    ReportingInReporting,
    ReportingMessage,
    ReportingMessageReadReceipt,
    ReportingRelation,
)
from .notifications import reporting_message_created


class DashboardReportingSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "occurrence_type",
        "status",
        "company",
        "created_by",
        "firm",
    ]

    uuid = serializers.UUIDField(required=False)
    status = ResourceRelatedField(
        queryset=ServiceOrderActionStatus.objects,
        required=True,
        allow_null=False,
    )
    occurrence_type = ResourceRelatedField(
        queryset=OccurrenceType.objects, required=True, allow_null=False
    )

    class Meta:
        model = Reporting
        fields = [
            "uuid",
            "point",
            "occurrence_type",
            "status",
            "number",
            "road_name",
            "km",
            "end_km",
            "form_data",
            "lane",
            "direction",
            "created_by",
            "firm",
            "found_at",
            "updated_at",
            "executed_at",
            "due_at",
            "track",
            "branch",
            "km_reference",
        ]
        read_only_fields = ["number", "created_by", "found_at", "updated_at"]


class LightReportingSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "created_by",
        "status",
        "job",
        "occurrence_type",
        "approval_step",
        "reporting_files",
        "reporting_resources",
        "road",
        "company",
        "firm",
        "firm__subcompany",
        "historicalreporting",
        "historicalreporting__history_user",
        "parent",
        "construction",
    ]

    uuid = serializers.UUIDField(required=False)
    occurrence_kind = serializers.SerializerMethodField()

    class Meta:
        model = Reporting
        fields = [
            "uuid",
            "number",
            "company",
            "road_name",
            "road",
            "end_km",
            "project_km",
            "project_end_km",
            "km",
            "occurrence_type",
            "form_data",
            "occurrence_kind",
            "status",
            "lot",
            "approval_step",
            "point",
            "due_at",
            "construction",
        ]

    def get_occurrence_kind(self, obj):
        if obj.occurrence_type:
            try:
                kind = obj.occurrence_type.occurrence_kind
            except Exception:
                kind = None
            return kind
        else:
            return None


class ReportingSerializer(serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin):
    _PREFETCH_RELATED_FIELDS = [
        "created_by",
        "status",
        "job",
        "occurrence_type",
        "approval_step",
        "approval_step__responsible_users",
        "approval_step__responsible_firms",
        "approval_step__responsible_firms__manager",
        "approval_step__responsible_firms__users",
        "reporting_files",
        "services",
        "reporting_usage__measurement__measurement_services",
        "reporting_usage__service",
        "reporting_resources",
        "road",
        "parent__occurrence_type",
        "company",
        "firm",
        "firm__subcompany",
        "historicalreporting",
        "historicalreporting__history_user",
        "active_inspection",
        "active_inspection__occurrence_type",
        "active_inspection_of_inventory",
        "construction",
        "reporting_construction_progresses__construction",
        "pdf_import",
        "menu",
        "reporting_construction_progresses",
        "reporting_relation_parent",
        "reporting_relation_parent__child",
        "reporting_relation_parent__child__occurrence_type",
        "reporting_relation_child",
        "active_tile_layer",
        Prefetch("active_shape_files", queryset=ShapeFile.objects.all().only("uuid")),
    ]

    occurrence_kind = serializers.SerializerMethodField()
    parent_kind = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    measurement = SerializerMethodResourceRelatedField(
        model=Measurement, method_name="get_measurement", read_only=True
    )
    uuid = serializers.UUIDField(required=False)
    reporting_files = ResourceRelatedField(many=True, read_only=True)
    services = ResourceRelatedField(many=True, read_only=True, required=False)
    reason = serializers.CharField(required=False, write_only=True)
    parent = ReportingRelatedField(
        many=False,
        read_only=False,
        required=False,
        queryset=Reporting.objects,
        extra_allowed_types=["Inventory"],
        type_lookup_path="occurrence_type.occurrence_kind",
        type_lookup_map={"1": "Reporting", "2": "Inventory"},
        allow_null=True,
    )
    active_inspection = ReportingRelatedField(
        many=False,
        read_only=False,
        required=False,
        queryset=Reporting.objects,
        extra_allowed_types=["Inventory"],
        type_lookup_path="occurrence_type.occurrence_kind",
        type_lookup_map={"1": "Reporting", "2": "Inventory"},
    )
    active_inspection_of_inventory = ReportingRelatedField(
        many=True,
        read_only=True,
        type_lookup_path="occurrence_type.occurrence_kind",
        type_lookup_map={"1": "Reporting", "2": "Inventory"},
    )
    image_count = serializers.SerializerMethodField()
    file_count = serializers.SerializerMethodField()
    last_history_user = SerializerMethodResourceRelatedField(
        model=User, method_name="get_last_history_user", read_only=True
    )
    is_currently_responsible = serializers.SerializerMethodField()
    subcompany = SerializerMethodResourceRelatedField(
        model=SubCompany, method_name="get_subcompany", read_only=True, many=False
    )
    recuperation_occurrence_types = UUIDSerializerMethodResourceRelatedField(
        model=OccurrenceType,
        method_name="get_recuperation_occurrence_types",
        read_only=True,
        many=True,
    )
    shared_with_agency = serializers.SerializerMethodField()
    inspection_with_recuperations = serializers.SerializerMethodField()

    status_inspection_with_recuperations = serializers.SerializerMethodField()

    feature_collection = FeatureCollectionField(
        required=False,
        allow_null=True,
        geometry_field="geometry",
        properties_field="properties",
    )

    history_change_reason = serializers.SerializerMethodField()

    manual_geometry = serializers.BooleanField(write_only=True, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        view = self.context.get("view")

        if self.__class__.__name__ == "ReportingObjectSerializer":
            return

        if request and request.method != "GET":
            return

        if request and request.method == "GET":
            if view and hasattr(view, "action"):
                if view.action == "retrieve":
                    return

            include_geometry = request.query_params.get("include_geometry", "").lower()
            if include_geometry != "true":
                self.fields.pop("feature_collection", None)

    class Meta:
        model = Reporting
        fields = [
            "uuid",
            "number",
            "company",
            "road_name",
            "road",
            "km",
            "project_km",
            "point",
            "feature_collection",
            "direction",
            "lane",
            "created_by",
            "firm",
            "occurrence_type",
            "form_data",
            "form_metadata",
            "created_at",
            "updated_at",
            "executed_at",
            "due_at",
            "found_at",
            "occurrence_kind",
            "parent_kind",
            "status",
            "reporting_files",
            "job",
            "parent",
            "reason",
            "services",
            "measurement",
            "price",
            "end_km",
            "project_end_km",
            "image_count",
            "file_count",
            "due_at_manually_specified",
            "end_km_manually_specified",
            "project_end_km_manually_specified",
            "approval_step",
            "last_history_user",
            "editable",
            "is_currently_responsible",
            "lot",
            "city",
            "track",
            "branch",
            "address",
            "km_reference",
            "active_inspection",
            "active_inspection_of_inventory",
            "technical_opinion",
            "construction",
            "pdf_import",
            "subcompany",
            "recuperation_occurrence_types",
            "inspection_with_recuperations",
            "status_inspection_with_recuperations",
            "history_change_reason",
            "menu",
            "shared_with_agency",
            "active_tile_layer",
            "active_shape_files",
            "manual_geometry",
        ]
        read_only_fields = [
            "number",
            "editable",
            "created_by",
            "created_at",
            "updated_at",
            "occurrence_kind",
            "parent_kind",
            "reporting_files",
            "children",
            "services",
            "measurement",
            "image_count",
            "file_count",
            "end_km_manually_specified",
            "project_end_km_manually_specified",
            "is_currently_responsible",
            "city",
            "inspection_with_recuperations",
            "status_inspection_with_recuperations",
            "history_change_reason",
            "shared_with_agency",
        ]
        # Add company here to use serializer is_valid
        # method when passing just company_id
        extra_kwargs = {
            "services": {"required": False},
            "company": {"required": False},
        }

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        return clean_invalid_characters(representation)

    def to_internal_value(self, data):
        cleaned_data = clean_invalid_characters(data)
        return super().to_internal_value(cleaned_data)

    def get_history_change_reason(self, obj):
        try:
            return obj.historicalreporting.all()[0].history_change_reason
        except Exception:
            return None

    def get_last_history_user(self, obj):
        # Use history[0] to get the latest one,
        # it is ordered naturally by history_date
        history = obj.historicalreporting.all()

        try:
            return history[0].history_user
        except Exception:
            return None

    def get_occurrence_kind(self, obj):
        if obj.occurrence_type:
            try:
                kind = obj.occurrence_type.occurrence_kind
            except Exception:
                kind = None
            return kind
        else:
            return None

    def get_file_names(self, obj):
        is_antt_qs = self.context.get("antt_supervisor_agency", False)
        if is_antt_qs:
            shared_approval_steps = obj.company.metadata.get(
                "shared_approval_steps", []
            )
            return [
                str(a.upload)
                for a in obj.reporting_files.filter(
                    reporting__approval_step__in=shared_approval_steps, is_shared=True
                )
            ]
        return [str(a.upload) for a in obj.reporting_files.all()]

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

    def get_price(self, obj):
        price = 0
        reporting_usage_len = len(obj.reporting_usage.all())
        if reporting_usage_len and obj.reporting_usage.all()[0].measurement:
            measurement_services = obj.reporting_usage.all()[
                0
            ].measurement.measurement_services.all()

            for usage in obj.reporting_usage.all():
                try:
                    service = next(
                        a
                        for a in measurement_services
                        if a.service_id == usage.service_id
                    )
                    price += (
                        usage.amount
                        * service.unit_price
                        * service.adjustment_coefficient
                    )
                except (StopIteration, TypeError):
                    continue
        elif reporting_usage_len:
            services = obj.services.all()
            for usage in obj.reporting_usage.all():
                try:
                    service = next(a for a in services if a.uuid == usage.service.uuid)
                    price += (
                        usage.amount
                        * service.unit_price
                        * service.adjustment_coefficient
                    )
                except (StopIteration, TypeError):
                    continue

        if len(obj.reporting_resources.all()):
            for resource in obj.reporting_resources.all():
                price += resource.total_price

        return round(price, 2)

    def get_parent_kind(self, obj):
        if obj.parent:
            if obj.parent.occurrence_type:
                try:
                    kind = obj.occurrence_type.occurrence_kind
                except Exception:
                    kind = None
                return kind
            else:
                return None
        else:
            return None

    def get_measurement(self, obj):
        if len(obj.reporting_usage.all()) and obj.reporting_usage.all()[0].measurement:
            return obj.reporting_usage.all()[0].measurement
        else:
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

    def get_subcompany(self, obj):
        if obj.firm:
            return obj.firm.subcompany
        return None

    def get_shared_with_agency(self, obj: Reporting):
        has_agency_constructions = False
        for a in obj.reporting_construction_progresses.all():
            if a.construction.origin == "AGENCY":
                has_agency_constructions = True

        return (
            obj.shared_with_agency
            or bool(obj.form_data.get("artesp_code", False))
            or has_agency_constructions
        )

    def get_recuperation_occurrence_types(self, obj):
        recuperation_reporting_relation = get_obj_from_path(
            obj.company.metadata, "recuperation_reporting_relation"
        )
        if recuperation_reporting_relation:
            related_items = [
                a.child.occurrence_type.uuid
                for a in obj.reporting_relation_parent.all()
                if str(a.reporting_relation_id) == recuperation_reporting_relation
                and a.child.occurrence_type is not None
            ]
            return list(set(related_items))
        return []

    def get_inspection_with_recuperations(self, obj):
        inspection_occurrence_kind = get_obj_from_path(
            obj.company.metadata, "inspection_occurrence_kind"
        )
        reporting_relation_metadata = get_obj_from_path(
            obj.company.metadata, "recuperation_reporting_relation"
        )

        if inspection_occurrence_kind and reporting_relation_metadata:
            if isinstance(inspection_occurrence_kind, str):
                inspection_occurrence_kind = [inspection_occurrence_kind]
            has_reporting_in_reporting = False
            for a in obj.reporting_relation_parent.all():
                if str(a.reporting_relation_id) == reporting_relation_metadata:
                    has_reporting_in_reporting = True
            return (
                obj.occurrence_type
                and obj.occurrence_type.occurrence_kind in inspection_occurrence_kind
                and has_reporting_in_reporting
            )
        else:
            return False

    def get_status_inspection_with_recuperations(self, obj):
        inspection_occurrence_kind = get_obj_from_path(
            obj.company.metadata, "inspection_occurrence_kind"
        )
        reporting_relation_metadata = get_obj_from_path(
            obj.company.metadata, "recuperation_reporting_relation"
        )
        if obj.occurrence_type:
            if isinstance(inspection_occurrence_kind, str):
                inspection_occurrence_kind = [inspection_occurrence_kind]
            if obj.occurrence_type.occurrence_kind in inspection_occurrence_kind:
                therapy = obj.form_data.get("therapy", [])
                occ_ids = [item.get("occurrence_type", "") for item in therapy]
                not_filled_therapy = not therapy or not any(occ_ids)

                created_recuperations_with_relation = getattr(
                    obj, "created_recuperations_with_relation", None
                )

                if created_recuperations_with_relation is None:
                    if not_filled_therapy:
                        return "02"
                    return "10"
                elif (
                    isinstance(created_recuperations_with_relation, bool)
                    and created_recuperations_with_relation
                ):
                    return "20"
                elif (
                    isinstance(created_recuperations_with_relation, bool)
                    and not created_recuperations_with_relation
                ):
                    return "99"
            else:
                reporting_relation_recuperation = False
                for a in obj.reporting_relation_child.all():
                    if str(a.reporting_relation_id) == reporting_relation_metadata:
                        reporting_relation_recuperation = True
                if not reporting_relation_recuperation:
                    return "00"
                else:
                    return "01"
        else:
            return None

    def validate(self, data):
        kms_fields = ["km", "end_km", "project_km", "project_end_km"]
        # kms cannot be negative
        for field in kms_fields:
            if field in data and data[field] and data[field] < 0:
                data[field] = 0

        if "resources" in self.initial_data:
            for resource in self.initial_data["resources"]:
                if "amount" in resource:
                    if not isinstance(resource["amount"], (int, float)):
                        raise serializers.ValidationError(
                            "Campo amount não é um número válido"
                        )

        return data

    def update(self, instance, validated_data):
        # Verify if occurrence_type will become an inventory (occurrence_kind == "2")
        # Inventories cannot be inside a Job
        new_occurrence_type = validated_data.get("occurrence_type")
        if new_occurrence_type is not None:
            if new_occurrence_type.occurrence_kind == "2" and instance.job is not None:
                raise serializers.ValidationError(
                    "kartado.error.inventory_in_job_exception"
                )

        if (
            "end_km" in validated_data
            and validated_data["end_km"] is not None
            and validated_data["end_km"] != instance.end_km
        ):
            validated_data["end_km_manually_specified"] = True

        if "end_km" in validated_data and validated_data["end_km"] is None:
            validated_data["end_km_manually_specified"] = False

        if (
            "project_end_km" in validated_data
            and validated_data["project_end_km"] is not None
            and validated_data["project_end_km"] != instance.project_end_km
        ):
            validated_data["project_end_km_manually_specified"] = True

        if (
            "project_end_km" in validated_data
            and validated_data["project_end_km"] is None
        ):
            validated_data["project_end_km_manually_specified"] = False

        if "project_km" in validated_data and validated_data["project_km"] is None:
            validated_data["project_end_km_manually_specified"] = False

        if "resources" in self.initial_data:
            resource_list = {
                resource["id"]: resource["amount"]
                for resource in self.initial_data["resources"]
                if "id" in resource and "amount" in resource
            }
            create_using_resources(instance, resource_list)

        # Auto fill form_metadata
        occurrence_type = (
            validated_data.get("occurrence_type", False) or instance.occurrence_type
        )
        form_metadata = (
            validated_data.get("form_metadata", {}) or instance.form_metadata
        )
        if occurrence_type:
            validated_data["form_metadata"] = get_form_metadata(
                validated_data.get("form_data", {}),
                occurrence_type,
                form_metadata,
                instance.form_data,
            )

        if (
            "due_at" in validated_data
            and validated_data["due_at"] is not None
            and validated_data["due_at"] != instance.due_at
        ):
            validated_data["due_at_manually_specified"] = True
        else:
            if "found_at" in validated_data:
                found_at = validated_data["found_at"]
                found_at_has_changed = validated_data["found_at"] != instance.found_at
            else:
                found_at = instance.found_at
                found_at_has_changed = False

            type_has_changed = occurrence_type != instance.occurrence_type

            if (found_at_has_changed or type_has_changed) and (
                not instance.due_at_manually_specified
            ):
                if occurrence_type.deadline:
                    validated_data["due_at"] = found_at + occurrence_type.deadline
                else:
                    validated_data["due_at"] = None

        # Send MobileSync to be saved in history signal
        if "mobile_sync" in self.initial_data:
            try:
                instance.mobile_sync = MobileSync.objects.get(
                    pk=self.initial_data["mobile_sync"]["id"]
                )
            except Exception:
                pass

        # Change reason update
        reason = ""
        if "reason" in validated_data.keys():
            reason = validated_data.pop("reason")
        instance._change_reason = reason

        if "create_self_relations" in self.initial_data:
            for item in self.initial_data["create_self_relations"]:
                try:
                    parent = Reporting.objects.get(uuid=item["parent"])
                    child = Reporting.objects.get(uuid=item["child"])
                    reporting_relation = ReportingRelation.objects.get(
                        uuid=item["reporting_relation"]
                    )
                    ReportingInReporting.objects.create(
                        parent=parent,
                        child=child,
                        reporting_relation=reporting_relation,
                    )
                except Exception:
                    raise serializers.ValidationError(
                        "kartado.error.reporting_in_reporting.invalid_link"
                    )
        if "delete_self_relations" in self.initial_data:
            uuid_list = [
                item["uuid"] for item in self.initial_data["delete_self_relations"]
            ]
            ReportingInReporting.objects.filter(uuid__in=uuid_list).delete()

        reporting = super(ReportingSerializer, self).update(instance, validated_data)

        # Add Reporting to RDO if exists
        possible_path = "field_to_automatically_link_reportings_to_rdo"
        field_to_link_rdo = get_obj_from_path(reporting.company.metadata, possible_path)
        if not field_to_link_rdo:
            field_to_link_rdo = "found_at"
        try:
            multiple_daily_report_at_date = MultipleDailyReport.objects.filter(
                date=getattr(reporting, field_to_link_rdo).date(),
                company=reporting.company,
                firm=reporting.firm,
                editable=True,
            ).first()
        except AttributeError:
            pass
        else:
            if multiple_daily_report_at_date:
                reporting_already_present = (
                    multiple_daily_report_at_date.reportings.filter(
                        pk=reporting.pk
                    ).exists()
                )
                if not reporting_already_present:
                    multiple_daily_report_at_date.reportings.add(reporting)

        return reporting

    def create(self, validated_data):
        company = validated_data["company"]
        active_shape_files = validated_data.pop("active_shape_files", [])
        occurrence_type = validated_data.get("occurrence_type", None)
        is_inventory = (
            occurrence_type.occurrence_kind == "2" if occurrence_type else False
        )

        # Insert fallback menu if not provided (needed for mobile and integrations)
        if validated_data.get("menu", None) is None and not is_inventory:
            fallback_menu = (
                RecordMenu.objects.filter(company=company, system_default=False)
                .order_by("created_at")
                .first()
            )
            if fallback_menu:
                validated_data["menu"] = fallback_menu
            else:
                # Should not be possible under normal usage since we block the deletion of the last menu
                # See RecordMenuPermissions.has_object_permission() for more info
                raise serializers.ValidationError(
                    "kartado.error.reporting.fallback_menu_could_not_be_determined_for_the_reporting"
                )

        if "end_km" in validated_data and validated_data["end_km"] is not None:
            validated_data["end_km_manually_specified"] = True

        if (
            "project_end_km" in validated_data
            and validated_data["project_end_km"] is not None
        ):
            validated_data["project_end_km_manually_specified"] = True

        if "due_at" not in validated_data or (
            "due_at" in validated_data and validated_data["due_at"] is None
        ):
            if (
                "found_at" in validated_data
                and "occurrence_type" in validated_data
                and validated_data["occurrence_type"].deadline
            ):
                validated_data["due_at"] = (
                    validated_data["found_at"]
                    + validated_data["occurrence_type"].deadline
                )
        else:
            validated_data["due_at_manually_specified"] = True

        # Auto fill ApprovalStep
        try:
            approval_step = ApprovalStep.objects.filter(
                approval_flow__company=company,
                approval_flow__target_model="reportings.Reporting",
                previous_steps__isnull=True,
            ).first()
            validated_data["approval_step"] = approval_step
        except Exception:
            pass

        # Auto fill form_metadata
        if (
            "occurrence_type" in validated_data
            and validated_data["occurrence_type"] is not None
        ):
            form_data = validated_data.get("form_data", {})
            validated_data["form_metadata"] = get_form_metadata(
                form_data,
                validated_data["occurrence_type"],
                validated_data.get("form_metadata", {}),
            )

        if "create_self_relations" in self.initial_data:
            for item in self.initial_data["create_self_relations"]:
                if item.get("parent", None) is None and item.get("child", None) is None:
                    raise serializers.ValidationError(
                        "kartado.error.reporting_in_reporting.invalid_link"
                    )
        if "geometry" in validated_data and validated_data["geometry"]:
            validated_data["point"] = validated_data["geometry"].centroid
            validated_data["manual_geometry"] = True

        # Create object
        reporting = Reporting.objects.create(**validated_data)

        # Create active_shape_files relationships
        reporting.active_shape_files.add(*active_shape_files)

        if "create_self_relations" in self.initial_data:
            for item in self.initial_data["create_self_relations"]:
                if item.get("parent", None) is None:
                    item["parent"] = str(reporting.uuid)
                elif item.get("child", None) is None:
                    item["child"] = str(reporting.uuid)
                try:
                    parent = Reporting.objects.get(uuid=item["parent"])
                    child = Reporting.objects.get(uuid=item["child"])
                    reporting_relation = ReportingRelation.objects.get(
                        uuid=item["reporting_relation"]
                    )
                    ReportingInReporting.objects.create(
                        parent=parent,
                        child=child,
                        reporting_relation=reporting_relation,
                    )
                except Exception:
                    raise serializers.ValidationError(
                        "kartado.error.reporting_in_reporting.invalid_link"
                    )

        # Add Reporting to RDO if exists
        possible_path = "field_to_automatically_link_reportings_to_rdo"
        field_to_link_rdo = get_obj_from_path(reporting.company.metadata, possible_path)
        if not field_to_link_rdo:
            field_to_link_rdo = "found_at"
        try:
            multiple_daily_report_at_date = MultipleDailyReport.objects.filter(
                date=getattr(reporting, field_to_link_rdo).date(),
                company=reporting.company,
                firm=reporting.firm,
                editable=True,
            ).first()
        except AttributeError:
            pass
        else:
            if multiple_daily_report_at_date:
                multiple_daily_report_at_date.reportings.add(reporting)

        # Save MobileSync in the history
        if "mobile_sync" in self.initial_data:
            try:
                mobile_sync = MobileSync.objects.get(
                    pk=self.initial_data["mobile_sync"]["id"]
                )
            except Exception:
                pass
            else:
                hist = reporting.history.first()
                hist.mobile_sync = mobile_sync
                hist.save()

        if "resources" in self.initial_data:
            resource_list = {
                resource["id"]: resource["amount"]
                for resource in self.initial_data["resources"]
                if "id" in resource and "amount" in resource
            }
            create_using_resources(reporting, resource_list)

        return reporting


class ReportingObjectSerializer(ReportingSerializer):
    _PREFETCH_RELATED_FIELDS = ReportingSerializer._PREFETCH_RELATED_FIELDS + [
        "children",
        "children__occurrence_type",
    ]
    history = serializers.SerializerMethodField()
    children = ReportingRelatedField(
        many=True,
        read_only=True,
        type_lookup_path="occurrence_type.occurrence_kind",
        type_lookup_map={"1": "Reporting", "2": "Inventory"},
    )

    class Meta(ReportingSerializer.Meta):
        model = Reporting
        fields = ReportingSerializer.Meta.fields + ["history", "children"]

    def get_history(self, obj):
        history_list = []
        for history in obj.history.all():
            history_dict = history.__dict__
            del history_dict["_state"]
            history_dict["point"] = {
                "type": "Point",
                "coordinates": (
                    list(history_dict["point"].coords)
                    if history_dict["point"]
                    else None
                ),
            }
            feature_collection_field = self.fields["feature_collection"]

            try:
                history_dict[
                    "feature_collection"
                ] = feature_collection_field.to_representation(history)
            except Exception:
                history_dict["feature_collection"] = None
            try:
                del history_dict[feature_collection_field.geometry_field]
            except Exception:
                pass
            try:
                del history_dict[feature_collection_field.properties_field]
            except Exception:
                pass
            history_list.append(history_dict)
        return history_list


class ReportingWithInventoryCandidates(ReportingSerializer):
    _PREFETCH_RELATED_FIELDS = ReportingSerializer._PREFETCH_RELATED_FIELDS + [
        "inventory_candidates",
        "inventory_candidates__occurrence_type",
    ]

    inventory_candidates = ReportingRelatedField(
        many=True,
        read_only=False,
        required=False,
        queryset=Reporting.objects,
        extra_allowed_types=["Inventory"],
        type_lookup_path="occurrence_type.occurrence_kind",
        type_lookup_map={"1": "Reporting", "2": "Inventory"},
    )

    class Meta(ReportingSerializer.Meta):
        model = Reporting
        fields = ReportingSerializer.Meta.fields + ["inventory_candidates"]


class ReportingGeoGZIPSerializer(GeoFeatureModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["status", "occurrence_type", "company"]

    status_name = serializers.SerializerMethodField()
    occurrence_type_name = serializers.SerializerMethodField()
    occurrence_type_id = serializers.SerializerMethodField()

    class Meta:
        model = Reporting
        geo_field = "geometry"
        fields = [
            "uuid",
            "status_name",
            "occurrence_type_name",
            "number",
            "occurrence_type_id",
            "found_at",
            "direction",
            "km",
        ]

    def to_representation(self, instance: Reporting):
        rep = super().to_representation(instance)

        if "hides_location" not in self.context:
            metadata = instance.company.metadata if instance.company else {}
            self.context["hides_location"] = get_obj_from_path(
                metadata, "hidereportinglocation"
            )

        if "properties" in rep and self.context["hides_location"] is True:
            try:
                del rep["properties"]["km"]
                del rep["properties"]["direction"]
            except Exception as e:
                sentry_sdk.capture_exception(e)

        return rep

    def get_status_name(self, obj):
        return obj.status.name if obj.status else ""

    def get_occurrence_type_name(self, obj):
        return obj.occurrence_type.name if obj.occurrence_type else ""

    def get_occurrence_type_id(self, obj):
        return str(obj.occurrence_type.uuid) if obj.occurrence_type else ""


class ReportingFileSerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _PREFETCH_RELATED_FIELDS = [
        "reporting",
        "created_by",
        "reporting__occurrence_type",
        Prefetch(
            "reporting__reporting_construction_progresses",
            queryset=ConstructionProgress.objects.filter(construction__origin="AGENCY"),
            to_attr="agency_constructions",
        ),
    ]

    uuid = serializers.UUIDField(required=False)
    upload = EmptyFileField()
    upload_url = serializers.SerializerMethodField()

    reporting = ReportingRelatedField(
        queryset=Reporting.objects,
        extra_allowed_types=["Inventory"],
        type_lookup_path="occurrence_type.occurrence_kind",
        type_lookup_map={"1": "Reporting", "2": "Inventory"},
        required=False,
    )

    shared_with_agency = serializers.SerializerMethodField()

    upload_ext = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ReportingFile
        fields = [
            "uuid",
            "reporting",
            "description",
            "upload",
            "upload_url",
            "uploaded_at",
            "datetime",
            "created_by",
            "include_dnit",
            "include_rdo",
            "km",
            "point",
            "md5",
            "kind",
            "shared_with_agency",
            "is_shared",
            "upload_ext",
        ]
        read_only_fields = [
            "uploaded_at",
            "created_by",
            "shared_with_agency",
            "upload_ext",
        ]

    def get_upload_ext(self, obj):
        if obj.upload and obj.upload.name:
            _, ext = splitext(obj.upload.name)
            return (
                "IMAGE" if ext.replace(".", "").lower() in COMMON_IMAGE_TYPE else "FILE"
            )
        return ""

    def get_upload_url(self, obj):
        return {}
        # kept this field here to maintain compatibility

    def get_shared_with_agency(self, obj: ReportingFile):
        reporting: Reporting = obj.reporting

        return (
            (reporting.shared_with_agency and obj.is_shared)
            or bool(reporting.form_data.get("artesp_code", False))
            or bool(getattr(reporting, "agency_constructions", []))
        )


class ReportingFileObjectSerializer(ReportingFileSerializer):
    def get_upload_url(self, obj):
        return get_url(obj)


class ReportingGeoSerializer(GeoFeatureModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "occurrence_type__occurrencetype_specs__company",
        "status__status_specs__company",
        "company",
    ]

    color = serializers.SerializerMethodField()
    color_status = serializers.SerializerMethodField()
    lane = serializers.SerializerMethodField()
    direction = serializers.SerializerMethodField()
    km = serializers.SerializerMethodField()
    track = serializers.SerializerMethodField()
    branch = serializers.SerializerMethodField()
    km_reference = serializers.SerializerMethodField()

    class Meta:
        model = Reporting
        geo_field = "point"
        fields = [
            "uuid",
            "occurrence_type",
            "status",
            "color",
            "km",
            "direction",
            "lane",
            "color_status",
            "track",
            "branch",
            "km_reference",
        ]

    def get_color_status(self, obj):
        try:
            # do it this way to avoid query explosion. calling first() or get()
            # will make a new query for each object
            color = next(
                a
                for a in list(obj.status.status_specs.all())
                if a.company.uuid
                == uuid.UUID(self.context["request"].query_params["company"])
            ).color
        except (StopIteration, Exception):
            color = ""

        return color

    def get_color(self, obj):
        try:
            # do it this way to avoid query explosion. calling first() or get()
            # will make a new query for each object
            color = next(
                a
                for a in list(obj.occurrence_type.occurrencetype_specs.all())
                if a.company.uuid
                == uuid.UUID(self.context["request"].query_params["company"])
            ).color
        except (StopIteration, Exception):
            color = ""

        return color

    def get_lane(self, obj):
        possible_path = "reporting__fields__lane__selectoptions__options"
        try:
            lane = next(
                a
                for a in get_obj_from_path(obj.company.custom_options, possible_path)
                if a["value"] == obj.lane
            )["name"]
        except (StopIteration, Exception) as e:
            print(str(e))
            lane = ""

        return lane

    def get_track(self, obj):
        possible_path = "reporting__fields__track__selectoptions__options"
        try:
            track = next(
                a
                for a in get_obj_from_path(obj.company.custom_options, possible_path)
                if a["value"] == obj.track
            )["name"]
        except (StopIteration, Exception) as e:
            print(str(e))
            track = ""

        return track

    def get_branch(self, obj):
        possible_path = "reporting__fields__branch__selectoptions__options"
        try:
            branch = next(
                a
                for a in get_obj_from_path(obj.company.custom_options, possible_path)
                if a["value"] == obj.branch
            )["name"]
        except (StopIteration, Exception) as e:
            print(str(e))
            branch = ""

        return branch

    def get_direction(self, obj):
        possible_path = "reporting__fields__direction__selectoptions__options"
        try:
            direction = next(
                a
                for a in get_obj_from_path(obj.company.custom_options, possible_path)
                if a["value"] == obj.direction
            )["name"]
        except (StopIteration, Exception) as e:
            print(str(e))
            direction = ""

        return direction

    def get_km(self, obj):
        start_km = "{:07.3f}".format(obj.km)
        end_km = "{:07.3f}".format(obj.end_km or 0)

        return "{} - {}".format(start_km, end_km)

    def get_km_reference(self, obj):
        if obj.km_reference:
            return "{:07.3f}".format(obj.km_reference)
        else:
            return ""


# This endpoint will be used by a single customer (Eixo SP)
# They will consume GeoJSON data from their ArcGIS solution (SISGIS x SISOAE integration)
# That's the reason for the pretty field names
class ReportingGisIntegrationSerializer(ReportingGeoSerializer):
    _PREFETCH_RELATED_FIELDS = ["occurrence_type", "status", "company"]

    found_at = serializers.DateTimeField(format="%d/%m/%y %H:%M")
    executed_at = serializers.DateTimeField(format="%d/%m/%y %H:%M")
    km = serializers.SerializerMethodField()
    occurrence_kind_name = serializers.SerializerMethodField()
    occurrence_type_name = serializers.SerializerMethodField()
    status_name = serializers.SerializerMethodField()
    artesp_code = serializers.SerializerMethodField()
    link = serializers.SerializerMethodField()

    name_map = {
        "found_at": "Encontrado em",
        "executed_at": "Executado em",
        "number": "Serial",
        "road_name": "Rodovia",
        "km": "km",
        "direction": "Sentido",
        "occurrence_kind_name": "Natureza",
        "occurrence_type_name": "Classe",
        "status_name": "Status",
        "artesp_code": "Código de fiscalização",
        "link": "Link",
    }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        new_data = OrderedDict()
        for name, value in data["properties"].items():
            new_data[self.name_map[name]] = value
        return {**data, "properties": new_data}

    class Meta:
        model = Reporting
        geo_field = "point"
        id_field = "uuid"
        fields = [
            "uuid",
            "found_at",
            "executed_at",
            "number",
            "road_name",
            "km",
            "direction",
            "occurrence_kind_name",
            "occurrence_type_name",
            "status_name",
            "artesp_code",
            "link",
        ]

    def get_km(self, obj):
        return "{:07.3f}".format(obj.km).replace(".", "+")

    def get_occurrence_kind_name(self, obj):
        possible_path = "reporting__fields__occurrence_kind__selectoptions__options"
        try:
            occurrence_kind = next(
                a
                for a in get_obj_from_path(obj.company.custom_options, possible_path)
                if a["value"] == obj.occurrence_type.occurrence_kind
            )["name"]
        except (StopIteration, Exception) as e:
            print(str(e))
            occurrence_kind = ""

        return occurrence_kind

    def get_occurrence_type_name(self, obj):
        return obj.occurrence_type.name if obj.occurrence_type else ""

    def get_status_name(self, obj):
        return obj.status.name if obj.status else ""

    def get_artesp_code(self, obj):
        artesp_code = get_obj_from_path(obj.form_data, "artesp_code")
        return str(artesp_code) if artesp_code != [] else ""

    def get_link(self, obj):
        return "{}/#/SharedLink/Reporting/{}/?company={}".format(
            settings.FRONTEND_URL, str(obj.uuid), str(obj.company.pk)
        )


# This endpoint will be used by a single customer (Eixo SP)
# They will consume GeoJSON data from their ArcGIS solution (SISGIS x SISOAE integration)
# That's the reason for the pretty field names
class InventoryGisIntegrationSerializer(ReportingGeoSerializer):
    _PREFETCH_RELATED_FIELDS = [
        "occurrence_type",
        "status",
        "company",
        "active_inspection",
    ]

    km = serializers.SerializerMethodField()
    occurrence_type_name = serializers.SerializerMethodField()
    functional_classification = serializers.SerializerMethodField()
    structural_classification = serializers.SerializerMethodField()
    wear_classification = serializers.SerializerMethodField()
    link = serializers.SerializerMethodField()

    name_map = {
        "number": "Item de serviço ARTESP",
        "occurrence_type_name": "Tipo da obra",
        "road_name": "Rodovia",
        "km": "km",
        "direction": "Sentido",
        "functional_classification": "Funcional",
        "structural_classification": "Estrutural",
        "wear_classification": "Durabilidade",
        "link": "Link",
    }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        new_data = OrderedDict()
        for name, value in data["properties"].items():
            new_data[self.name_map[name]] = value
        return {**data, "properties": new_data}

    class Meta:
        model = Reporting
        geo_field = "point"
        id_field = "uuid"
        fields = [
            "uuid",
            "number",
            "occurrence_type_name",
            "road_name",
            "km",
            "direction",
            "link",
            "functional_classification",
            "structural_classification",
            "wear_classification",
        ]

    def get_km(self, obj):
        return "{:07.3f}".format(obj.km).replace(".", "+")

    def get_occurrence_type_name(self, obj):
        return obj.occurrence_type.name if obj.occurrence_type else ""

    def get_functional_classification(self, obj):
        if not obj.active_inspection:
            return ""

        functional_classification = get_obj_from_path(
            obj.active_inspection.form_data, "functional_classification"
        )
        return str(functional_classification) if functional_classification != [] else ""

    def get_structural_classification(self, obj):
        if not obj.active_inspection:
            return ""

        structural_classification = get_obj_from_path(
            obj.active_inspection.form_data, "structural_classification"
        )
        return str(structural_classification) if structural_classification != [] else ""

    def get_wear_classification(self, obj):
        if not obj.active_inspection:
            return ""

        wear_classification = get_obj_from_path(
            obj.active_inspection.form_data, "wear_classification"
        )
        return str(wear_classification) if wear_classification != [] else ""

    def get_link(self, obj):
        return "{}/#/SharedLink/Inventory/{}/show?company={}".format(
            settings.FRONTEND_URL, str(obj.uuid), str(obj.company.pk)
        )


class ReportingMessageReadReceiptSerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    _SELECT_RELATED_FIELDS = ["user", "reporting_message"]

    uuid = serializers.UUIDField(required=False)
    user = serializers.ResourceRelatedField(
        queryset=User.objects, default=serializers.CurrentUserDefault()
    )

    class Meta:
        model = ReportingMessageReadReceipt
        fields = ["uuid", "user", "reporting_message", "read_at"]
        extra_kwargs = {"user": {"required": False}}


class ReportingMessageSerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _SELECT_RELATED_FIELDS = ["reporting", "created_by", "created_by_firm"]
    _PREFETCH_RELATED_FIELDS = ["read_by", "mentioned_users", "mentioned_firms"]

    uuid = serializers.UUIDField(required=False)

    read_at = serializers.SerializerMethodField(read_only=True)

    mentioned_users = ResourceRelatedField(
        queryset=User.objects, read_only=False, many=True, required=False
    )
    mentioned_firms = ResourceRelatedField(
        queryset=Firm.objects, read_only=False, many=True, required=False
    )

    class Meta:
        model = ReportingMessage
        fields = [
            "uuid",
            "message",
            "created_at",
            "reporting",
            "created_by",
            "created_by_firm",
            "read_by",
            "read_at",
            "mentioned_users",
            "mentioned_firms",
        ]
        read_only_fields = ["created_by_firm", "created_by", "created_at"]

    def get_read_at(self, obj):
        try:
            # do it this way to avoid query explosion. calling first() or get()
            # will make a new query for each object
            read_at = next(
                a
                for a in list(obj.read_receipts.all())
                if a.reporting_message.reporting.company.uuid
                == uuid.UUID(self.context["request"].query_params["company"])
            ).read_at
        except (Exception, StopIteration):
            read_at = ""

        return read_at

    def update(self, instance, validated_data):
        instance = super(ReportingMessageSerializer, self).update(
            instance, validated_data
        )
        reporting_message_created(instance)
        return instance

    def create(self, validated_data):
        if "created_by_firm" not in validated_data:
            try:
                validated_data["created_by_firm"] = (
                    self.context["request"]
                    .user.user_firms.filter(company=validated_data["reporting"].company)
                    .first()
                )
            except Exception:
                pass

        instance = super(ReportingMessageSerializer, self).create(validated_data)
        reporting_message_created(instance)
        return instance


class HideMenuField(serializers.BooleanField):
    def to_representation(self, value):
        # No need to make more calls if we have it annotated
        if hasattr(value, "user_hidden"):
            return value.user_hidden
        # System default menu is never hidden
        elif value.system_default:
            return False
        # Will make an extra DB call (should only happen on POST/PUT)
        else:
            user = self.parent.context["request"].user
            relation = value.recordmenurelation_set.filter(user=user).first()
            return relation.hide_menu if relation else False

    def to_internal_value(self, data):
        if not isinstance(data, bool):
            self.fail("invalid_type")
        return {"hide_menu": data}


class ContentTypeName(serializers.Field):
    def to_representation(self, value):
        return value.content_type.model if value.content_type else ""

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid_type")

        try:
            content_type = ContentType.objects.get(model=data)
        except Exception:
            self.fail("invalida_content_type")

        return {"content_type": content_type}


class RecordMenuSerializer(serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin):
    _PREFETCH_RELATED_FIELDS = [
        "users",
        "company",
        "created_by",
        "menu_record_panels",
        "content_type",
    ]

    hide_menu = HideMenuField(
        source="*",
        error_messages={"invalid_type": "hide_menu must be a boolean"},
    )
    order = serializers.SerializerMethodField()
    content_type_name = ContentTypeName(
        source="*",
        error_messages={
            "required": "kartado.error.record_menu.need_to_specify_menu_type",
            "invalida_content_type": "invalid content type",
            "invalid_type": "content_type_name must be a string",
        },
    )
    show_as_layer = serializers.SerializerMethodField()

    contains_new_to_user = serializers.SerializerMethodField()

    class Meta:
        model = RecordMenu
        fields = [
            "uuid",
            "name",
            "company",
            "created_by",
            "content_type_name",
            "order",
            "system_default",
            "hide_menu",
            "menu_record_panels",
            "show_as_layer",
            "contains_new_to_user",
        ]
        read_only_fields = [
            "created_by",
            "system_default",
            "menu_record_panels",
            "show_as_layer",
        ]

    def create_user_record_menu_relation(
        self, hide_menu: bool, company, record_menu: RecordMenu
    ):
        max_order = RecordMenuRelation.objects.filter(
            hide_menu=False,
            company=company,
            user=self.context["request"].user,
            record_menu__content_type__model=record_menu.content_type.model,
            record_menu__system_default=False,
        ).aggregate(Max("order"))
        if max_order.get("order__max") is not None:
            next_order = max_order["order__max"] + 1
        else:
            next_order = 0

        user_record_menu = RecordMenuRelation.objects.create(
            record_menu=record_menu,
            company=company,
            hide_menu=hide_menu,
            order=next_order,
            user=self.context["request"].user,
        )

        return user_record_menu

    def get_max_order(self, company: Company, content_type: ContentType):
        max_order = RecordMenu.objects.filter(
            company=company, content_type=content_type, system_default=False
        ).aggregate(Max("order"))
        if max_order.get("order__max") is not None:
            order = max_order["order__max"] + 1
        else:
            order = 0
        return order

    def create(self, validated_data):
        company = validated_data["company"]
        record_menu_count = RecordMenu.objects.filter(company=company).count()
        if record_menu_count >= 20:
            raise serializers.ValidationError(
                "kartado.error.record_menu.reached_limited_20"
            )
        order = self.get_max_order(
            validated_data["company"], validated_data["content_type"]
        )

        request_user = self.context["request"].user
        validated_data["created_by"] = request_user
        validated_data["order"] = order

        hide_menu = validated_data.pop("hide_menu")
        if (
            hide_menu is False
            and RecordMenuRelation.objects.filter(
                company=company, user=request_user, hide_menu=False
            ).count()
            >= 9
        ):
            raise serializers.ValidationError(
                "kartado.error.record_menu.reached_limit_10_visible_menus"
            )
        rm = RecordMenu.objects.create(**validated_data)
        self.create_user_record_menu_relation(hide_menu, validated_data["company"], rm)

        # exclude current user to avoid integrity error
        users_id = validated_data["company"].get_active_users_id()
        users_to_exclude = [validated_data["created_by"].pk]
        create_users_record_menu(
            rm, users_id, validated_data["company"], users_to_exclude
        )

        return rm

    def update_user_hide_menu(self, instance: RecordMenu, hide_menu: bool):
        user = self.context["request"].user
        user_record_menu: RecordMenuRelation = instance.recordmenurelation_set.filter(
            user=user
        ).first()
        current_hide_menu = getattr(user_record_menu, "hide_menu", None)

        if current_hide_menu is None:
            self.create_user_record_menu_relation(
                hide_menu=hide_menu,
                company=instance.company,
                record_menu=instance,
            )

        # NOTE: If current_hide_menu == hide_menu we don't need to change anything
        elif current_hide_menu != hide_menu:
            user_record_menu.hide_menu = hide_menu

            # When showing a menu again, position it at the bottom
            if hide_menu is False:
                user_record_menu.order = get_user_max_order(user, instance.company)

            user_record_menu.save()

    def update(self, instance, validated_data):
        if validated_data.get("hide_menu") is not None:
            self.update_user_hide_menu(instance, validated_data["hide_menu"])

        return super().update(instance, validated_data)

    def get_order(self, obj):
        # No need to make more calls if we have it annotated
        if hasattr(obj, "user_order"):
            return obj.user_order
        # System default menus have global order (bottom of the list)
        elif obj.system_default:
            return obj.order
        # Will make an extra DB call (should only happen on POST/PUT)
        else:
            user = self.context["request"].user
            relation = obj.recordmenurelation_set.filter(user=user).first()
            return relation.order if relation else obj.order

    def get_show_as_layer(self, obj: RecordMenu):
        return getattr(obj, "show_as_layer", False)

    def get_contains_new_to_user(self, obj):
        return getattr(obj, "contains_new_to_user", False)


class ReportingRelationSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["company"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = ReportingRelation
        fields = ["uuid", "company", "name", "outward", "inward"]


class ReportingInReportingSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "parent",
        "parent__occurrence_type",
        "child",
        "child__occurrence_type",
        "reporting_relation",
    ]
    uuid = serializers.UUIDField(required=False)
    parent = ReportingRelatedField(
        many=False,
        read_only=False,
        required=True,
        queryset=Reporting.objects,
        extra_allowed_types=["Inventory"],
        type_lookup_path="occurrence_type.occurrence_kind",
        type_lookup_map={"1": "Reporting", "2": "Inventory"},
    )
    child = ReportingRelatedField(
        many=False,
        read_only=False,
        required=True,
        queryset=Reporting.objects,
        extra_allowed_types=["Inventory"],
        type_lookup_path="occurrence_type.occurrence_kind",
        type_lookup_map={"1": "Reporting", "2": "Inventory"},
    )

    class Meta:
        model = ReportingInReporting
        fields = ["uuid", "parent", "child", "reporting_relation"]
