import uuid

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.gis.db import models
from django.db.models import JSONField
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.companies.models import Company, Firm
from apps.files.models import File
from apps.locations.models import City, Location, River
from apps.resources.models import Contract
from apps.service_orders.const import resource_approval_status
from apps.service_orders.models import Procedure, ServiceOrderActionStatus
from apps.users.models import User
from helpers.apps.json_logic import apply_json_logic
from helpers.forms import form_fields_dict
from helpers.serializers import get_obj_serialized
from helpers.strings import get_obj_from_path


class MonitoringPlan(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    number = models.CharField(max_length=100, blank=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    responsibles = models.ManyToManyField(
        User, related_name="plans_responsibles", blank=True
    )
    status = models.ForeignKey(
        ServiceOrderActionStatus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_monitorings",
    )

    specificity = models.TextField(blank=True)
    description = models.TextField(blank=True)
    legal_requirement = models.TextField(blank=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plans_user",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_not_notified = models.BooleanField(default=False)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}]: {} - {}".format(self.company.name, self.number, self.description)

    @property
    def get_company_id(self):
        return self.company_id


class MonitoringCycle(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    number = models.CharField(max_length=100, blank=True)
    start_date = models.DateTimeField(default=None)
    end_date = models.DateTimeField(default=None)

    status = models.ForeignKey(
        ServiceOrderActionStatus,
        on_delete=models.SET_NULL,
        null=True,
        related_name="cycles_status",
    )

    monitoring_plan = models.ForeignKey(
        MonitoringPlan, on_delete=models.CASCADE, related_name="cycles_plan"
    )

    executers = models.ManyToManyField(
        Firm, related_name="cycles_executers", blank=True
    )
    viewers = models.ManyToManyField(Firm, related_name="cycles_viewers", blank=True)
    evaluators = models.ManyToManyField(
        Firm, related_name="cycles_evaluators", blank=True
    )
    approvers = models.ManyToManyField(
        Firm, related_name="cycles_approvers", blank=True
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cycles_user",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    contracts = models.ManyToManyField(
        Contract, related_name="monitoring_cycles", blank=True
    )

    responsibles = models.ManyToManyField(
        User, related_name="responsible_cycles", blank=True
    )

    email_created = models.BooleanField(default=False)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}]: {} - {} - [{} - {}]".format(
            self.monitoring_plan.company.name,
            self.monitoring_plan.description,
            self.number,
            self.start_date,
            self.end_date,
        )

    @property
    def get_company_id(self):
        return self.monitoring_plan.company_id


class MonitoringPoint(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    active = models.BooleanField(default=True)

    code = models.TextField()

    # Location
    uf_code = models.IntegerField(blank=True, null=True)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, blank=True, null=True)
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, blank=True, null=True
    )
    river = models.ForeignKey(River, on_delete=models.SET_NULL, blank=True, null=True)
    place_on_dam = models.CharField(max_length=50, blank=True)
    coordinates = models.PointField(blank=True, null=True)

    monitoring_plan = models.ForeignKey(
        MonitoringPlan,
        on_delete=models.CASCADE,
        related_name="monitoring_points",
        null=True,
    )

    coverage_area = models.PolygonField(blank=True, null=True)

    segment = models.TextField(blank=True)
    description = models.TextField(blank=True)
    depth = models.TextField(blank=True)
    position = models.TextField(blank=True)
    stratification = models.TextField(blank=True)
    zone = models.TextField(blank=True)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}]: {}".format(self.monitoring_plan.company.name, self.code)

    @property
    def get_company_id(self):
        return self.monitoring_plan.company_id


class MonitoringFrequency(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    monitoring_plan = models.ForeignKey(
        MonitoringPlan, on_delete=models.CASCADE, related_name="frequency_plans"
    )

    monitoring_points = models.ManyToManyField(
        MonitoringPoint, related_name="scheduled_frequencies", blank=True
    )

    parameter_group = models.ForeignKey(
        "occurrence_records.OccurrenceType",
        on_delete=models.SET_NULL,
        null=True,
    )

    start_date = models.DateTimeField(default=None)
    end_date = models.DateTimeField(default=None)

    frequency = models.TextField(blank=True)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}]: {} - [{} - {}]".format(
            self.monitoring_plan.company.name,
            self.frequency,
            self.start_date,
            self.end_date,
        )

    @property
    def get_company_id(self):
        return self.monitoring_plan.company_id


class MonitoringCampaign(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    start_date = models.DateTimeField(default=None)
    end_date = models.DateTimeField(default=None)

    firm = models.ForeignKey(Firm, on_delete=models.SET_NULL, null=True)

    monitoring_plan = models.ForeignKey(
        MonitoringPlan, on_delete=models.CASCADE, related_name="campaigns"
    )
    frequencies = models.ManyToManyField(
        MonitoringFrequency, related_name="campaigns", blank=True
    )

    status = models.ForeignKey(
        ServiceOrderActionStatus, on_delete=models.SET_NULL, null=True
    )

    procedures = models.ManyToManyField(
        Procedure, related_name="monitoring_campaigns", blank=True
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campaigns_user",
    )

    history = HistoricalRecords()

    def __str__(self):
        return "[{}]: {} - [{} - {}]".format(
            self.monitoring_plan.company.name,
            self.firm,
            self.start_date,
            self.end_date,
        )

    @property
    def get_company_id(self):
        return self.monitoring_plan.company_id


class MonitoringCollect(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_collects"
    )

    # Basic Information
    number = models.CharField(max_length=100, blank=True)
    datetime = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_by_collects",
    )

    responsible = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsible_collects",
    )

    parameter_group = models.ForeignKey(
        "occurrence_records.OccurrenceType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parameter_group_collects",
    )
    dict_form_data = JSONField(default=dict, blank=True, null=True)
    array_form_data = JSONField(default=list, blank=True, null=True)

    monitoring_frequency = models.ForeignKey(
        MonitoringFrequency,
        on_delete=models.CASCADE,
        related_name="frequency_collects",
    )

    monitoring_point = models.ForeignKey(
        MonitoringPoint,
        related_name="point_collects",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    occurrence_record = models.ForeignKey(
        "occurrence_records.OccurrenceRecord",
        on_delete=models.CASCADE,
        related_name="record_collects",
    )

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - {} - {}".format(self.company.name, self.number, self.datetime)

    @property
    def get_company_id(self):
        return self.company_id


class MonitoringRecord(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(Company, on_delete=models.CASCADE)

    # Basic Information
    datetime = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    editable = models.BooleanField(default=True)

    # Registerer
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    number = models.CharField(max_length=100, blank=True)

    # Occurrence Info
    parameter_group = models.ForeignKey(
        "occurrence_records.OccurrenceType",
        on_delete=models.SET_NULL,
        null=True,
    )
    form_data = JSONField(default=dict, blank=True, null=True)
    form_metadata = JSONField(default=dict, blank=True, null=True)

    monitoring_campaign = models.ForeignKey(
        MonitoringCampaign,
        on_delete=models.CASCADE,
        related_name="monitoring_records",
    )

    monitoring_frequency = models.ForeignKey(
        MonitoringFrequency,
        on_delete=models.CASCADE,
        related_name="monitoring_records",
    )

    monitoring_point = models.ForeignKey(
        MonitoringPoint,
        related_name="monitoring_records",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    procedures = models.ManyToManyField(
        Procedure, related_name="monitoring_records", blank=True
    )

    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
        related_name="historicalmonitoringrecord",
    )

    # File
    file = GenericRelation(File, related_query_name="monitoring_record_file")

    def __str__(self):
        return "[{}] - {} - {}".format(
            self.monitoring_campaign.monitoring_plan.company.name,
            self.number,
            self.datetime,
        )

    @property
    def get_company_id(self):
        return self.company_id

    @property
    def is_normal(self):
        normal = True
        if self.form_data and self.parameter_group:
            form_data_keys = self.form_data.keys()
            if self.parameter_group.form_fields:
                form_fields = self.parameter_group.form_fields
                if "fields" in form_fields.keys():
                    for item in form_fields["fields"]:
                        if "api_name" in item.keys():
                            if item["api_name"] in form_data_keys:
                                value = self.form_data[item["api_name"]]
                                if "lower_limit" in item.keys() and item["lower_limit"]:
                                    normal &= item["lower_limit"] <= value
                                if "upper_limit" in item.keys() and item["upper_limit"]:
                                    normal &= item["upper_limit"] >= value
                    return normal
        return False

    def save(self, *args, **kwargs):
        # Apply logic in form_data fields
        # check if any form field has autofill specified (i.e., manually_specified=False)
        if not all(
            [item["manually_specified"] for item in self.form_metadata.values()]
        ):
            from apps.monitorings.views import (
                MonitoringRecordSerializer,
                MonitoringRecordView,
            )

            obj_serialized = get_obj_serialized(
                self,
                serializer=MonitoringRecordSerializer,
                view=MonitoringRecordView,
            )
        else:
            obj_serialized = None

        if obj_serialized:
            form_fields = form_fields_dict(self.parameter_group)
            for key, value in self.form_metadata.items():
                if "manually_specified" in value and not value["manually_specified"]:
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
                                self.parameter_group,
                                self.company,
                            )
                        except Exception:
                            pass

        super(MonitoringRecord, self).save(*args, **kwargs)


class OperationalControl(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="contract_op_controls",
        null=True,
    )

    firm = models.ForeignKey(
        Firm, on_delete=models.CASCADE, related_name="firm_op_controls"
    )

    responsible = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="responsible_op_controls"
    )

    kind = models.CharField(max_length=100)
    metadata = JSONField(default=dict, blank=True, null=True)

    config_occurrence_types = models.ManyToManyField(
        "occurrence_records.OccurrenceType",
        related_name="occurrence_type_op_controls",
        blank=True,
    )

    # Map
    show_map = models.BooleanField(default=False)
    map_default_filters = JSONField(default=dict, blank=True, null=True)

    # Materials
    show_materials = models.BooleanField(default=False)

    # File
    files = GenericRelation(File, related_query_name="op_control_file")

    history = HistoricalRecords()

    def __str__(self):
        return "[{}]: {} - [{}]".format(
            self.firm.company.name if self.firm.company else "",
            self.kind,
            self.contract.name if self.contract else "",
        )

    @property
    def get_company_id(self):
        return self.firm.company_id


class OperationalCycle(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    number = models.CharField(max_length=100, blank=True)
    start_date = models.DateTimeField(default=None)
    end_date = models.DateTimeField(default=None)

    creators = models.ManyToManyField(
        Firm, related_name="operational_cycles_creators", blank=True
    )
    viewers = models.ManyToManyField(
        Firm, related_name="operational_cycle_viewers", blank=True
    )

    operational_control = models.ForeignKey(
        OperationalControl,
        on_delete=models.CASCADE,
        related_name="operational_control_cycles",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operational_cycle_user",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}]: {} - [{} - {}]".format(
            self.operational_control.firm.company.name,
            self.number,
            self.start_date,
            self.end_date,
        )

    @property
    def get_company_id(self):
        return self.operational_control.firm.company_id


class MaterialItem(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_material_items"
    )
    operational_control = models.ForeignKey(
        OperationalControl,
        on_delete=models.CASCADE,
        related_name="control_material_items",
    )

    name = models.TextField()
    amount = models.FloatField(default=0)
    unit_price = models.FloatField(default=0)
    used_price = models.FloatField(default=0)
    remaining_amount = models.FloatField(default=0)
    creation_date = models.DateTimeField(auto_now_add=True)
    effective_date = models.DateTimeField(default=timezone.now)
    unit = models.CharField(max_length=50, blank=True)
    is_extra = models.BooleanField(default=False)

    resource_kind = models.CharField(max_length=60, blank=True)
    entity = models.ForeignKey(
        "companies.Entity",
        related_name="material_items",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    additional_control = models.CharField(max_length=60, blank=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="creator_material_items",
        null=True,
        blank=True,
    )

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - {}: {} {}".format(
            self.company.name, self.name, self.amount, self.unit
        )

    @property
    def get_company_id(self):
        return self.company_id


class MaterialUsage(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    material_item = models.ForeignKey(
        MaterialItem,
        on_delete=models.CASCADE,
        related_name="material_item_usages",
    )

    occurrence_record = models.ForeignKey(
        "occurrence_records.OccurrenceRecord",
        on_delete=models.SET_NULL,
        related_name="record_usages",
        null=True,
        blank=True,
    )
    firm = models.ForeignKey(
        Firm,
        on_delete=models.SET_NULL,
        related_name="firm_usages",
        blank=True,
        null=True,
    )

    amount = models.FloatField(default=0)
    unit_price = models.FloatField(null=True, blank=True)
    total_price = models.FloatField(null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="creator_usages",
        null=True,
        blank=True,
    )

    # Fields related to the approval of this object
    approval_status = models.CharField(
        max_length=100,
        choices=resource_approval_status.APPROVAL_STATUS_CHOICES,
        default=resource_approval_status.WAITING_APPROVAL,
    )
    approval_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="approver_usages",
        null=True,
        blank=True,
    )

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - {} {}".format(
            self.material_item.company.name,
            self.amount,
            self.material_item.unit,
        )

    @property
    def get_company_id(self):
        return self.material_item.company_id
