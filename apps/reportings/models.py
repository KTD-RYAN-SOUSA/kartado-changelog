import copy
import logging
import uuid
from graphlib import CycleError, TopologicalSorter

from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.db.models import JSONField, Max, QuerySet
from django.utils import timezone
from django_bulk_update.helper import bulk_update
from simple_history.models import HistoricalRecords

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Company, Firm
from apps.maps.models import ShapeFile, TileLayer
from apps.occurrence_records.helpers.methods.altimetry_methods import AltimetryMethods
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.helpers.get_form_data import get_value_in_form_fields
from apps.roads.models import Road
from apps.service_orders.models import ServiceOrderActionStatus
from apps.users.models import User
from apps.work_plans.models import Job
from helpers.apps.json_logic import apply_json_logic
from helpers.apps.record_filter import create_keywords
from helpers.forms import form_fields_dict, get_form_metadata
from helpers.km_converter import calculate_end_km
from helpers.models import AbstractBaseModel
from helpers.serializers import get_obj_serialized
from helpers.strings import get_obj_from_path, to_camel_case, to_snake_case
from RoadLabsAPI.storage_backends import PrivateMediaStorage

logger = logging.getLogger(__name__)


class ReportingHistoricalModel(models.Model):
    """
    Abstract model for reporting history to save MobileSync
    """

    mobile_sync = models.ForeignKey(
        "templates.MobileSync",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="sync_historicalreporting",
    )

    class Meta:
        abstract = True


def gather_all_dependencies(autofill: dict) -> list:
    deps = set()

    def _traverse(node):
        if isinstance(node, str):
            if node.startswith("formData."):
                deps.add(node[len("formData.") :])
        elif isinstance(node, dict):
            for v in node.values():
                _traverse(v)
        elif isinstance(node, list):
            for item in node:
                _traverse(item)

    _traverse(autofill)
    return list(deps)


def topological_sort(graph: dict) -> list:
    nodes = set(graph.keys())
    ts_input = {
        node: {dep for dep in deps if dep in nodes} for node, deps in graph.items()
    }
    try:
        return list(TopologicalSorter(ts_input).static_order())
    except CycleError as e:
        logger.warning(
            "Cycle detected in autofill dependency graph, falling back to alphabetical order. Cycle: %s",
            e,
        )
        return sorted(nodes)


def get_dependency_graph(occ: OccurrenceType) -> dict:
    graph = {}
    for field in occ.form_fields["fields"]:
        autofill = field.get("autofill", {})
        graph[field["apiName"]] = gather_all_dependencies(autofill) if autofill else []
    return graph


class Reporting(models.Model, AltimetryMethods):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Basic Information
    number = models.CharField(max_length=100, blank=True)  # Autofill
    company = models.ForeignKey(Company, on_delete=models.CASCADE)  # Required

    # Location
    # Required
    road_name = models.CharField(max_length=50, blank=True)
    road = models.ForeignKey(
        Road, on_delete=models.SET_NULL, null=True, related_name="reportings"
    )

    km = models.FloatField()  # Required
    end_km = models.FloatField(blank=True, null=True)
    km_reference = models.FloatField(blank=True, null=True)

    project_km = models.FloatField(default=0, null=True, blank=True)
    project_end_km = models.FloatField(blank=True, null=True)

    point = models.PointField(null=True, blank=True)
    direction = models.CharField(max_length=100)  # Required
    lane = models.CharField(max_length=100)  # Required

    track = models.TextField(null=True, blank=True)
    branch = models.TextField(null=True, blank=True)

    address = JSONField(default=dict)

    geometry = models.GeometryCollectionField(null=True, blank=True)
    properties = JSONField(default=list, blank=True)
    active_tile_layer = models.ForeignKey(
        TileLayer,
        on_delete=models.SET_NULL,
        related_name="tyle_layer_reportings",
        null=True,
        blank=True,
    )
    active_shape_files = models.ManyToManyField(
        ShapeFile, related_name="shape_file_reportings", blank=True
    )

    manual_geometry = models.BooleanField(default=False)

    # Registerer Autofill
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reportings",
    )

    firm = models.ForeignKey(
        Firm, on_delete=models.SET_NULL, null=True, related_name="reportings"
    )

    # Occurrence Info
    occurrence_type = models.ForeignKey(
        OccurrenceType,
        null=True,
        on_delete=models.SET_NULL,
        related_name="reporting_occurrence",
    )
    form_data = JSONField(default=dict)
    form_metadata = JSONField(default=dict)

    # Key Dates Info
    executed_at = models.DateTimeField(default=None, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    found_at = models.DateTimeField(default=timezone.now)  # Autofill
    due_at = models.DateTimeField(default=None, null=True)

    # Required
    status = models.ForeignKey(
        ServiceOrderActionStatus,
        on_delete=models.SET_NULL,
        null=True,
        related_name="reportings",
    )

    job = models.ForeignKey(
        Job, on_delete=models.SET_NULL, null=True, related_name="reportings"
    )

    services = models.ManyToManyField(
        "services.Service",
        through="services.ServiceUsage",
        related_name="reporting_services",
        blank=True,
    )

    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    active_inspection = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_inspection_of_inventory",
    )

    due_at_manually_specified = models.BooleanField(default=False)
    end_km_manually_specified = models.BooleanField(default=False)
    project_end_km_manually_specified = models.BooleanField(default=False)
    editable = models.BooleanField(default=True)

    approval_step = models.ForeignKey(
        ApprovalStep,
        on_delete=models.SET_NULL,
        related_name="step_reportings",
        null=True,
        blank=True,
    )

    keywords = models.TextField(default="", null=True)
    lot = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=255, blank=True, null=True)

    technical_opinion = models.TextField(blank=True, null=True)

    construction = models.ForeignKey(
        "constructions.Construction",
        related_name="construction_reportings",
        on_delete=models.SET_NULL,
        null=True,
    )

    pdf_import = models.ForeignKey(
        "templates.PDFImport",
        related_name="pdf_import_reportings",
        on_delete=models.SET_NULL,
        null=True,
    )

    menu = models.ForeignKey(
        "reportings.RecordMenu",
        on_delete=models.SET_NULL,
        related_name="record_menu_reportings",
        null=True,
    )

    shared_with_agency = models.BooleanField(default=False, blank=True, null=True)
    self_relations = models.ManyToManyField(
        "self",
        related_name="reporting_self_relations",
        through="ReportingInReporting",
        blank=True,
        symmetrical=False,
    )
    inventory_candidates = models.ManyToManyField(
        "self",
        related_name="inventory_candidates_for",
        blank=True,
        symmetrical=False,
    )

    created_recuperations_with_relation = models.BooleanField(null=True)

    # History Waiting Merge
    history = HistoricalRecords(
        bases=[ReportingHistoricalModel],
        related_name="historicalreporting",
        user_related_name="user_historicalreporting",
        history_change_reason_field=models.TextField(null=True),
    )

    def __str__(self):
        return "[{}] {} - {}".format(self.company.name, self.number, self.found_at)

    def save(self, *args, **kwargs):
        # Refresh end_km
        if not self.end_km_manually_specified:
            self.end_km = calculate_end_km(self)

        # Refresh project_end_km
        if not self.project_end_km_manually_specified:
            self.project_end_km = calculate_end_km(self, project_km=True)
        # Apply logic in form_data fields
        form_data = self.form_data
        self.form_metadata = get_form_metadata(
            form_data, self.occurrence_type, self.form_metadata
        )
        # check if any form field has autofill specified (i.e., manually_specified=False)
        if not all(
            [
                get_obj_from_path(item, "manually_specified")
                for item in self.form_metadata.values()
            ]
        ):
            obj_serialized = get_obj_serialized(self, is_reporting=True)
        else:
            obj_serialized = None

        if obj_serialized:
            form_fields = form_fields_dict(self.occurrence_type)
            dependency_graph = get_dependency_graph(self.occurrence_type)
            topo_order = topological_sort(dependency_graph)
            topo_order = [to_snake_case(key) for key in topo_order]
            topo_set = set(topo_order)
            sorted_form_metadata = {
                key: self.form_metadata[key]
                for key in topo_order
                if key in self.form_metadata
            }
            sorted_form_metadata.update(
                {k: v for k, v in self.form_metadata.items() if k not in topo_set}
            )

            for key, value in sorted_form_metadata.items():
                manually_specified = get_obj_from_path(value, "manually_specified")
                if isinstance(manually_specified, bool) and not manually_specified:
                    # use get_obj_from_path here to avoid crashes
                    # when key gets here in snake_case but field name is camelCase
                    # If unable to get form_field or unable to compute jsonLogic, don't crash
                    form_field = get_obj_from_path(form_fields, key)
                    if isinstance(form_field, dict):
                        autofill = form_field.get("autofill", {})
                        try:
                            self.form_data[key] = apply_json_logic(
                                autofill,
                                obj_serialized,
                                self.occurrence_type,
                                self.company,
                            )
                        except Exception:
                            logger.warning(
                                "Failed to apply autofill for field '%s'",
                                key,
                                exc_info=True,
                            )
                            continue
                        obj_serialized["formData"][to_camel_case(key)] = self.form_data[
                            key
                        ]

        super(Reporting, self).save(*args, **kwargs)

        # Refresh keywords with expanded searchable data
        if self.occurrence_type:
            self.keywords = create_keywords(self.form_data, self.occurrence_type, self)
        if self.keywords:
            bulk_update([self], update_fields=["keywords"])

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["uuid"]

    def get_form_data_display(self) -> dict:
        form_fields = self.occurrence_type.form_fields
        _form_data = copy.deepcopy(
            self.form_data if isinstance(self.form_data, dict) else {}
        )

        for k, v in _form_data.items():
            _form_data[k] = get_value_in_form_fields(k, v, form_fields) or v
        return _form_data

    def get_single_form_data_display(self, field_name, default="") -> dict:
        form_fields = self.occurrence_type.form_fields
        _form_data = (
            copy.deepcopy(self.form_data) if isinstance(self.form_data, dict) else {}
        )
        field_value = get_obj_from_path(_form_data, field_name)

        return (
            get_value_in_form_fields(field_name, field_value, form_fields)
            or field_value
            or default
        )

    def get_inventory(self):
        return self.parent if getattr(self, "parent") else None

    def get_children(self) -> QuerySet:
        pks_child = self.reporting_relation_parent.values_list("child_id", flat=True)
        return self.__class__.objects.prefetch_related(
            "occurrence_type",
        ).filter(pk__in=pks_child)


class ReportingFile(models.Model):
    """
    Models the image attached to the Reporting.
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    reporting = models.ForeignKey(
        Reporting, on_delete=models.CASCADE, related_name="reporting_files"
    )
    description = models.TextField(blank=True)
    md5 = models.TextField(blank=True)
    upload = models.FileField(storage=PrivateMediaStorage())
    uploaded_at = models.DateTimeField(auto_now_add=True)
    datetime = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_reporting_files",
    )
    include_dnit = models.BooleanField(default=True)
    include_rdo = models.BooleanField(default=False)
    km = models.FloatField(default=None, null=True, blank=True)
    point = models.PointField(null=True, blank=True)

    history = HistoricalRecords(history_change_reason_field=models.TextField(null=True))
    kind = models.CharField(max_length=100, blank=True, default="")

    is_shared = models.BooleanField(default=False)

    def __str__(self):
        return "[{}] - {} - {}".format(
            self.reporting.company.name, self.description, self.uploaded_at
        )

    @property
    def get_company_id(self):
        return self.reporting.company_id


class ReportingMessage(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    reporting = models.ForeignKey(
        Reporting, on_delete=models.CASCADE, related_name="reporting_messages"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reporting_messages",
    )
    # Autofill
    created_by_firm = models.ForeignKey(
        Firm,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reporting_messages",
    )
    read_by = models.ManyToManyField(
        User,
        through="ReportingMessageReadReceipt",
        related_name="read_reporting_messages",
    )

    mentioned_users = models.ManyToManyField(
        User, related_name="mentioned_in_messages", blank=True
    )
    mentioned_firms = models.ManyToManyField(
        Firm, related_name="mentioned_firm_in_messages", blank=True
    )

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - [{}]: {} - {}".format(
            self.reporting.company.name,
            self.reporting.number,
            self.created_by.username,
            self.created_at,
        )

    @property
    def get_company_id(self):
        return self.reporting.company_id


class ReportingMessageReadReceipt(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Required
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="read_receipts"
    )
    # Required
    reporting_message = models.ForeignKey(
        ReportingMessage, on_delete=models.CASCADE, related_name="read_receipts"
    )

    read_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - [{}]: {} - {}".format(
            self.reporting_message.reporting.company.name,
            self.reporting_message.reporting.number,
            self.user.username,
            self.read_at,
        )

    class Meta:
        unique_together = ("user", "reporting_message")

    @property
    def get_company_id(self):
        return self.reporting_message.reporting.company_id


class RecordMenu(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField(null=False, blank=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_record_menus",
        null=True,
    )
    created_at = models.DateField(auto_now_add=True)
    limit = models.Q(app_label="reportings", model="reporting")
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        limit_choices_to=limit,
    )
    users = models.ManyToManyField(User, through="RecordMenuRelation")
    order = models.IntegerField()
    system_default = models.BooleanField(default=False)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.company} - {self.name}"

    def get_user_menu_max_order(self):
        max_order = self.recordmenurelation_set.aggregate(Max("order"))
        return max_order.get("order__max")

    def set_max_order(self):
        max_order = self.get_user_menu_max_order()
        if isinstance(max_order, int) and max_order <= self.order:
            self.order = max_order + 1
            self.save()

    class Meta:
        ordering = ["order"]


class RecordMenuRelation(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record_menu = models.ForeignKey(RecordMenu, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    hide_menu = models.BooleanField(default=False)
    order = models.IntegerField()
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    history = HistoricalRecords()

    def __str__(self):
        return f"[{self.order}] {self.record_menu.name} ({self.user.full_name})"

    class Meta:
        unique_together = ["user", "record_menu"]
        ordering = ["order"]


class ReportingRelation(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    outward = models.CharField(max_length=100)
    inward = models.CharField(max_length=100)
    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.company_id

    def __str__(self):
        return "[{}] {} ({} - {})".format(
            self.company.name, self.name, self.outward, self.inward
        )


class ReportingInReporting(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent = models.ForeignKey(
        "Reporting",
        on_delete=models.CASCADE,
        related_name="reporting_relation_parent",
    )
    child = models.ForeignKey(
        "Reporting",
        on_delete=models.CASCADE,
        related_name="reporting_relation_child",
    )
    reporting_relation = models.ForeignKey(
        "ReportingRelation",
        on_delete=models.CASCADE,
        related_name="reporting_relation_in",
    )

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.reporting_relation.company_id

    def __str__(self):
        return "[{}] {} - {} ({})".format(
            self.reporting_relation.company.name,
            self.parent.number,
            self.child.number,
            self.reporting_relation.name,
        )


class ReportingInReportingAsyncBatch(AbstractBaseModel):
    in_progress = models.BooleanField(default=False, blank=False)
    job = models.ForeignKey(
        Job, on_delete=models.CASCADE, related_name="rep_in_rep_async_batches"
    )
    pending_batch_items = JSONField(default=list, blank=True, null=True)

    def __str__(self) -> str:
        return f"[{self.company.name}] {'[In Progress]' if self.in_progress else ''}: {len(self.pending_batch_items)} ReportingInReporting items in this batch"


class ReportingBulkEdit(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    reportings = models.ManyToManyField(
        Reporting, related_name="reporting_bulk_edits", blank=True
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_bulk_edits",
    )
    edit_data = JSONField(default=dict)
    done = models.BooleanField(default=False)
    error = models.BooleanField(default=False)

    def __str__(self):
        return f"Editing {self.reportings.count()} at {self.created_at}"
