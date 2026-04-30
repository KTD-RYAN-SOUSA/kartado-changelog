import uuid

from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.db.models import JSONField, QuerySet
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Company, Entity, Firm
from apps.locations.models import City, Location, River
from apps.resources.models import Contract, Resource
from apps.service_orders.manager import ServiceOrderResourceManager
from apps.users.models import User
from helpers.fields import ColorField
from RoadLabsAPI.storage_backends import PrivateMediaStorage

from .const import kind_types, resource_approval_status, status_types


class ServiceOrderActionStatus(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    kind = models.CharField(
        max_length=100,
        choices=status_types.STATUS_TYPE_CHOICES,
        default=status_types.ACTION_STATUS,
    )

    companies = models.ManyToManyField(
        Company,
        through="ServiceOrderActionStatusSpecs",
        related_name="status_company",
    )

    name = models.TextField()
    metadata = JSONField(default=dict, blank=True, null=True)
    is_final = models.BooleanField(default=False)

    history = HistoricalRecords()

    def __str__(self):
        return "{} - {}".format(self.name, self.kind)

    class Meta:
        get_latest_by = ["kind"]
        verbose_name_plural = "Service Order Statuses"

    @property
    def get_company_id(self):
        return self.companies.first().uuid


class ServiceOrderActionStatusSpecs(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Required
    status = models.ForeignKey(
        ServiceOrderActionStatus,
        on_delete=models.CASCADE,
        related_name="status_specs",
    )
    # Required
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_status_specs"
    )

    color = ColorField(default="#FF0000")
    order = models.IntegerField()

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - {}".format(self.status.name, self.company.name)

    class Meta:
        unique_together = ("status", "company")

    @property
    def get_company_id(self):
        return self.company_id


class ServiceOrder(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    number = models.CharField(max_length=100, default="", blank=True)
    description = models.TextField(blank=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    # Kind
    kind = models.CharField(
        max_length=100,
        choices=kind_types.KIND_TYPE_CHOICES,
        default=kind_types.ENVIRONMENT,
    )
    process_type = models.CharField(max_length=100, default="", blank=True)
    shape_file_property = models.CharField(max_length=100, default="", blank=True)

    # Location
    uf_code = ArrayField(models.CharField(max_length=100), blank=True, null=True)
    place_on_dam = ArrayField(models.CharField(max_length=100), blank=True, null=True)
    other_reference = models.TextField(blank=True)
    city = models.ManyToManyField(City, related_name="city_service_orders", blank=True)
    location = models.ManyToManyField(
        Location, related_name="location_service_orders", blank=True
    )
    river = models.ManyToManyField(
        River, related_name="river_service_orders", blank=True
    )

    opened_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    is_closed = models.BooleanField(default=False)
    closed_description = models.TextField(blank=True)
    closed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="service_order_closed_by",
        null=True,
        blank=True,
    )
    priority = JSONField(default=dict, null=True, blank=True)
    canvas_layout = JSONField(default=list, blank=True, null=True)

    responsibles = models.ManyToManyField(
        User, related_name="responsibles_service_orders", blank=True
    )
    managers = models.ManyToManyField(
        User, related_name="managers_service_orders", blank=True
    )
    entity = models.ForeignKey(
        Entity,
        on_delete=models.SET_NULL,
        related_name="service_orders",
        null=True,
        blank=True,
    )

    obra = models.CharField(max_length=200, null=True, blank=True)
    sequencial = models.CharField(max_length=200, null=True, blank=True)
    identificador = models.CharField(max_length=200, null=True, blank=True)
    offender_name = models.CharField(max_length=200, null=True, blank=True)
    status = models.ForeignKey(
        ServiceOrderActionStatus,
        on_delete=models.SET_NULL,
        related_name="status_service_order",
        null=True,
    )

    history = HistoricalRecords()

    def get_main_occurrence_record(self):
        try:
            qs_occurrence_record = self.so_records.order_by("-created_at")
            for occurrence_record in qs_occurrence_record:
                form_data = occurrence_record.form_data
                if (
                    form_data.get("shape_file_property", None)
                    == self.shape_file_property
                ):
                    return occurrence_record

            return qs_occurrence_record.first()
        except Exception:
            pass

    def get_main_property(self) -> dict:
        try:
            occurrence_record = self.get_main_occurrence_record()
            if occurrence_record:
                form_data = occurrence_record.form_data
                property_intersections = form_data.get("property_intersections", None)
                if property_intersections:
                    for main_property in property_intersections:
                        if (
                            main_property["attributes"]["uuid"]
                            == self.shape_file_property
                        ):
                            return main_property
        except Exception:
            pass

    def get_process_type_option(self, process_type: str = ""):
        try:
            if not process_type:
                process_type = self.process_type

            return self.company.get_process_type_option(process_type)
        except Exception:
            pass

    def get_process_type_display(self):
        try:
            option = self.get_process_type_option()
            return option["name"]
        except Exception:
            pass

    def get_offender_name(self) -> str:
        return (self.get_main_occurrence_record()).get_offender_name()

    def get_procedure_files(self) -> QuerySet:
        try:
            return ProcedureFile.objects.filter(procedures__action__service_order=self)
        except Exception:
            return ProcedureFile.objects.none

    def __str__(self):
        return "[{}]{} - {}".format(self.company, self.number, self.opened_at)

    @property
    def get_company_id(self):
        return self.company_id


class ServiceOrderWatcher(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    notification_frequency = models.TextField(default="month")

    # Required
    service_order = models.ForeignKey(
        ServiceOrder,
        on_delete=models.CASCADE,
        related_name="serviceorder_watchers",
    )
    # Required
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="so_user_watchers",
        blank=True,
        null=True,
    )

    firm = models.ForeignKey(
        Firm,
        on_delete=models.CASCADE,
        related_name="so_firm_watchers",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="so_created_watchers",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="so_updated_watchers",
        null=True,
        blank=True,
    )
    status_email = models.BooleanField(default=True)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - {}".format(
            self.service_order.number, self.service_order.company.name
        )

    @property
    def get_company_id(self):
        return self.service_order.company_id


class ServiceOrderAction(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    service_order = models.ForeignKey(
        ServiceOrder, on_delete=models.CASCADE, related_name="actions"
    )

    name = models.TextField()

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    service_order_action_status = models.ForeignKey(
        ServiceOrderActionStatus,
        related_name="action_status",
        on_delete=models.SET_NULL,
        null=True,
    )

    firm = models.ForeignKey(Firm, on_delete=models.SET_NULL, null=True)

    responsible = models.ForeignKey(
        User,
        related_name="action_responsibles",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    estimated_end_date = models.DateTimeField(blank=True, null=True)

    parent_record = models.ForeignKey(
        "occurrence_records.OccurrenceRecord",
        on_delete=models.SET_NULL,
        related_name="record_actions",
        null=True,
        blank=True,
    )

    allow_forwarding = models.BooleanField(default=False)
    history = HistoricalRecords()

    def __str__(self):
        return "[{}]{} - Action: {}".format(
            self.service_order.company, self.service_order.number, self.name
        )

    @property
    def get_company_id(self):
        return self.service_order.company_id

    class Meta:
        ordering = ["-opened_at"]
        get_latest_by = ["opened_at"]


class Procedure(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    action = models.ForeignKey(
        ServiceOrderAction,
        on_delete=models.CASCADE,
        related_name="procedures",
        null=True,
    )

    occurrence_kind = models.TextField(blank=True)
    occurrence_type = models.ForeignKey(
        "occurrence_records.OccurrenceType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    service_order_action_status = models.ForeignKey(
        ServiceOrderActionStatus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    firm = models.ForeignKey(
        Firm,
        on_delete=models.SET_NULL,
        related_name="procedure_firm",
        null=True,
    )

    responsible = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    procedure_previous = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="procedure_next",
    )

    form_data = JSONField(default=dict, null=True, blank=True)
    to_do = models.TextField(blank=True)

    occurrence_records = models.ManyToManyField(
        "occurrence_records.OccurrenceRecord",
        related_name="procedures_mentioned",
        blank=True,
    )

    resources = models.ManyToManyField(
        Resource, through="service_orders.ProcedureResource"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="created_by",
        null=True,
        blank=True,
    )

    forward_to_judiciary = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField()
    done_at = models.DateTimeField(blank=True, null=True)

    history = HistoricalRecords()

    def __str__(self):
        try:
            return "[{}] {} - {}".format(
                self.action.service_order.number,
                self.action.service_order_action_status.name,
                self.deadline,
            )
        except Exception as e:
            print(e)
            return "{}".format(self.uuid)

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = ["created_at"]

    @property
    def get_company_id(self):
        return self.action.service_order.company_id


class ProcedureFile(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    procedures = models.ManyToManyField(
        Procedure, related_name="procedure_files", blank=True
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
        related_name="user_files",
    )

    history = HistoricalRecords(history_change_reason_field=models.TextField(null=True))

    def __str__(self):
        return "{} - {}".format(self.description, self.uploaded_at)

    @property
    def get_company_id(self):
        return self.procedures.first().action.service_order.company_id


class AdditionalControl(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="additional_controls_creator",
        null=True,
        blank=True,
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="additional_controls"
    )
    name = models.CharField(max_length=255, blank=False, default=None)
    is_active = models.BooleanField(default=True)


class ServiceOrderResource(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    contract = models.ForeignKey(
        Contract, on_delete=models.CASCADE, related_name="resources", null=True
    )
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="resource_service_orders",
        null=True,
        default=None,
    )

    amount = models.FloatField(default=0)
    unit_price = models.FloatField(default=0)
    used_price = models.FloatField(default=0)
    remaining_amount = models.FloatField(default=0)
    creation_date = models.DateTimeField(auto_now_add=True)
    effective_date = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="service_order_resource_creator",
        null=True,
        blank=True,
    )
    resource_kind = models.CharField(max_length=60, blank=True)
    entity = models.ForeignKey(
        "companies.Entity",
        related_name="service_order_resources",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    additional_control_model = models.ForeignKey(
        AdditionalControl,
        on_delete=models.PROTECT,
        related_name="service_order_resources",
        null=True,
        blank=True,
    )

    additional_control = models.CharField(max_length=60, blank=True)

    objects = ServiceOrderResourceManager()
    history = HistoricalRecords()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__original_unit_price = self.unit_price

    def save(self, *args, **kwargs):
        super(ServiceOrderResource, self).save(*args, **kwargs)
        if self.unit_price != self.__original_unit_price:
            for adm_item in self.resource_contract_administration_items.all():
                adm_item.save()

    def __str__(self):
        return "{} - {} {}".format(
            self.resource,
            self.amount,
            self.resource.unit if self.resource else "",
        )

    @property
    def get_company_id(self):
        return self.resource.company_id


class AdministrativeInformation(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    service_order = models.ForeignKey(
        ServiceOrder,
        on_delete=models.CASCADE,
        null=True,
        related_name="administrative_informations",
    )
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="administrative_informations",
        null=True,
    )
    responsible = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="administrative_informations_responsible",
    )
    spend_limit = models.FloatField(default=0)

    history = HistoricalRecords()

    def __str__(self):
        contract_name = self.contract.name if self.contract else ""
        service_order_number = self.service_order.number if self.service_order else ""
        return "{} - {}".format(contract_name, service_order_number)

    @property
    def get_company_id(self):
        return self.service_order.company_id


class MeasurementBulletin(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    number = models.CharField(max_length=100, blank=True)
    identification_bulletin = models.CharField(
        max_length=100,
        blank=True,
    )
    firm = models.ForeignKey(
        Firm,
        on_delete=models.SET_NULL,
        related_name="firm_measurement_bulletins",
        null=True,
    )
    firm_manager = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    creation_date = models.DateTimeField(auto_now_add=True)
    measurement_date = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_measurement_bulletins",
    )
    total_price = models.FloatField(null=True, blank=True)
    contract = models.ForeignKey(
        Contract,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bulletins",
    )
    extra_info = JSONField(default=dict, blank=True)
    description = models.TextField(blank=True, default="")

    approval_step = models.ForeignKey(
        ApprovalStep,
        on_delete=models.SET_NULL,
        related_name="step_bulletins",
        null=True,
        blank=True,
    )

    editable = models.BooleanField(default=True)

    history = HistoricalRecords()

    period_starts_at = models.DateTimeField(blank=True, null=True)
    period_ends_at = models.DateTimeField(blank=True, null=True)
    work_day = models.IntegerField(blank=True, null=True)

    is_processing = models.BooleanField(default=False)

    related_firms = models.ManyToManyField(
        Firm, related_name="related_bulletins_from_firm", blank=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_bulletin_surveys = None

    def save(self, *args, **kwargs):
        super(MeasurementBulletin, self).save(*args, **kwargs)

        if self.original_bulletin_surveys:
            for bs in self.original_bulletin_surveys:
                bs.refresh_from_db()
                bs.save()

        for fs in self.bulletin_surveys.all():
            if self.original_bulletin_surveys and fs in self.original_bulletin_surveys:
                continue
            fs.refresh_from_db()
            fs.save()

    def __str__(self):
        try:
            return "{} - {}".format(self.firm.name, self.number)
        except Exception:
            return "{}".format(self.number)

    @property
    def get_company_id(self):
        return (
            self.contract.firm.company_id
            if self.contract.firm
            else self.contract.subcompany.company_id
        )


class ProcedureResource(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    procedure = models.ForeignKey(
        Procedure,
        on_delete=models.CASCADE,
        related_name="procedure_resources",
        null=True,
        blank=True,
    )
    service_order = models.ForeignKey(
        ServiceOrder,
        on_delete=models.CASCADE,
        related_name="resources_service_order",
        null=True,
        blank=True,
    )
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="resource_procedures",
        null=True,
        blank=True,
    )
    service_order_resource = models.ForeignKey(
        ServiceOrderResource,
        on_delete=models.CASCADE,
        related_name="serviceorderresource_procedures",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    amount = models.FloatField(default=0)
    unit_price = models.FloatField(null=True, blank=True)
    total_price = models.FloatField(null=True, blank=True)

    creation_date = models.DateTimeField(default=timezone.now)

    # Fields related to the approval of this procedure resource
    approval_status = models.CharField(
        max_length=100,
        choices=resource_approval_status.APPROVAL_STATUS_CHOICES,
        default=resource_approval_status.WAITING_APPROVAL,
    )
    approval_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="resource_approver",
        null=True,
        blank=True,
    )
    measurement_bulletin = models.ForeignKey(
        MeasurementBulletin,
        on_delete=models.SET_NULL,
        related_name="bulletin_resources",
        blank=True,
        null=True,
    )
    firm = models.ForeignKey(Firm, on_delete=models.SET_NULL, blank=True, null=True)
    reporting = models.ForeignKey(
        "reportings.Reporting",
        on_delete=models.CASCADE,
        related_name="reporting_resources",
        null=True,
        blank=True,
    )

    history = HistoricalRecords(
        related_name="history_procedure_resources",
        history_change_reason_field=models.TextField(null=True),
    )

    def __str__(self):
        return "{} - {} {}".format(
            self.resource,
            self.amount,
            self.resource.unit if self.resource else "",
        )

    @property
    def get_company_id(self):
        if self.service_order:
            return self.service_order.company_id
        else:
            return self.service_order_resource.resource.company_id


class PendingProceduresExport(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_pending_procedures_exports",
    )
    filters = JSONField(default=dict)
    exported_file = models.FileField(  # Read only
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )

    done = models.BooleanField(default=False)
    error = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_pending_procedures_exports",
    )

    def __str__(self):
        return "[{}]: {}".format(self.company.name, self.uuid)

    @property
    def get_company_id(self):
        return self.company.pk
