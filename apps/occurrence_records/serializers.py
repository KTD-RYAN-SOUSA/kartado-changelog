import copy
import json
import uuid
from datetime import datetime
from urllib import parse

from django.conf import settings
from django.contrib.gis.geos import GeometryCollection
from django.db.models import Prefetch
from fnc.mappings import get
from rest_framework.relations import ManyRelatedField
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import (
    ResourceRelatedField,
    SerializerMethodResourceRelatedField,
)
from simple_history.utils import bulk_create_with_history

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Company, Firm
from apps.locations.models import City
from apps.maps.models import ShapeFile
from apps.monitorings.models import MonitoringCollect, MonitoringPlan
from apps.occurrence_records.const.custom_table import (
    VLR_DAILY,
    VLR_HOURLY,
    VLR_MONTHLY,
)
from apps.occurrence_records.const.property_intersections import (
    MAX_PROPERTY_INTERSECTIONS,
)
from apps.occurrence_records.helpers.get.history import get_record_history
from apps.permissions.models import UserPermission
from apps.service_orders.const import status_types
from apps.service_orders.models import (
    Procedure,
    ServiceOrder,
    ServiceOrderActionStatusSpecs,
)
from apps.users.models import User
from helpers.apis.hidro_api.functions import hidro_api
from helpers.apps.approval_flow import is_currently_responsible
from helpers.apps.companies import is_energy_company
from helpers.apps.json_logic import apply_json_logic
from helpers.apps.monitoring_collect import create_monitoring_collect
from helpers.apps.occurrence_records import (
    create_services,
    get_collection,
    handle_record_panel_show,
    remove_procedure_objects,
)
from helpers.apps.record_panel import send_panel_notifications
from helpers.apps.service_orders import create_procedure_objects
from helpers.fields import FeatureCollectionField
from helpers.forms import get_form_metadata
from helpers.mixins import EagerLoadingMixin, UUIDMixin
from helpers.permissions import PermissionManager
from helpers.serializers import (
    LimitedSizeJsonField,
    LimitedSizeSerializerMethodField,
    get_field_if_provided_or_present,
)
from helpers.sih_integration import set_reading_data
from helpers.sih_table import SihTable
from helpers.strings import (
    check_image_file,
    dict_to_casing,
    get_obj_from_path,
    to_snake_case,
)

from .models import (
    CustomDashboard,
    CustomTable,
    DataSeries,
    OccurrenceRecord,
    OccurrenceRecordWatcher,
    OccurrenceType,
    OccurrenceTypeSpecs,
    RecordPanel,
    RecordPanelShowList,
    RecordPanelShowMobileMap,
    RecordPanelShowWebMap,
    TableDataSeries,
)


class OccurrenceTypeSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        Prefetch("company", queryset=Company.objects.all().only("uuid", "name")),
        Prefetch(
            "occurrencetype_specs__company",
            queryset=Company.objects.all().only("uuid"),
        ),
        Prefetch(
            "monitoring_plan",
            queryset=MonitoringPlan.objects.all().only("uuid"),
        ),
        Prefetch("created_by", queryset=User.objects.all().only("uuid")),
        Prefetch("next_version", queryset=OccurrenceType.objects.all().only("uuid")),
        Prefetch(
            "previous_version",
            queryset=OccurrenceType.objects.all().only("uuid"),
        ),
    ]

    uuid = serializers.UUIDField(required=False)
    company = ResourceRelatedField(queryset=Company.objects, many=True)
    next_version = ResourceRelatedField(many=True, read_only=True)
    color = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = OccurrenceType
        fields = [
            "uuid",
            "name",
            "company",
            "occurrence_kind",
            "form_fields",
            "goal_formula",
            "created_at",
            "updated_at",
            "created_by",
            "deadline",
            "monitoring_plan",
            "previous_version",
            "active",
            "next_version",
            "is_oae",
            "show_in_web_map",
            "show_in_app_map",
            "icon",
            "icon_size",
            "color",
            "custom_map_table",
            "repetition",
        ]

    def get_color(self, obj):
        try:
            # do it this way to avoid query explosion. calling first() or get()
            # will make a new query for each object
            color = next(
                a
                for a in list(obj.occurrencetype_specs.all())
                if a.company.uuid
                == uuid.UUID(self.context["request"].query_params["company"])
            ).color
        except (Exception, StopIteration):
            color = obj.color

        return color

    def create(self, validated_data):
        if "name" in validated_data:
            name = validated_data["name"]
            companies = validated_data["company"]

            for company in companies:
                if OccurrenceType.objects.filter(name=name).filter(company=company):
                    raise serializers.ValidationError(
                        "Tipo de Ocorrência com esse Nome e Unidade já existe"
                    )

        # Remove companies and firms from validated_data.
        companies = validated_data.pop("company")
        firms = validated_data.pop("firms", [])

        # Create object
        occurrence_type = OccurrenceType.objects.create(**validated_data)

        extra_args = {}
        if "color" in self.initial_data:
            extra_args["color"] = self.initial_data["color"]

        # Create OccurrenceTypeSpecs objects
        occurrence_type_specs = [
            OccurrenceTypeSpecs(
                occurrence_type=occurrence_type, company=company, **extra_args
            )
            for company in companies
        ]

        bulk_create_with_history(occurrence_type_specs, OccurrenceTypeSpecs)

        # Save firms relationships after the occurrence_type is created.
        occurrence_type.firms.add(*firms)
        occurrence_type.save()

        return occurrence_type

    def update(self, instance, validated_data):
        if "company" in validated_data:
            validated_data.pop("company")

        if "company_color" in self.initial_data and "color" in self.initial_data:
            company_color = self.initial_data["company_color"]
            color = self.initial_data["color"]

            try:
                occurrence_type_specs = OccurrenceTypeSpecs.objects.get(
                    company_id=company_color["id"], occurrence_type=instance
                )
            except Exception:
                raise serializers.ValidationError(
                    "Não existe cor associada a esse Tipo e Unidade"
                )

            occurrence_type_specs.color = color
            occurrence_type_specs.save()

        return super(OccurrenceTypeSerializer, self).update(instance, validated_data)


class OccurrenceTypeObjectSerializer(OccurrenceTypeSerializer):
    color = serializers.SerializerMethodField()

    class Meta(OccurrenceTypeSerializer.Meta):
        model = OccurrenceType
        fields = OccurrenceTypeSerializer.Meta.fields + ["color"]

    def get_color(self, obj):
        query_params = self._context["request"].query_params

        try:
            user_company = uuid.UUID(query_params["company"])
            occurrence_type_specs = OccurrenceTypeSpecs.objects.get(
                company=user_company, occurrence_type=obj
            )
        except Exception:
            return ""

        return occurrence_type_specs.color


class OccurrenceTypeSpecsSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["company", "occurrence_type"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = OccurrenceTypeSpecs
        fields = [
            "uuid",
            "occurrence_type",
            "company",
            "color",
            "has_no_flow",
            "is_not_listed",
            "is_not_notified",
        ]


class OccurrenceTypeSimpleSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = OccurrenceType
        fields = ["uuid", "name", "occurrence_kind", "form_fields"]


class OccurrenceRecordSerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _PREFETCH_RELATED_FIELDS = [
        "city",
        "location",
        "river",
        "service_orders",
        "status",
        "parent_action",
        "firm",
        "monitoring_points",
        "record_collects",
        "approval_step",
        "approval_step__responsible_users",
        "approval_step__responsible_firms",
        "occurrence_type",
        "created_by",
        "operational_control",
        "operational_control__firm",
        "operational_control__responsible",
        "operational_control__contract",
        "monitoring_plan",
        "responsible",
        "active_tile_layer",
        "company",
        "file",
        "historicaloccurrencerecord",
        "historicaloccurrencerecord__history_user",
        "occurrencerecord_watchers",
        "occurrencerecord_watchers__user",
        "occurrencerecord_watchers__firm",
        "firm__entity__approver_firm",
        Prefetch("active_shape_files", queryset=ShapeFile.objects.all().only("uuid")),
        Prefetch(
            "procedures_mentioned",
            queryset=Procedure.objects.all().only("uuid"),
        ),
        "search_tags",
        "main_linked_record",
        "other_linked_records",
    ]

    uuid = serializers.UUIDField(required=False)
    occurrence_kind = serializers.SerializerMethodField()
    monitoring_status_final = serializers.SerializerMethodField()
    file = ResourceRelatedField(many=True, required=False, read_only=True)
    approved_by = SerializerMethodResourceRelatedField(
        model=User, method_name="get_approved_by", read_only=True
    )
    feature_collection = FeatureCollectionField(
        required=False,
        allow_null=True,
        geometry_field="geometry",
        properties_field="properties",
    )
    watcher_users = SerializerMethodResourceRelatedField(
        model=User, method_name="get_watcher_users", read_only=True, many=True
    )
    watcher_firms = SerializerMethodResourceRelatedField(
        model=Firm, method_name="get_watcher_firms", read_only=True, many=True
    )
    service_orders = ResourceRelatedField(
        queryset=ServiceOrder.objects, required=False, many=True
    )
    record_collects = ResourceRelatedField(
        queryset=MonitoringCollect.objects, required=False, many=True
    )
    is_currently_responsible = serializers.SerializerMethodField()
    procedures = ResourceRelatedField(
        source="procedures_mentioned",
        read_only=False,
        many=True,
        queryset=Procedure.objects,
        required=False,
    )
    procedures_count = serializers.SerializerMethodField()
    history_change_reason = serializers.SerializerMethodField()
    other_linked_records = ResourceRelatedField(
        queryset=OccurrenceRecord.objects, required=False, many=True
    )
    image_count = serializers.SerializerMethodField()
    file_count = serializers.SerializerMethodField()
    form_data = LimitedSizeJsonField(required=False)

    class Meta:
        model = OccurrenceRecord
        fields = [
            "uuid",
            "datetime",
            "number",
            "company",
            "editable",
            "service_orders",
            "uf_code",
            "city",
            "location",
            "place_on_dam",
            "river",
            "point",
            "feature_collection",
            "distance_from_dam",
            "other_reference",
            "origin",
            "origin_media",
            "informer",
            "created_by",
            "operational_control",
            "monitoring_plan",
            "occurrence_kind",
            "search_tags",
            "occurrence_type",
            "form_data",
            "form_metadata",
            "created_at",
            "updated_at",
            "file",
            "status",
            "parent_action",
            "firm",
            "responsible",
            "approved_by",
            "monitoring_points",
            "watcher_users",
            "watcher_firms",
            "approval_step",
            "active_tile_layer",
            "active_shape_files",
            "is_currently_responsible",
            "involved_parts",
            "involved_parts_keywords",
            "procedures",
            "is_approved",
            "territorial_administration",
            "procedures_count",
            "record_collects",
            "monitoring_status_final",
            "history_change_reason",
            "validation_deadline",
            "validated_at",
            "main_linked_record",
            "other_linked_records",
            "properties",
            "image_count",
            "file_count",
            # SearchTag data
            "search_tag_description",
            "record_tag_id",
            "record_tag",
            "record",
            "type_tag_id",
            "type_tag",
            "type",
            "kind_tag_id",
            "kind",
            "subject_tag_id",
            "subject",
        ]
        read_only_fields = [
            "number",
            "editable",
            "created_by",
            "created_at",
            "updated_at",
            "occurrence_kind",
            "approved_by",
            "file",
            "is_currently_responsible",
            "procedures",
            "is_approved",
            "involved_parts_keywords",
            "keywords",
            "monitoring_status_final",
            "history_change_reason",
            "image_count",
            "file_count",
            # SearchTag data
            "record_tag_id",
            "record_tag",
            "record",
            "type_tag_id",
            "type_tag",
            "type",
            "kind_tag_id",
            "kind",
            "subject_tag_id",
            "subject",
        ]
        extra_kwargs = {"company": {"required": False}}

    def get_monitoring_status_final(self, obj):
        try:
            return obj.monitoring_plan.status.is_final
        except Exception:
            return False

    def get_history_change_reason(self, obj):
        try:
            return obj.historicaloccurrencerecord.first().history_change_reason
        except Exception:
            return None

    def get_procedures_count(self, obj):
        procedures_objects = get("form_data.procedure_objects", obj, default=[]) or []
        return len(procedures_objects)

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

    def get_watcher_users(self, obj):
        users = [item.user for item in obj.occurrencerecord_watchers.all() if item.user]
        return list(set(users))

    def get_watcher_firms(self, obj):
        firms = [item.firm for item in obj.occurrencerecord_watchers.all() if item.firm]
        return list(set(firms))

    def get_occurrence_kind(self, obj):
        if obj.occurrence_type:
            try:
                kind = obj.occurrence_type.occurrence_kind
            except Exception:
                kind = None
            return kind
        else:
            return None

    def get_approved_by(self, obj):
        hist = get_record_history(obj)
        if hist is None:
            return
        return hist.history_user

    def get_file_names(self, obj):
        return [str(a.upload) for a in obj.file.all()]

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
        fields = ["watcher_users", "watcher_firms"]
        fields_and_names = [
            ("watcher_users", "user_id"),
            ("watcher_firms", "firm_id"),
        ]

        if set(fields).issubset(self.initial_data.keys()):
            for field, name_id in fields_and_names:
                current_watchers = instance.occurrencerecord_watchers.all()
                current_watchers_ids_list = current_watchers.values_list(
                    name_id, flat=True
                ).distinct()
                current_watchers_ids = [
                    str(item) for item in current_watchers_ids_list if item
                ]

                watcher_objects = self.initial_data.pop(field, [])
                watcher_objects_ids = [item["id"] for item in watcher_objects]

                delete_ids = list(set(current_watchers_ids) - set(watcher_objects_ids))
                add_ids = list(set(watcher_objects_ids) - set(current_watchers_ids))

                name_field = name_id + "__in"
                filter_delete = {
                    name_field: delete_ids,
                    "occurrence_record": instance,
                }

                OccurrenceRecordWatcher.objects.filter(**filter_delete).delete()

                for item in add_ids:
                    filter_add = {
                        name_id: item,
                        "occurrence_record": instance,
                        "created_by": self.context["request"].user,
                    }
                    OccurrenceRecordWatcher.objects.create(**filter_add)

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

        # Remove procedures_objects when record is land_used
        validated_data = remove_procedure_objects(validated_data)

        # Create service_orders from procedures_objects
        validated_data = create_services(validated_data, self.context["request"].user)

        # Hidrologia API
        if "datetime" in validated_data.keys():
            try:
                if "form_data" not in validated_data.keys() or not isinstance(
                    validated_data["form_data"], dict
                ):
                    validated_data["form_data"] = {}
                if "engie_hidrologia" not in validated_data["form_data"].keys():
                    dam = validated_data["company"].metadata.get("company_prefix", "")
                    level = hidro_api(dam, validated_data["datetime"])["response"]
                    validated_data["form_data"]["engie_hidrologia"] = level
            except Exception:
                pass

        # Get the related properties from shape
        geom = validated_data.get("geometry", instance.geometry)

        if geom and "properties_shape" in instance.company.metadata:
            try:
                shape = ShapeFile.objects.get(
                    uuid=instance.company.metadata["properties_shape"]
                )
            except Exception:
                pass
            else:
                intersects = []
                for index, geometry in enumerate(shape.geometry):
                    try:
                        if geometry.intersects(geom):
                            intersects.append((index, geometry))
                    except Exception:
                        pass

                if len(intersects) > MAX_PROPERTY_INTERSECTIONS:
                    raise serializers.ValidationError(
                        "kartado.error.occurrence_records.provided_geometry_contains_too_many_property_intersections"
                    )

                intersects = [
                    {
                        "geometry": json.loads(geometry[1].json),
                        "attributes": {
                            "uuid": "{}-{}".format(
                                str(shape.uuid),
                                shape.properties[geometry[0]]["OBJECTID"],
                            ),
                            **shape.properties[geometry[0]],
                        },
                    }
                    for geometry in intersects
                ]

                field = "property_intersections"

                if "form_data" in validated_data.keys():
                    validated_data["form_data"][field] = intersects
                else:
                    if isinstance(instance.form_data, dict):
                        instance.form_data.update({field: intersects})
                    else:
                        instance.form_data = {field: intersects}

        return super(OccurrenceRecordSerializer, self).update(instance, validated_data)

    def create(self, validated_data):
        # Remove monitoring_collects from form_data
        monitoring_collects = validated_data.get("form_data", {}).pop(
            "monitoring_collects", []
        )

        # Auto fill form_metadata
        occurrence_type = validated_data.get("occurrence_type", None)
        if occurrence_type:
            form_data = validated_data.get("form_data", {})
            validated_data["form_metadata"] = get_form_metadata(
                form_data,
                validated_data["occurrence_type"],
                validated_data.get("form_metadata", {}),
            )

        # Auto fill firm
        if "firm" not in validated_data:
            user = self.context["request"].user
            validated_data["firm"] = user.user_firms.filter(
                company=validated_data["company"]
            ).first()

        # Auto fill status
        try:
            has_no_flow = (
                validated_data["occurrence_type"]
                .occurrencetype_specs.filter(company=validated_data["company"])[0]
                .has_no_flow
            )
        except Exception:
            has_no_flow = False

        if "status" not in validated_data:
            if has_no_flow:
                status_filter = {
                    "company": validated_data["company"],
                    "status__kind": status_types.OCCURRENCE_RECORD_STATUS,
                    "status__name__icontains": "registro deferido",
                }
            else:
                status_filter = {
                    "company": validated_data["company"],
                    "status__kind": status_types.OCCURRENCE_RECORD_STATUS,
                    "order": 1,
                }
            try:
                status = ServiceOrderActionStatusSpecs.objects.filter(**status_filter)[
                    0
                ].status
            except Exception:
                pass
            else:
                validated_data["status"] = status

        # Auto fill service_order
        add_service_order = None
        if (
            "service_order" not in validated_data
            and "parent_action" in validated_data
            and validated_data["parent_action"]
        ):
            add_service_order = validated_data["parent_action"].service_order

        # Auto fill geometry
        if ("geometry" not in validated_data or not validated_data["geometry"]) and (
            "point" in validated_data and validated_data["point"]
        ):
            validated_data["geometry"] = GeometryCollection(validated_data["point"])
            validated_data["properties"] = [{}]

        # Remove M2Ms from data
        watcher_users = self.initial_data.pop("watcher_users", [])
        watcher_firms = self.initial_data.pop("watcher_firms", [])
        active_shape_files = validated_data.pop("active_shape_files", [])
        search_tags = validated_data.pop("search_tags", [])
        monitoring_points = validated_data.pop("monitoring_points", [])

        # Hidrologia API
        if "datetime" in validated_data.keys():
            try:
                if "form_data" not in validated_data.keys():
                    validated_data["form_data"] = {}
                if "engie_hidrologia" not in validated_data["form_data"].keys():
                    dam = validated_data["company"].metadata.get("company_prefix", "")
                    level = hidro_api(dam, validated_data["datetime"])["response"]
                    validated_data["form_data"]["engie_hidrologia"] = level
            except Exception:
                pass

        # Auto fill ApprovalStep
        if not has_no_flow:
            try:
                if "monitoring_plan" in validated_data:
                    approval_step = ApprovalStep.objects.filter(
                        approval_flow__company=validated_data["company"],
                        approval_flow__target_model="occurrence_records.OccurrenceRecord",
                        approval_flow__name__icontains="monitoramento",
                        previous_steps__isnull=True,
                    ).first()
                else:
                    approval_step = ApprovalStep.objects.filter(
                        approval_flow__company=validated_data["company"],
                        approval_flow__target_model="occurrence_records.OccurrenceRecord",
                        previous_steps__isnull=True,
                    ).first()
                validated_data["approval_step"] = approval_step
            except Exception:
                pass

        # Get the related properties from shape
        if (
            "geometry" in validated_data
            and validated_data["geometry"]
            and "properties_shape" in validated_data["company"].metadata
        ):
            try:
                shape = ShapeFile.objects.get(
                    uuid=validated_data["company"].metadata["properties_shape"]
                )
            except Exception:
                pass
            else:
                intersects = []
                for index, geometry in enumerate(shape.geometry):
                    try:
                        if geometry.intersects(validated_data["geometry"]):
                            intersects.append((index, geometry))
                    except Exception:
                        pass

                if len(intersects) > MAX_PROPERTY_INTERSECTIONS:
                    raise serializers.ValidationError(
                        "kartado.error.occurrence_records.provided_geometry_contains_too_many_property_intersections"
                    )

                intersects = [
                    {
                        "geometry": json.loads(geometry[1].json),
                        "attributes": {
                            "uuid": "{}-{}".format(
                                str(shape.uuid),
                                shape.properties[geometry[0]]["OBJECTID"],
                            ),
                            **shape.properties[geometry[0]],
                        },
                    }
                    for geometry in intersects
                ]

                field = "property_intersections"
                if "form_data" not in validated_data.keys():
                    validated_data["form_data"] = {}
                validated_data["form_data"][field] = intersects

        # Remove procedures_objects when record is land_used
        validated_data = remove_procedure_objects(validated_data)

        # Create service_orders from procedures_objects
        validated_data = create_services(validated_data, self.context["request"].user)

        # Change editable and is_approved flags if record has_no_flow
        if has_no_flow:
            validated_data["editable"] = True
            validated_data["is_approved"] = True

        # Get M2M field before instantiating to avoid problems
        other_linked_records = validated_data.pop("other_linked_records", None)

        # Fill SearchTag related fields
        if search_tags:
            for tag in search_tags:
                tag_name = tag.name
                tag_id = str(tag.uuid)

                if tag.level == 1:
                    occ_kind = (
                        occurrence_type.occurrence_kind if occurrence_type else None
                    )

                    validated_data.update(
                        {
                            "record_tag_id": tag_id,
                            "record_tag": tag_name,
                            "record": tag_name if tag_name else occ_kind,
                        }
                    )
                if tag.level == 2:
                    occ_name = occurrence_type.name if occurrence_type else None

                    validated_data.update(
                        {
                            "type_tag_id": tag_id,
                            "type_tag": tag_name,
                            "type": tag_name if tag_name else occ_name,
                        }
                    )
                if tag.level == 3:
                    validated_data.update(
                        {
                            "kind_tag_id": tag_id,
                            "kind": tag_name,
                        }
                    )
                if tag.level == 4:
                    validated_data.update(
                        {
                            "subject_tag_id": tag_id,
                            "subject": tag_name,
                        }
                    )

        # Create object
        occurrence_record = OccurrenceRecord.objects.create(**validated_data)

        # Add the linked records to the new instance
        if other_linked_records:
            occurrence_record.other_linked_records.add(*other_linked_records)

        # Create procedures from procedures_objects if record has_no_flow
        if has_no_flow:
            occurrence_record, _ = create_procedure_objects(occurrence_record)
            occurrence_record.save()

        # Fill service_orders
        if add_service_order:
            occurrence_record.service_orders.add(add_service_order)

        # Create active_shape_files relationships
        occurrence_record.active_shape_files.add(*active_shape_files)

        # Create search_tags relationships
        occurrence_record.search_tags.add(*search_tags)

        # Create MonitoringPoint relationships
        occurrence_record.monitoring_points.add(*monitoring_points)

        # Create MonitoringCollect objects
        for item in monitoring_collects:
            create_monitoring_collect(item, occurrence_record)

        # Create Watcher objects
        for user in watcher_users:
            OccurrenceRecordWatcher.objects.create(
                occurrence_record=occurrence_record,
                user_id=user["id"],
                created_by=self.context["request"].user,
            )

        for firm in watcher_firms:
            OccurrenceRecordWatcher.objects.create(
                occurrence_record=occurrence_record,
                firm_id=firm["id"],
                created_by=self.context["request"].user,
            )

        return occurrence_record


class OccurrenceRecordObjectSerializer(OccurrenceRecordSerializer):
    history = LimitedSizeSerializerMethodField()

    class Meta(OccurrenceRecordSerializer.Meta):
        model = OccurrenceRecord
        fields = OccurrenceRecordSerializer.Meta.fields + ["history"]

    def get_history(self, obj):
        history_list = []
        for history in obj.history.all():
            history_dict = copy.deepcopy(history.__dict__)

            feature_collection_field = self.fields["feature_collection"]
            try:
                history_dict[
                    "feature_collection"
                ] = feature_collection_field.to_representation(history)
            except Exception:
                history_dict["feature_collection"] = None

            del history_dict["_state"]
            try:
                del history_dict[feature_collection_field.properties_field]
            except Exception:
                pass
            try:
                del history_dict[feature_collection_field.geometry_field]
            except Exception:
                pass
            try:
                history_dict["point"] = {
                    "type": "Point",
                    "coordinates": list(history_dict["point"].coords),
                }
            except AttributeError:
                history_dict["point"] = {"type": "Point", "coordinates": [0, 0]}

            # NOTE: This field can be heavy and it's not used for history operations
            try:
                del history_dict["form_data"]["property_intersections"]
            except Exception:
                pass

            history_list.append(history_dict)

        return history_list


class OccurrenceRecordWatcherSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = [
        "occurrence_record",
        "user",
        "firm",
        "created_by",
        "updated_by",
    ]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = OccurrenceRecordWatcher
        fields = [
            "uuid",
            "occurrence_record",
            "user",
            "firm",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "status_email",
        ]


class OccurrenceRecordGeoSerializer(GeoFeatureModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "parent_action",
        "occurrence_type__occurrencetype_specs__company",
        "occurrence_type",
        "status__status_specs__company",
        "location",
        "city",
        "status",
        "company",
        "monitoring_plan",
        "monitoring_points",
    ]

    color = serializers.SerializerMethodField()
    color_status = serializers.SerializerMethodField()
    status_name = serializers.SerializerMethodField()
    occurrence_type_name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    is_record = serializers.SerializerMethodField()
    feature_collection = serializers.SerializerMethodField()

    class Meta:
        model = OccurrenceRecord
        geo_field = "feature_collection"
        fields = [
            "uuid",
            "color",
            "color_status",
            "occurrence_type",
            "occurrence_type_name",
            "status",
            "status_name",
            "number",
            "datetime",
            "description",
            "is_record",
            "feature_collection",
        ]

    def get_feature_collection(self, obj):
        return get_collection(obj)

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

    def get_status_name(self, obj):
        return obj.status.name if obj.status else ""

    def get_occurrence_type_name(self, obj):
        return obj.occurrence_type.name if obj.occurrence_type else ""

    def get_is_record(self, obj):
        return False if obj.parent_action else True

    def get_description(self, obj):
        if obj.form_data.get("action"):
            description = obj.form_data.get("action")
        else:
            description = ""
            if obj.city and obj.city.name:
                description += "Município: {}.".format(obj.city.name)
            if obj.location and obj.location.name:
                description += " Localidade: {}.".format(obj.location.name)

        return description


class OccurrenceRecordGeoGZIPSerializer(GeoFeatureModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["status", "occurrence_type"]

    status_name = serializers.SerializerMethodField()
    occurrence_type_name = serializers.SerializerMethodField()

    class Meta:
        model = OccurrenceRecord
        geo_field = "geometry"
        fields = ["uuid", "status_name", "occurrence_type_name", "number"]

    def get_status_name(self, obj):
        return obj.status.name if obj.status else ""

    def get_occurrence_type_name(self, obj):
        return obj.occurrence_type.name if obj.occurrence_type else ""


class DashboardOccurrenceRecordSerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    _SELECT_RELATED_FIELDS = ["status"]

    title = serializers.SerializerMethodField()
    status_name = serializers.SerializerMethodField()
    record = serializers.CharField()
    type = serializers.CharField()
    kind = serializers.CharField()
    subject = serializers.CharField()

    class Meta:
        model = OccurrenceRecord
        fields = [
            "uuid",
            "datetime",
            "number",
            "title",
            "status_name",
            "record",
            "type",
            "kind",
            "subject",
        ]

    def get_title(self, obj):
        return obj.search_tag_description

    def get_status_name(self, obj):
        return obj.status.name if obj.status else None


class RecordPanelSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    # select_related para FKs (1 JOIN na query principal)
    _SELECT_RELATED_FIELDS = [
        "content_type",  # Elimina 14 queries N+1
        "created_by",
        "menu",
    ]

    _PREFETCH_RELATED_FIELDS = [
        "viewer_users",
        "viewer_firms",
        "viewer_permissions",
        "editor_users",
        "editor_firms",
        "editor_permissions",
        "editor_subcompanies__subcompany_firms",  # Nested prefetch para get_can_you_edit
        "show_in_list_users",
        "show_in_web_map_users",
        "show_in_app_map_users",
        Prefetch("company", queryset=Company.objects.all().defer("shape")),
    ]

    uuid = serializers.UUIDField(required=False)

    # M2M
    viewer_users = ResourceRelatedField(
        queryset=User.objects, many=True, required=False
    )
    viewer_firms = ResourceRelatedField(
        queryset=Firm.objects, many=True, required=False
    )
    viewer_permissions = ResourceRelatedField(
        queryset=UserPermission.objects, many=True, required=False
    )
    editor_users = ResourceRelatedField(
        queryset=User.objects, many=True, required=False
    )
    editor_firms = ResourceRelatedField(
        queryset=Firm.objects, many=True, required=False
    )
    editor_permissions = ResourceRelatedField(
        queryset=UserPermission.objects, many=True, required=False
    )

    show_in_list = serializers.SerializerMethodField()
    show_in_web_map = serializers.SerializerMethodField()
    show_in_app_map = serializers.SerializerMethodField()

    order = serializers.FloatField(source="panel_order", read_only=True)
    can_you_edit = serializers.SerializerMethodField()
    content_type_name = serializers.SerializerMethodField()

    new_to_user = serializers.SerializerMethodField()

    class Meta:
        model = RecordPanel
        fields = [
            "uuid",
            "name",
            "panel_type",
            "conditions",
            "company",
            "viewer_users",
            "viewer_firms",
            "viewer_permissions",
            "editor_users",
            "editor_firms",
            "editor_permissions",
            "list_columns",
            "list_order_by",
            "kanban_columns",
            "kanban_group_by",
            "created_at",
            "created_by",
            "show_in_list",
            "show_in_web_map",
            "show_in_app_map",
            "order",
            "can_you_edit",
            "content_type_name",
            "icon",
            "icon_size",
            "color",
            "menu",
            "system_default",
            "new_to_user",
        ]
        read_only_fields = [
            "content_type",
        ]

    def validate(self, attrs):
        menu = get_field_if_provided_or_present("menu", attrs, self.instance)
        company = get_field_if_provided_or_present("company", attrs, self.instance)

        if not menu and not is_energy_company(company):
            raise serializers.ValidationError(
                "kartado.error.record_panel.menu_field_is_required"
            )

        return super().validate(attrs)

    def get_content_type_name(self, obj):
        try:
            return obj.content_type.model
        except Exception:
            return ""

    def get_show_in_list(self, obj):
        if getattr(obj, "hidden_menu", False):
            return False

        # Usa annotation da view para evitar N+1
        return getattr(obj, "show_in_list_flag", False)

    def get_show_in_web_map(self, obj):
        if getattr(obj, "hidden_menu", False):
            return False

        # Usa annotation da view para evitar N+1
        return getattr(obj, "show_in_web_map_flag", False)

    def get_show_in_app_map(self, obj):
        if getattr(obj, "hidden_menu", False):
            return False

        # Usa annotation da view para evitar N+1
        return getattr(obj, "show_in_app_map_flag", False)

    def get_can_you_edit(self, obj):
        request_user = self.context["request"].user
        user_permissions = (
            self.context["user_permissions"]
            if "user_permissions" in self.context
            else []
        )
        user_firms = self.context["user_firms"] if "user_firms" in self.context else []
        is_creator = request_user == obj.created_by

        # Usa prefetch_related cache - .all() não faz query se prefetchado
        editor_users_list = list(obj.editor_users.all())
        editor_firms_list = list(obj.editor_firms.all())
        editor_permissions_list = list(obj.editor_permissions.all())
        editor_subcompanies_list = list(obj.editor_subcompanies.all())

        is_editor = request_user in editor_users_list
        part_of_editor_firm = any(firm.pk in user_firms for firm in editor_firms_list)
        has_editor_user_permission = any(
            perm.pk in user_permissions for perm in editor_permissions_list
        )
        has_editor_subcompanies_permission = any(
            any(firm.pk in user_firms for firm in subcomp.subcompany_firms.all())
            for subcomp in editor_subcompanies_list
        )

        return any(
            [
                is_creator,
                is_editor,
                part_of_editor_firm,
                has_editor_user_permission,
                has_editor_subcompanies_permission,
            ]
        )

    def handle_show_fields(self, instance: RecordPanel):
        user = self.context["request"].user
        menu = instance.menu
        hidden_menu = (
            menu.recordmenurelation_set.filter(
                user=self.context["request"].user, hide_menu=True
            ).exists()
            if menu
            else False
        )

        # List
        new_show_in_list = self.initial_data.get("show_in_list", None)
        show_in_list = instance.show_in_list_users.filter(uuid=user.uuid).exists()
        if show_in_list != new_show_in_list:
            if hidden_menu:
                raise serializers.ValidationError(
                    "kartado.error.record_panel.cant_edit_show_in_list_for_panels_of_hidden_menus"
                )

            handle_record_panel_show(
                RecordPanelShowList,
                instance,
                new_show_in_list,
                user,
                use_order=True,
                menu=menu,
            )

        # Web Map
        new_show_in_web_map = self.initial_data.get("show_in_web_map", None)
        show_in_web_map = instance.show_in_web_map_users.filter(uuid=user.uuid).exists()
        if show_in_web_map != new_show_in_web_map:
            handle_record_panel_show(
                RecordPanelShowWebMap, instance, new_show_in_web_map, user
            )

        # Mobile Map
        new_show_in_app_map = self.initial_data.get("show_in_app_map", None)
        show_in_app_map = instance.show_in_app_map_users.filter(uuid=user.uuid).exists()
        if show_in_app_map != new_show_in_app_map:
            handle_record_panel_show(
                RecordPanelShowMobileMap,
                instance,
                new_show_in_app_map,
                user,
            )

    def create(self, validated_data):
        company = validated_data["company"]
        record_panel_count = RecordPanel.objects.filter(company=company).count()
        if record_panel_count >= 200:
            raise serializers.ValidationError(
                "kartado.error.record_panel.reached_limited_200"
            )
        new_instance = super().create(validated_data)
        self.handle_show_fields(new_instance)
        send_panel_notifications(new_instance)
        return new_instance

    def update(self, instance, validated_data):
        if not self.get_can_you_edit(instance):
            validated_data = {}

        updated_instance = super().update(instance, validated_data)
        self.handle_show_fields(updated_instance)
        return updated_instance

    def get_new_to_user(self, obj):
        # Usa annotation da view para evitar N+1
        return getattr(obj, "new_to_user_flag", False)


class CustomDashboardSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company", "created_by"]
    _PREFETCH_RELATED_FIELDS = [
        "instrument_types",
        "instrument_records",
        "sih_monitoring_points",
        "can_be_viewed_by",
        "can_be_edited_by",
        "sih_monitoring_parameters",
        "cities",
    ]

    uuid = serializers.UUIDField(required=False)

    instrument_types = ResourceRelatedField(
        queryset=OccurrenceType.objects, many=True, required=False
    )
    instrument_records = ResourceRelatedField(
        queryset=OccurrenceRecord.objects, many=True, required=False
    )
    sih_monitoring_points = ResourceRelatedField(
        queryset=OccurrenceRecord.objects, many=True, required=False
    )
    sih_monitoring_parameters = ResourceRelatedField(
        queryset=OccurrenceRecord.objects, many=True, required=False
    )
    cities = ResourceRelatedField(queryset=City.objects, many=True, required=False)

    instrument_types_urls = serializers.SerializerMethodField(read_only=True)
    instrument_records_urls = serializers.SerializerMethodField(read_only=True)
    sih_monitoring_points_urls = serializers.SerializerMethodField(read_only=True)
    sih_monitoring_parameters_urls = serializers.SerializerMethodField(read_only=True)

    can_you_edit = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CustomDashboard
        fields = [
            "uuid",
            "name",
            "description",
            "created_at",
            "operational_positions",
            "plot_descriptions",
            "created_by",
            "company",
            "instrument_types",
            "instrument_types_urls",
            "instrument_records",
            "instrument_records_urls",
            "sih_monitoring_points",
            "sih_monitoring_points_urls",
            "can_be_viewed_by",
            "can_be_edited_by",
            "can_you_edit",
            "sih_monitoring_parameters",
            "sih_monitoring_parameters_urls",
            "hidro_basins",
            "cities",
            "sih_frequency",
            "start_date_hydrological_parameters",
            "end_date_hydrological_parameters",
        ]

    def get_instrument_types_urls(self, obj):
        if obj.instrument_types.exists():
            types_urls = []
            types_values = obj.instrument_types.values_list(
                "uuid",
                "name",
                "type_records__company",
                "type_records__operational_control",
                "type_records__operational_control__firm__company",
            ).distinct()

            base_url_template = (
                settings.FRONTEND_URL + "/#/OperationalControl/{}/show/3?"
            )

            for (
                type_id,
                name,
                record_company_id,
                op_control_id,
                op_control_company_id,
            ) in types_values:
                company_id = obj.company.uuid

                if (
                    op_control_id
                    and company_id == record_company_id
                    and company_id == op_control_company_id
                ):
                    base_url = base_url_template.format(str(op_control_id))
                    query_values = {
                        "filter": '{{"occurrence_type":"{}"}}'.format(str(type_id)),
                        "order": "DESC",
                        "page": "1",
                        "perPage": "25",
                        "sort": "datetime",
                    }
                    url_query = parse.urlencode(query_values)
                    url = base_url + url_query

                    types_urls.append({"name": name if name else None, "url": url})

            return types_urls
        else:
            return None

    def get_instrument_records_urls(self, obj):
        if obj.instrument_records.exists():
            records_urls = []
            records_values = obj.instrument_records.values_list(
                "uuid", "occurrence_type", "form_data", "operational_control"
            ).distinct()

            base_url_template = (
                settings.FRONTEND_URL + "/#/OperationalControl/{}/show/records?"
            )

            for (
                record_id,
                type_id,
                form_data,
                op_control_id,
            ) in records_values:
                if op_control_id:
                    base_url = base_url_template.format(str(op_control_id))
                    query_values = {
                        "filter": '{{"occurrence_type":"{}","form_data__instrument":["{}"]}}'.format(
                            str(type_id), str(record_id)
                        ),
                        "order": "DESC",
                        "page": "1",
                        "perPage": "25",
                        "sort": "datetime",
                    }
                    url_query = parse.urlencode(query_values)
                    url = base_url + url_query

                    code = get_obj_from_path(form_data, "code")
                    if not code:
                        code = get_obj_from_path(form_data, "unome")

                    records_urls.append({"name": code if code else None, "url": url})

            return records_urls
        else:
            return None

    def get_sih_monitoring_points_urls(self, obj):
        if obj.sih_monitoring_points.exists():
            monitoring_points_urls = []
            monitoring_points_values = obj.sih_monitoring_points.values_list(
                "uuid", "occurrence_type", "form_data", "operational_control"
            ).distinct()
            base_url_template = (
                settings.FRONTEND_URL + "/#/OperationalControl/{}/show/records?"
            )
            for (
                record_id,
                type_id,
                form_data,
                op_control_id,
            ) in monitoring_points_values:
                if op_control_id:
                    base_url = base_url_template.format(str(op_control_id))
                    query_values = {
                        "filter": '{{"occurrence_type":"{}","form_data__instrument":["{}"]}}'.format(
                            str(type_id), str(record_id)
                        ),
                        "order": "DESC",
                        "page": "1",
                        "perPage": "25",
                        "sort": "datetime",
                    }
                    url_query = parse.urlencode(query_values)
                    url = base_url + url_query
                    code = get_obj_from_path(form_data, "code")
                    if not code:
                        code = get_obj_from_path(form_data, "unome")
                    monitoring_points_urls.append(
                        {"name": code if code else None, "url": url}
                    )
            return monitoring_points_urls
        else:
            return None

    def get_sih_monitoring_parameters_urls(self, obj):
        if obj.sih_monitoring_parameters.exists():
            monitoring_urls = []
            monitoring_values = obj.sih_monitoring_parameters.values_list(
                "uuid", "occurrence_type", "form_data", "operational_control"
            ).distinct()

            base_url_template = (
                settings.FRONTEND_URL + "/#/OperationalControl/{}/show/records?"
            )

            for (
                record_id,
                type_id,
                form_data,
                op_control_id,
            ) in monitoring_values:
                if op_control_id:
                    base_url = base_url_template.format(str(op_control_id))
                    query_values = {
                        "filter": '{{"occurrence_type":"{}","form_data__instrument":["{}"]}}'.format(
                            str(type_id), str(record_id)
                        ),
                        "order": "DESC",
                        "page": "1",
                        "perPage": "25",
                        "sort": "datetime",
                    }
                    url_query = parse.urlencode(query_values)
                    url = base_url + url_query

                    code = get_obj_from_path(form_data, "name")

                    monitoring_urls.append({"name": code if code else None, "url": url})

            return monitoring_urls
        else:
            return None

    def get_can_you_edit(self, obj):
        user = self.context["request"].user
        permissions = PermissionManager(
            user=user,
            company_ids=obj.company_id,
            model=self.Meta.model.__name__,
        )
        allowed_queryset = permissions.get_allowed_queryset()

        has_edit_permission = (
            permissions.has_permission(permission="can_edit") if permissions else False
        )
        is_present_in_can_edit_field = obj.can_be_edited_by.filter(
            uuid=user.uuid
        ).exists()
        is_creator = obj.created_by == user if obj.created_by else False

        if "all" in allowed_queryset and has_edit_permission:
            return True
        elif "default" in allowed_queryset and has_edit_permission:
            return is_present_in_can_edit_field or is_creator
        else:
            return False


class DataSeriesSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = [
        "company",
        "instrument_type",
        "instrument_record",
        "sih_monitoring_point",
        "created_by",
        "sih_monitoring_parameter",
    ]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = DataSeries
        fields = [
            "uuid",
            "name",
            "kind",
            "operational_position",
            "field_name",
            "data_type",
            "company",
            "instrument_type",
            "instrument_record",
            "sih_monitoring_point",
            "json_logic",
            "created_at",
            "created_by",
            "sih_monitoring_parameter",
            "sih_frequency",
        ]
        extra_kwargs = {
            "instrument_type": {"required": True},
            "instrument_record": {"required": True},
            "sih_monitoring_point": {"required": True},
        }

    def validate(self, attrs):
        # Check if the field sih_frequency is of the type sih
        kind = get_field_if_provided_or_present("kind", attrs, self.instance)
        sih_frequency = get_field_if_provided_or_present(
            "sih_frequency", attrs, self.instance
        )

        if kind == "SIH" and sih_frequency is None:
            raise serializers.ValidationError(
                "kartado.error.data_series.sih_kind_fields_need_to_fill_sih_frequency_field"
            )

        return super().validate(attrs)


class TableDescriptionsField(serializers.JSONField):
    def get_attribute(self, instance):
        # We pass the object instance onto `to_representation`,
        # not just the field attribute.
        return instance

    def to_representation(self, obj):
        try:
            sih_table = SihTable(table=obj)
            table_descriptions = sih_table.get_table_description()[0]
        except Exception:
            table_descriptions = {
                "header": {"values": []},
                "cells": {"values": []},
            }

        table_desc_data = (
            obj.table_descriptions["data"][0]
            if "data" in obj.table_descriptions and len(obj.table_descriptions["data"])
            else {}
        )

        return {
            **(obj.table_descriptions),
            "data": [
                {
                    **(table_desc_data or {}),
                    "header": {
                        **(
                            table_desc_data["header"]
                            if "header" in table_desc_data
                            else {}
                        ),
                        "values": table_descriptions["header"]["values"],
                    },
                    "cells": {
                        **(
                            table_desc_data["cells"]
                            if "cells" in table_desc_data
                            else {}
                        ),
                        "values": table_descriptions["cells"]["values"],
                    },
                }
            ],
        }


class MyManyRelatedField(ManyRelatedField):
    def to_representation(self, iterable):
        if iterable.exists():
            return self.child_relation.to_representation(iterable.first())
        else:
            return None

    def to_internal_value(self, data):
        return [self.child_relation.to_internal_value(data)]


class CustomTableSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company", "created_by"]
    _PREFETCH_RELATED_FIELDS = [
        "instrument_records",
        "sih_monitoring_points",
        "can_be_viewed_by",
        "can_be_edited_by",
        "cities",
    ]

    uuid = serializers.UUIDField(required=False)

    instrument_records = ResourceRelatedField(
        queryset=OccurrenceRecord.objects, many=True, required=False
    )
    sih_monitoring_points = ResourceRelatedField(
        queryset=OccurrenceRecord.objects, many=True, required=False
    )
    cities = ResourceRelatedField(queryset=City.objects, many=True, required=False)

    instrument_records_urls = serializers.SerializerMethodField(read_only=True)
    sih_monitoring_points_urls = serializers.SerializerMethodField(read_only=True)
    table_data_series_urls = serializers.SerializerMethodField(read_only=True)

    can_you_edit = serializers.SerializerMethodField(read_only=True)
    table_descriptions = TableDescriptionsField()

    instrument_record = MyManyRelatedField(
        child_relation=ResourceRelatedField(
            queryset=OccurrenceRecord.objects,
        ),
        required=False,
        source="instrument_records",
    )
    sih_monitoring_point = MyManyRelatedField(
        child_relation=ResourceRelatedField(
            queryset=OccurrenceRecord.objects,
        ),
        required=False,
        source="sih_monitoring_points",
    )
    table_data_serie = MyManyRelatedField(
        child_relation=ResourceRelatedField(
            queryset=TableDataSeries.objects,
        ),
        required=False,
        source="table_data_series",
    )
    city = MyManyRelatedField(
        child_relation=ResourceRelatedField(
            queryset=City.objects,
        ),
        required=False,
        source="cities",
    )
    start_period = serializers.DateField(required=False, source="_start_period")
    end_period = serializers.DateField(required=False, source="_end_period")

    class Meta:
        model = CustomTable
        fields = [
            "uuid",
            "company",
            "name",
            "description",
            "created_at",
            "created_by",
            "can_be_viewed_by",
            "can_be_edited_by",
            "start_period",
            "end_period",
            "dynamic_period_in_days",
            "table_type",
            "columns_break",
            "line_frequency",
            "hidro_basins",
            "cities",
            "city",
            "instrument_records",
            "instrument_record",
            "instrument_records_urls",
            "sih_monitoring_points",
            "sih_monitoring_point",
            "sih_monitoring_points_urls",
            "additional_columns",
            "additional_lines",
            "table_descriptions",
            "can_you_edit",
            "table_data_series",
            "table_data_serie",
            "table_data_series_urls",
        ]

    def get_instrument_records_urls(self, obj):
        if obj.instrument_records.exists():
            records_urls = []
            records_uuids = obj.instrument_records.values_list(
                "uuid", "form_data"
            ).distinct()

            base_url_template = settings.FRONTEND_URL + "/#/OccurrenceRecord/{}/show"

            for record_id, form_data in records_uuids:
                url = base_url_template.format(str(record_id))
                code = get_obj_from_path(form_data, "unome")

                records_urls.append({"name": code if code else None, "url": url})

            return records_urls
        else:
            return None

    def get_sih_monitoring_points_urls(self, obj):
        if obj.sih_monitoring_points.exists():
            monitoring_points_urls = []
            monitoring_points_uuids = obj.sih_monitoring_points.values_list(
                "uuid", "form_data"
            ).distinct()
            base_url_template = settings.FRONTEND_URL + "/#/OccurrenceRecord/{}/show"
            for record_id, form_data in monitoring_points_uuids:
                url = base_url_template.format(str(record_id))
                code = get_obj_from_path(form_data, "unome")
                monitoring_points_urls.append(
                    {"name": code if code else None, "url": url}
                )
            return monitoring_points_urls
        else:
            return None

    def get_table_data_series_urls(self, obj):
        if obj.table_data_series.exists():
            series_urls = []

            base_url_template = settings.FRONTEND_URL + "/#/OccurrenceRecord/{}/show"

            for data_series in obj.table_data_series.all():
                url = base_url_template.format(
                    str(data_series.sih_monitoring_parameter.uuid)
                )

                series_urls.append({"name": data_series.name, "url": url})

            return series_urls
        else:
            return None

    def get_can_you_edit(self, obj):
        user = self.context["request"].user
        permissions = PermissionManager(
            user=user,
            company_ids=obj.company_id,
            model=self.Meta.model.__name__,
        )
        allowed_queryset = permissions.get_allowed_queryset()

        has_edit_permission = (
            permissions.has_permission(permission="can_edit") if permissions else False
        )
        is_present_in_can_edit_field = obj.can_be_edited_by.filter(
            uuid=user.uuid
        ).exists()
        is_creator = obj.created_by == user if obj.created_by else False

        if "all" in allowed_queryset and has_edit_permission:
            return True
        elif "default" in allowed_queryset and has_edit_permission:
            return is_present_in_can_edit_field or is_creator
        else:
            return False

    def validate(self, attrs):
        dynamic_period_in_days = get_field_if_provided_or_present(
            "dynamic_period_in_days", attrs, self.instance
        )
        end_period = get_field_if_provided_or_present(
            "_end_period", attrs, self.instance
        )
        start_period = get_field_if_provided_or_present(
            "_start_period", attrs, self.instance
        )

        has_defined_static_date = end_period is not None and start_period is not None
        if not has_defined_static_date and dynamic_period_in_days is None:
            if not start_period and not end_period:
                raise serializers.ValidationError(
                    "kartado.error.custom_table.is_required_to_fill_dynamic_period_in_days_for_dynamic_date"
                )
            elif not start_period:
                raise serializers.ValidationError(
                    "kartado.error.custom_table.is_required_to_fill_start_period_for_static_date"
                )
            elif not end_period:
                raise serializers.ValidationError(
                    "kartado.error.custom_table.is_required_to_fill_end_period_for_static_date"
                )

        # If is static date, dynamic_period_in_days should be None
        if has_defined_static_date:
            attrs["dynamic_period_in_days"] = None
        # If is dynamic date, start_period and end_period should be None
        else:
            attrs["_start_period"] = start_period
            attrs["_end_period"] = end_period

        return super().validate(attrs)

    def to_representation(self, instance: CustomTable):
        representation = super().to_representation(instance)
        representation["start_period"] = instance.start_period
        representation["end_period"] = instance.end_period
        return representation


class TableDataSeriesSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = [
        "company",
        "instrument_record",
        "sih_monitoring_point",
        "created_by",
        "sih_monitoring_parameter",
    ]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = TableDataSeries
        fields = [
            "uuid",
            "name",
            "kind",
            "field_name",
            "company",
            "instrument_record",
            "sih_monitoring_point",
            "created_at",
            "created_by",
            "sih_monitoring_parameter",
        ]
        extra_kwargs = {
            "instrument_record": {"required": True},
            "sih_monitoring_point": {"required": True},
        }


class InstrumentMapSerializer(GeoFeatureModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "occurrence_type",
        "occurrence_type__occurrencetype_specs",
        "occurrence_type__occurrencetype_specs__company",
        "occurrence_record_dashboards",
        "company",
    ]

    occurrence_type_name = serializers.SerializerMethodField()
    instrument_color = serializers.SerializerMethodField()
    instrument_data = serializers.SerializerMethodField()
    reading_data = serializers.SerializerMethodField()
    reference_level_info = serializers.SerializerMethodField()
    dashboard_urls = serializers.SerializerMethodField()

    def get_instrument_color(self, obj):
        try:
            # do it this way to avoid query explosion. calling first() or get()
            # will make a new query for each object
            instrument_color = next(
                a
                for a in list(obj.occurrence_type.occurrencetype_specs.all())
                if a.company.uuid
                == uuid.UUID(self.context["request"].query_params["company"])
            ).color
        except (StopIteration, Exception):
            instrument_color = None

        return instrument_color

    def get_occurrence_type_name(self, obj):
        return obj.occurrence_type.name if obj.occurrence_type else None

    def extract_date(self):
        try:
            raw_date = self.context["request"].query_params.get("date")
            if raw_date:
                date = datetime.strptime(raw_date, "%Y-%m-%d")
            else:
                date = None
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.instrument_map.invalid_date_format"
            )
        else:
            return date

    def get_reference_level_info(self, obj):
        if obj.occurrence_type:
            form_fields = obj.occurrence_type.form_fields
            form_fields = dict_to_casing(form_fields, "underscore")

            if "map_color_logic" in form_fields:
                color_logic = form_fields["map_color_logic"]
                input_data = {
                    "data": self.get_instrument_data(obj),
                    "reading_data": self.get_reading_data(obj),
                }
                (name, color) = apply_json_logic(
                    color_logic, dict_to_casing(input_data)
                )

                return {"name": name, "color": color} if name and color else None

        return None

    def get_instrument_data(self, obj):
        occ_type = obj.occurrence_type
        instrument_data = {}

        if occ_type:
            occ_type_fields = get_obj_from_path(occ_type.form_fields, "fields")
            occ_type_fields = dict_to_casing(occ_type_fields, "underscore")

            form_data_to_show = [
                (to_snake_case(field["api_name"]), field["display_name"])
                for field in occ_type_fields
                if "show_in_map" in field and field["show_in_map"]
            ]
            obj_form_data = dict_to_casing(obj.form_data, "underscore")

            # Handle fixed info
            instrument_data["instrument_code"] = {
                "name": obj_form_data.get("code", None),
                "url": f"/OccurrenceRecord/{obj.uuid}/show",
            }

            # Handle variable form data
            for api_name, display_name in form_data_to_show:
                if api_name in obj_form_data:
                    instrument_data[display_name] = obj_form_data[api_name]

        return dict_to_casing(instrument_data) if instrument_data else None

    def get_reading_data(self, obj):
        reading_data = {}

        record = self.context["latest_readings"][str(obj.uuid)]

        if record:
            occ_type_fields = get_obj_from_path(
                record.occurrence_type_form_fields, "fields"
            )
            occ_type_fields = dict_to_casing(occ_type_fields, "underscore")
            form_data_to_show = [
                (to_snake_case(field["api_name"]), field["display_name"])
                for field in occ_type_fields
                if "show_in_map" in field and field["show_in_map"]
            ]
            obj_form_data = dict_to_casing(record.form_data, "underscore")

            # Handle fixed info
            op_control_kind_options = get_obj_from_path(
                obj.company.custom_options,
                "operationalcontrol__fields__kind__selectoptions__options",
            )
            op_control_kind = next(
                (
                    item["name"]
                    for item in op_control_kind_options
                    if item["value"] == record.operational_control_kind
                ),
                None,
            )

            reading_data["subject"] = {
                "name": op_control_kind,
                "url": (
                    "/OperationalControl/{}/show".format(record.operational_control_id)
                    if record.operational_control_id
                    else None
                ),
            }

            occ_type_uuid = (
                record.occurrence_type_id if record.occurrence_type_id else None
            )
            reading_data["occurrence_type"] = {
                "name": record.occurrence_type_name if occ_type_uuid else None,
                "url": f'/OperationalControl/{record.operational_control_id}/show/3?filter={{"occurrence_type"%3A"{occ_type_uuid}"}}&order=DESC&page=1&perPage=25&sort=datetime',
            }

            reading_data["reading_number"] = {
                "name": record.number if record.number else None,
                "url": "/OccurrenceRecord/{}/show".format(record.uuid),
            }

            # Handle variable form data
            if form_data_to_show:
                for api_name, display_name in form_data_to_show:
                    if api_name in obj_form_data:
                        reading_data[display_name] = obj_form_data[api_name]

        return dict_to_casing(reading_data) if reading_data else None

    def get_dashboard_urls(self, obj):
        dashboard_urls = [
            {
                "name": dashboard.name,
                "url": "/Dashboard?tab=customDashboard&uuid={}".format(dashboard.uuid),
            }
            for dashboard in obj.occurrence_record_dashboards.all()
        ]

        return dashboard_urls

    class Meta:
        model = OccurrenceRecord
        geo_field = "geometry"
        fields = [
            "uuid",
            "geometry",
            "instrument_data",
            "reading_data",
            "occurrence_type_name",
            "instrument_color",
            "reference_level_info",
            "dashboard_urls",
        ]


class SIHMonitoringPointMapSerializer(GeoFeatureModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "occurrence_type",
        "occurrence_type__occurrencetype_specs",
        "occurrence_type__occurrencetype_specs__company",
        "occurrence_record_dashboards",
        "occurrence_record_tables",
        "company",
        "operational_control",
    ]
    instrument_data = serializers.SerializerMethodField()
    parameter_data = serializers.SerializerMethodField()
    reading_data = serializers.SerializerMethodField()
    dashboard_urls = serializers.SerializerMethodField()
    table_urls = serializers.SerializerMethodField()
    point_type = serializers.SerializerMethodField()

    def get_instrument_data(self, obj):
        instrument_data = {}

        company = obj.company

        if obj.operational_control:
            op_control = obj.operational_control
            op_control_kind_options = get_obj_from_path(
                company.custom_options,
                "operationalcontrol__fields__kind__selectoptions__options",
            )
            op_control_kind = next(
                (
                    item["name"]
                    for item in op_control_kind_options
                    if item["value"] == op_control.kind
                ),
                None,
            )

            # Handle fixed info
            instrument_data["subject"] = {
                "name": op_control_kind,
                "url": (
                    "/OperationalControl/{}/show".format(op_control.uuid)
                    if op_control
                    else None
                ),
            }

        if obj.occurrence_type:
            # Handle fixed info
            instrument_data["occurrence_type"] = {
                "name": obj.occurrence_type.name,
                "url": f'/OperationalControl/{op_control.uuid}/show/records?filter={{"occurrence_type"%3A"{obj.occurrence_type.uuid}"}}&order=DESC&page=1&perPage=25&sort=datetime',
            }

            occ_type_fields = get_obj_from_path(
                obj.occurrence_type.form_fields, "fields"
            )
            occ_type_fields = dict_to_casing(occ_type_fields, "underscore")

            form_data_to_show = [
                (to_snake_case(field["api_name"]), field["display_name"])
                for field in occ_type_fields
                if "show_in_map" in field and field["show_in_map"]
            ]
            obj_form_data = dict_to_casing(obj.form_data, "underscore")

            # Handle fixed info
            instrument_data["instrument_code"] = {
                "name": obj_form_data.get("uposto", None),
                "url": f"/OccurrenceRecord/{obj.uuid}/show",
            }

            # Handle variable form data
            for api_name, display_name in form_data_to_show:
                if api_name in obj_form_data:
                    instrument_data[display_name] = obj_form_data[api_name]

        return dict_to_casing(instrument_data) if instrument_data else None

    def get_parameter_data(self, obj):
        all_parameters_dict = self.context.get("all_parameters_dict", None)

        monitored_parameters = ""

        if all_parameters_dict:
            parameters = obj.form_data.get("monitoring_parameters", [])
            parameter_records = [
                all_parameters_dict[a] for a in parameters if a in all_parameters_dict
            ]

            monitored_parameters = ", ".join(
                [
                    "{} ({})".format(a.form_data["name"], a.form_data["unit"])
                    for a in parameter_records
                    if "name" in a.form_data and "unit" in a.form_data
                ]
            )

        parameter_dict = {"Parâmetros monitorados": monitored_parameters}

        return parameter_dict

    def get_reading_data(self, obj):
        reading_data = {}
        all_parameters_dict = self.context.get("all_parameters_dict", None)

        form_data = obj.form_data
        if (
            not form_data
            or "monitoring_parameters_map" not in form_data
            or not all_parameters_dict
        ):
            return {}

        parameters = obj.form_data.get("monitoring_parameters_map", [])
        parameter_records = [
            all_parameters_dict[a] for a in parameters if a in all_parameters_dict
        ]

        vlr_dado_hidromet_diario = self.context.get(VLR_DAILY, {})
        vlr_dado_hidromet_horario = self.context.get(VLR_HOURLY, {})
        vlr_dado_hidromet_mensal = self.context.get(VLR_MONTHLY, {})

        if vlr_dado_hidromet_diario:
            reading_data = set_reading_data(
                parameter_records,
                form_data,
                vlr_dado_hidromet_diario,
                VLR_DAILY,
            )

        elif vlr_dado_hidromet_horario:
            reading_data = set_reading_data(
                parameter_records,
                form_data,
                vlr_dado_hidromet_horario,
                VLR_HOURLY,
            )
        elif vlr_dado_hidromet_mensal:
            reading_data = set_reading_data(
                parameter_records,
                form_data,
                vlr_dado_hidromet_mensal,
                VLR_MONTHLY,
            )

        return reading_data

    def get_dashboard_urls(self, obj):
        dashboard_urls = [
            {
                "name": dashboard.name,
                "url": "/Dashboard?tab=customDashboard&uuid={}".format(dashboard.uuid),
            }
            for dashboard in obj.occurrence_record_dashboards.all()
        ]

        return dashboard_urls

    def get_table_urls(self, obj):
        table_urls = [
            {
                "name": table.name,
                "url": "/Dashboard?tab=customTable&uuid={}".format(table.uuid),
            }
            for table in obj.occurrence_record_tables.all()
        ]

        return table_urls

    def get_point_type(self, obj):
        form_data = obj.form_data
        if "utipo" in form_data and form_data["utipo"]:
            return form_data["utipo"]

    class Meta:
        model = OccurrenceRecord
        geo_field = "geometry"
        fields = [
            "uuid",
            "geometry",
            "instrument_data",
            "parameter_data",
            "reading_data",
            "dashboard_urls",
            "table_urls",
            "point_type",
        ]
