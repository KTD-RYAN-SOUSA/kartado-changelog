import uuid

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import JSONField, Q
from django.db.models.fields import CharField
from django.utils import timezone
from rest_framework_json_api import serializers
from simple_history.models import HistoricalRecords

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Company, Firm
from apps.reportings.models import Reporting, ReportingFile
from apps.resources.models import Contract, ContractItemAdministration, Resource
from apps.service_orders.const import resource_approval_status
from apps.service_orders.models import MeasurementBulletin
from apps.services.models import Service
from apps.users.models import User, UserSignature
from RoadLabsAPI.storage_backends import PrivateMediaStorage

from .const import export_formats, occurrence_origin, weather_forecast, work_conditions


class BaseDailyReport(models.Model):
    # NOTE: Related names in abstract models have special behaviour
    # https://docs.djangoproject.com/en/3.2/topics/db/models/#be-careful-with-related-name-and-related-query-name

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_%(class)ss"
    )
    date = models.DateField()
    day_without_work = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)
    reporting_files = models.ManyToManyField(
        ReportingFile, related_name="reporting_file_%(class)ss", blank=True
    )
    number = models.CharField(max_length=40, null=True)
    use_reporting_resources = models.BooleanField(default=False)
    editable = models.BooleanField(default=True)

    approval_step = models.ForeignKey(
        ApprovalStep,
        on_delete=models.SET_NULL,
        related_name="step_%(class)ss",
        null=True,
        blank=True,
    )

    history = HistoricalRecords(
        inherit=True,
        related_name="history_%(class)ss",
        history_change_reason_field=models.TextField(null=True),
    )

    # Weather
    # Size determined by the longest choice
    morning_weather = CharField(
        max_length=6,
        choices=weather_forecast.WEATHER_FORECAST_CHOICES,
        null=True,
        blank=True,
    )
    afternoon_weather = CharField(
        max_length=6,
        choices=weather_forecast.WEATHER_FORECAST_CHOICES,
        null=True,
        blank=True,
    )
    night_weather = CharField(
        max_length=6,
        choices=weather_forecast.WEATHER_FORECAST_CHOICES,
        null=True,
        blank=True,
    )

    # Conditions
    # Size determined by the longest choice
    morning_conditions = CharField(
        max_length=10,
        choices=work_conditions.WORK_CONDITION_CHOICES,
        null=True,
        blank=True,
    )
    afternoon_conditions = CharField(
        max_length=10,
        choices=work_conditions.WORK_CONDITION_CHOICES,
        null=True,
        blank=True,
    )
    night_conditions = CharField(
        max_length=10,
        choices=work_conditions.WORK_CONDITION_CHOICES,
        null=True,
        blank=True,
    )

    # Work duration
    morning_start = models.TimeField(null=True, blank=True)
    morning_end = models.TimeField(null=True, blank=True)

    afternoon_start = models.TimeField(null=True, blank=True)
    afternoon_end = models.TimeField(null=True, blank=True)

    night_start = models.TimeField(null=True, blank=True)
    night_end = models.TimeField(null=True, blank=True)

    # Creation info
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_%(class)ss",
    )
    # Defaults to request user, check perform_create()
    responsible = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_responsible_%(class)ss",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    inspector = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="user_inspector_%(class)ss",
    )

    # Header data
    header_info = JSONField(default=dict, blank=True, null=True)
    contract = models.ForeignKey(
        Contract,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract_%(class)ss",
    )

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]
        abstract = True

    def __str__(self):
        return "[{}] {} - {}".format(self.company.name, self.uuid, self.date)


class DailyReport(BaseDailyReport):
    identification = JSONField(default=dict, blank=True, null=True)

    class Meta(BaseDailyReport.Meta):
        unique_together = ["date", "company"]


class MultipleDailyReport(BaseDailyReport):
    firm = models.ForeignKey(
        Firm,
        on_delete=models.CASCADE,
        related_name="firm_multiple_daily_report",
    )
    reportings = models.ManyToManyField(
        Reporting, related_name="reporting_multiple_daily_reports", blank=True
    )
    legacy_number = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )

    compensation = models.BooleanField(default=False)

    _history_m2m_fields = ["reportings"]

    class Meta(BaseDailyReport.Meta):
        unique_together = ["created_by", "firm", "date"]


class DailyReportWorker(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    daily_reports = models.ManyToManyField(
        DailyReport,
        through="DailyReportRelation",
        related_name="daily_report_workers",
    )
    multiple_daily_reports = models.ManyToManyField(
        MultipleDailyReport,
        through="DailyReportRelation",
        related_name="multiple_daily_report_workers",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="daily_report_workers",
        null=True,
        blank=True,
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_daily_report_workers",
        blank=True,
        null=True,
    )
    firm = models.ForeignKey(
        Firm,
        on_delete=models.CASCADE,
        related_name="firm_daily_report_workers",
        blank=True,
        null=True,
    )
    members = models.TextField(blank=True, null=True)
    amount = models.FloatField()
    role = models.TextField(blank=True, null=True)
    creation_date = models.DateTimeField(default=timezone.now)
    total_price = models.FloatField(blank=True, null=True)
    unit_price = models.FloatField(blank=True, null=True)
    contract_item_administration = models.ForeignKey(
        ContractItemAdministration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract_item_administration_workers",
    )

    # Approval fields
    approval_status = models.CharField(
        max_length=100,
        choices=resource_approval_status.APPROVAL_STATUS_CHOICES,
        default=resource_approval_status.WAITING_APPROVAL,
    )
    approval_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="workers_approver",
        null=True,
        blank=True,
    )

    measurement_bulletin = models.ForeignKey(
        MeasurementBulletin,
        on_delete=models.SET_NULL,
        related_name="bulletin_workers",
        null=True,
    )

    history = HistoricalRecords(
        related_name="history_workers",
        history_change_reason_field=models.TextField(null=True),
    )

    extra_hours = JSONField(default=dict, blank=True, null=True)

    class Meta:
        ordering = ["uuid"]

    @property
    def get_company_id(self):
        if self.firm:
            return self.firm.company_id
        else:
            return self.company.uuid

    def __str__(self):
        if self.firm:
            company_name = self.firm.company.name
        elif self.company:
            company_name = self.company.name
        else:
            company_name = ""

        return "[{}] {}: {}".format(company_name, self.uuid, self.role)


class DailyReportExternalTeam(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    daily_reports = models.ManyToManyField(
        DailyReport,
        through="DailyReportRelation",
        related_name="daily_report_external_teams",
    )
    multiple_daily_reports = models.ManyToManyField(
        MultipleDailyReport,
        through="DailyReportRelation",
        related_name="multiple_daily_report_external_teams",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="daily_report_external_teams",
        null=True,
        blank=True,
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_external_teams"
    )
    contract_number = models.TextField()
    contractor_name = models.TextField()
    amount = models.IntegerField()
    contract_description = models.TextField()

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]

    def __str__(self):
        return "[{}] {}: {}".format(self.company.name, self.uuid, self.contractor_name)


class DailyReportEquipment(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    daily_reports = models.ManyToManyField(
        DailyReport,
        through="DailyReportRelation",
        related_name="daily_report_equipment",
    )
    multiple_daily_reports = models.ManyToManyField(
        MultipleDailyReport,
        through="DailyReportRelation",
        related_name="multiple_daily_report_equipment",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="daily_report_equipments",
        null=True,
        blank=True,
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_daily_report_equipment",
    )
    kind = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    amount = models.FloatField()
    creation_date = models.DateTimeField(default=timezone.now)
    total_price = models.FloatField(blank=True, null=True)
    unit_price = models.FloatField(blank=True, null=True)

    contract_item_administration = models.ForeignKey(
        ContractItemAdministration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract_item_administration_equipment",
    )

    # Approval fields
    approval_status = models.CharField(
        max_length=100,
        choices=resource_approval_status.APPROVAL_STATUS_CHOICES,
        default=resource_approval_status.WAITING_APPROVAL,
    )
    approval_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="equipment_approver",
        null=True,
        blank=True,
    )

    history = HistoricalRecords(
        related_name="history_equipment",
        history_change_reason_field=models.TextField(null=True),
    )

    measurement_bulletin = models.ForeignKey(
        MeasurementBulletin,
        on_delete=models.SET_NULL,
        related_name="bulletin_equipments",
        null=True,
    )

    extra_hours = JSONField(default=dict, blank=True, null=True)

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]
        verbose_name_plural = "Daily report equipment"

    def __str__(self):
        return "[{}] {}: {}".format(self.company.name, self.uuid, self.description)


class DailyReportVehicle(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    daily_reports = models.ManyToManyField(
        DailyReport,
        through="DailyReportRelation",
        related_name="daily_report_vehicles",
    )
    multiple_daily_reports = models.ManyToManyField(
        MultipleDailyReport,
        through="DailyReportRelation",
        related_name="multiple_daily_report_vehicles",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="daily_report_vehicles",
        null=True,
        blank=True,
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_daily_report_vehicles",
    )
    kind = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    amount = models.FloatField()
    creation_date = models.DateTimeField(default=timezone.now)
    total_price = models.FloatField(blank=True, null=True)
    unit_price = models.FloatField(blank=True, null=True)

    contract_item_administration = models.ForeignKey(
        ContractItemAdministration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract_item_administration_vehicles",
    )

    # Approval fields
    approval_status = models.CharField(
        max_length=100,
        choices=resource_approval_status.APPROVAL_STATUS_CHOICES,
        default=resource_approval_status.WAITING_APPROVAL,
    )
    approval_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="vehicle_approver",
        null=True,
        blank=True,
    )

    history = HistoricalRecords(
        related_name="history_vehicles",
        history_change_reason_field=models.TextField(null=True),
    )

    measurement_bulletin = models.ForeignKey(
        MeasurementBulletin,
        on_delete=models.SET_NULL,
        related_name="bulletin_vehicles",
        null=True,
    )

    extra_hours = JSONField(default=dict, blank=True, null=True)

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]

    def __str__(self):
        return "[{}] {}: {}".format(self.company.name, self.uuid, self.description)


class DailyReportSignaling(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    daily_reports = models.ManyToManyField(
        DailyReport,
        through="DailyReportRelation",
        related_name="daily_report_signaling",
    )
    multiple_daily_reports = models.ManyToManyField(
        MultipleDailyReport,
        through="DailyReportRelation",
        related_name="multiple_daily_report_signaling",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="daily_report_signaling",
        null=True,
        blank=True,
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_daily_report_signaling",
    )
    kind = models.TextField(blank=True, null=True)

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]
        verbose_name_plural = "Daily report signaling"

    def __str__(self):
        return "[{}] {}: {}".format(self.company.name, self.uuid, self.kind)


class DailyReportOccurrence(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    daily_reports = models.ManyToManyField(
        DailyReport,
        through="DailyReportRelation",
        related_name="daily_report_occurrences",
    )
    multiple_daily_reports = models.ManyToManyField(
        MultipleDailyReport,
        through="DailyReportRelation",
        related_name="multiple_daily_report_occurrences",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="daily_report_occurrences",
        null=True,
        blank=True,
    )

    firm = models.ForeignKey(
        Firm,
        on_delete=models.CASCADE,
        related_name="firm_daily_report_occurrences",
    )

    origin = CharField(
        max_length=10,
        choices=occurrence_origin.OCCURRENCE_ORIGIN_CHOICES,
        default=occurrence_origin.EXECUTOR,
    )

    starts_at = models.TimeField(null=True, blank=True)
    ends_at = models.TimeField(null=True, blank=True)
    impact_duration = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^\d{2}:\d{2}(:\d{2})?$",
                message="Formato inválido. Preencha o campo no formato esperado HH:MM",
                code="invalid_format",
            )
        ],
    )
    description = models.TextField()
    extra_info = models.TextField(blank=True)

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.firm.company_id

    class Meta:
        ordering = ["firm__company"]

    def __str__(self):
        return "[{}] {}: {}".format(self.firm.company.name, self.uuid, self.description)


class DailyReportResource(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    daily_reports = models.ManyToManyField(
        DailyReport,
        through="DailyReportRelation",
        related_name="daily_report_resources",
    )
    multiple_daily_reports = models.ManyToManyField(
        MultipleDailyReport,
        through="DailyReportRelation",
        related_name="multiple_daily_report_resources",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="daily_report_resources",
        null=True,
        blank=True,
    )

    kind = models.TextField(blank=True, null=True)
    amount = models.FloatField()
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="resource_daily_report_resources",
        null=True,
    )

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.resource.company_id

    class Meta:
        ordering = ["resource__company"]

    def __str__(self):
        return "[{}] {}: {}".format(
            self.resource.company.name, self.uuid, self.resource.name
        )


class ProductionGoal(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    daily_reports = models.ManyToManyField(
        DailyReport,
        through="DailyReportRelation",
        related_name="daily_report_production_goals",
    )
    multiple_daily_reports = models.ManyToManyField(
        MultipleDailyReport,
        through="DailyReportRelation",
        related_name="multiple_daily_report_production_goals",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="daily_report_production_goals",
        null=True,
        blank=True,
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="service_production_goals",
    )
    starts_at = models.DateField()
    ends_at = models.DateField()
    days_of_work = models.IntegerField()
    amount = models.FloatField()

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.service.company_id

    class Meta:
        ordering = ["service__company"]

    def __str__(self):
        return "[{}] {}: {}".format(
            self.service.company.name, self.uuid, self.service.name
        )


class DailyReportRelation(models.Model):
    # Basic info
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    active = models.BooleanField(default=True)
    daily_planned_amount = models.FloatField(blank=True, null=True)

    # Possible reports
    daily_report = models.ForeignKey(
        DailyReport,
        on_delete=models.CASCADE,
        related_name="report_relations",
        blank=True,
        null=True,
    )
    multiple_daily_report = models.ForeignKey(
        MultipleDailyReport,
        on_delete=models.CASCADE,
        related_name="multiple_report_relations",
        blank=True,
        null=True,
    )

    history = HistoricalRecords()

    # Possible relations to reports
    worker = models.ForeignKey(
        DailyReportWorker,
        on_delete=models.CASCADE,
        related_name="worker_relations",
        blank=True,
        null=True,
    )

    external_team = models.ForeignKey(
        DailyReportExternalTeam,
        on_delete=models.CASCADE,
        related_name="external_team_relations",
        blank=True,
        null=True,
    )

    equipment = models.ForeignKey(
        DailyReportEquipment,
        on_delete=models.CASCADE,
        related_name="equipment_relations",
        blank=True,
        null=True,
    )

    vehicle = models.ForeignKey(
        DailyReportVehicle,
        on_delete=models.CASCADE,
        related_name="vehicle_relations",
        blank=True,
        null=True,
    )

    signaling = models.ForeignKey(
        DailyReportSignaling,
        on_delete=models.CASCADE,
        related_name="signaling_relations",
        blank=True,
        null=True,
    )

    occurrence = models.ForeignKey(
        DailyReportOccurrence,
        on_delete=models.CASCADE,
        related_name="occurrence_relations",
        blank=True,
        null=True,
    )

    resource = models.ForeignKey(
        DailyReportResource,
        on_delete=models.CASCADE,
        related_name="resource_relations",
        blank=True,
        null=True,
    )

    production_goal = models.ForeignKey(
        ProductionGoal,
        on_delete=models.CASCADE,
        related_name="production_goal_relations",
        blank=True,
        null=True,
    )

    @property
    def get_company_id(self):
        return self.multiple_daily_report.company_id

    class Meta:
        ordering = ["multiple_daily_report__company"]
        constraints = [
            models.CheckConstraint(
                name="only_one_report_field_is_filled",
                check=(
                    Q(
                        daily_report__isnull=False,
                        multiple_daily_report__isnull=True,
                    )
                    | Q(
                        daily_report__isnull=True,
                        multiple_daily_report__isnull=False,
                    )
                ),
            ),
            models.UniqueConstraint(
                name="mdr_worker", fields=["multiple_daily_report", "worker"]
            ),
            models.UniqueConstraint(
                name="mdr_external_team",
                fields=["multiple_daily_report", "external_team"],
            ),
            models.UniqueConstraint(
                name="mdr_equipment", fields=["multiple_daily_report", "equipment"]
            ),
            models.UniqueConstraint(
                name="mdr_vehicle", fields=["multiple_daily_report", "vehicle"]
            ),
            models.UniqueConstraint(
                name="mdr_signaling", fields=["multiple_daily_report", "signaling"]
            ),
            models.UniqueConstraint(
                name="mdr_occurrence", fields=["multiple_daily_report", "occurrence"]
            ),
            models.UniqueConstraint(
                name="mdr_resource", fields=["multiple_daily_report", "resource"]
            ),
            models.UniqueConstraint(
                name="mdr_production_goal",
                fields=["multiple_daily_report", "production_goal"],
            ),
        ]

    def __str__(self):
        # Determine related model
        if self.worker:
            related_model = "Worker"
        elif self.external_team:
            related_model = "External Team"
        elif self.equipment:
            related_model = "Equipment"
        elif self.vehicle:
            related_model = "Vehicle"
        elif self.signaling:
            related_model = "Signaling"
        elif self.occurrence:
            related_model = "Occurrence"
        elif self.production_goal:
            related_model = "Production Goal"
        elif self.resource:
            related_model = "Report Resource"
        else:
            related_model = "Model"

        # Determine company name and kind of report
        if self.daily_report:
            company_name = self.daily_report.company.name
            report_model = "DailyReport"
        elif self.multiple_daily_report:
            company_name = self.multiple_daily_report.company.name
            report_model = "MultipleDailyReport"
        else:
            company_name = "Company"
            report_model = "Report"

        relation = "{} to {}".format(related_model, report_model)

        return "[{}] {}: {}".format(company_name, self.uuid, relation)


class DailyReportContractUsage(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Possible usage items
    worker = models.OneToOneField(
        DailyReportWorker,
        on_delete=models.CASCADE,
        related_name="worker_contract_usage",
        blank=True,
        null=True,
    )
    equipment = models.OneToOneField(
        DailyReportEquipment,
        on_delete=models.CASCADE,
        related_name="equipment_contract_usage",
        blank=True,
        null=True,
    )
    vehicle = models.OneToOneField(
        DailyReportVehicle,
        on_delete=models.CASCADE,
        related_name="vehicle_contract_usage",
        blank=True,
        null=True,
    )

    # ========== DENORMALIZED FIELDS FOR PERFORMANCE OPTIMIZATION ==========
    # These fields are duplicated from worker/equipment/vehicle for query optimization
    # They are automatically populated and updated by signals and helpers

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="contract_usages",
        db_index=True,
        null=True,
        blank=True,
        help_text="Denormalized from worker/equipment/vehicle for query optimization",
    )

    multiple_daily_reports = models.ManyToManyField(
        MultipleDailyReport,
        related_name="contract_usages",
        blank=True,
        help_text="Denormalized M2M from worker/equipment/vehicle",
    )
    daily_reports = models.ManyToManyField(
        DailyReport,
        related_name="contract_usages",
        blank=True,
        help_text="Denormalized M2M from worker/equipment/vehicle",
    )

    contract_item_administration = models.ForeignKey(
        ContractItemAdministration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract_usages",
        db_index=True,
        help_text="Denormalized from worker/equipment/vehicle",
    )

    firm = models.ForeignKey(
        Firm,
        on_delete=models.CASCADE,
        related_name="contract_usages",
        null=True,
        blank=True,
        db_index=True,
        help_text="Only relevant for workers, null for equipment/vehicle",
    )

    measurement_bulletin = models.ForeignKey(
        MeasurementBulletin,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract_usages",
        db_index=True,
        help_text="Denormalized from worker/equipment/vehicle",
    )

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        # Use denormalized field for better performance
        if self.company_id:
            return self.company_id
        # Fallback to original logic
        if self.worker:
            return self.worker.company_id
        elif self.equipment:
            return self.equipment.company_id
        elif self.vehicle:
            return self.vehicle.company_id
        else:
            return None

    def __str__(self):
        # Use denormalized company field when available for better performance
        if self.company_id:
            company_name = self.company.name if self.company else ""
        else:
            # Fallback to original logic
            if self.worker:
                company_name = self.worker.company.name
            elif self.equipment:
                company_name = self.equipment.company.name
            elif self.vehicle:
                company_name = self.vehicle.company.name
            else:
                company_name = ""

        # Determine usage item type
        if self.worker:
            usage_item = "DailyReportWorker"
        elif self.equipment:
            usage_item = "DailyReportEquipment"
        elif self.vehicle:
            usage_item = "DailyReportVehicle"
        else:
            usage_item = ""

        return "[{}] {}: {}".format(company_name, self.uuid, usage_item)


class DailyReportExport(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="user_daily_report_exports",
        null=True,
        blank=True,
    )
    is_compiled = models.BooleanField(default=False)

    format = models.CharField(
        max_length=5,
        choices=export_formats.EXPORT_FORMAT_CHOICES,
        default=export_formats.EXCEL,
    )

    daily_reports = models.ManyToManyField(
        DailyReport, related_name="daily_report_exports", blank=True
    )
    multiple_daily_reports = models.ManyToManyField(
        MultipleDailyReport,
        related_name="multiple_daily_report_exports",
        blank=True,
    )

    exported_file = models.FileField(  # Read only
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )

    done = models.BooleanField(default=False)
    error = models.BooleanField(default=False)

    sort = CharField(max_length=60, blank=True)
    order = CharField(max_length=4, blank=True)

    export_photos = models.BooleanField(default=True)

    def __str__(self):
        if self.daily_reports.exists():
            report = self.daily_reports.first()
        elif self.multiple_daily_reports.exists():
            report = self.multiple_daily_reports.first()

        return "[{}] {}".format(report.company.name, self.uuid)

    @property
    def get_company_id(self):
        if self.daily_reports.exists():
            report = self.daily_reports.first()
        elif self.multiple_daily_reports.exists():
            report = self.multiple_daily_reports.first()

        return report.company_id


class MultipleDailyReportFile(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    multiple_daily_report = models.ForeignKey(
        MultipleDailyReport,
        on_delete=models.SET_NULL,
        related_name="multiple_daily_report_files",
        null=True,
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
        related_name="user_multiple_daily_report_files",
    )
    kind = models.CharField(max_length=100, blank=True, default="")
    legacy_uuid = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
    )
    history = HistoricalRecords(history_change_reason_field=models.TextField(null=True))


class MultipleDailyReportSignature(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    multiple_daily_report = models.ForeignKey(
        MultipleDailyReport,
        on_delete=models.CASCADE,
        related_name="multiple_daily_report_signatures",
    )
    signature_name = models.TextField(blank=True)
    md5 = models.TextField(blank=True)
    upload = models.FileField(storage=PrivateMediaStorage())
    uploaded_at = models.DateTimeField(auto_now_add=True)
    signature_date = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_multiple_daily_report_signatures",
    )
    user_signature = models.ForeignKey(
        UserSignature,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="multiple_daily_report_user_signatures",
    )
    history = HistoricalRecords(history_change_reason_field=models.TextField(null=True))

    def save(self, *args, **kwargs):
        if self.user_signature_id and not self.signature_name:
            self.signature_name = self.user_signature.user.get_full_name()
        if not self.signature_name:
            raise serializers.ValidationError(
                "Um dos campos obrigatórios não está preenchido"
            )
        super(MultipleDailyReportSignature, self).save(*args, **kwargs)

    @property
    def get_company_id(self):

        return self.multiple_daily_report.company_id
