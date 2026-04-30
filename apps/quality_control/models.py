import uuid

from django.db import models
from django.db.models import JSONField
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.companies.models import Company, Firm
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import Reporting
from apps.templates.models import CSVImport
from apps.users.models import User
from RoadLabsAPI.storage_backends import PrivateMediaStorage


class QualityProject(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_number = models.TextField()
    firm = models.ForeignKey(
        Firm, on_delete=models.CASCADE, related_name="firm_quality_projects"
    )
    created_at = models.DateField(auto_now_add=True)
    registered_at = models.DateField(default=timezone.now)
    expires_at = models.DateField()
    occurrence_type = models.ForeignKey(
        OccurrenceType,
        on_delete=models.CASCADE,
        related_name="type_quality_projects",
    )
    form_data = JSONField(default=dict)

    @property
    def get_company_id(self):
        return self.firm.company_id

    class Meta:
        ordering = ["firm__company"]

    def __str__(self):
        return "[{}] {}: {}".format(
            self.firm.company.name, self.uuid, self.project_number
        )


class ConstructionPlant(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_construction_plants",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_construction_plants",
    )

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]

    def __str__(self):
        return "[{}] {}: {}".format(self.company.name, self.uuid, self.name)


class QualitySample(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_quality_samples",
    )
    collected_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_quality_samples",
    )
    # Defaults to request user, check perform_create()
    responsible = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_responsible_quality_samples",
    )
    quality_project = models.ForeignKey(
        QualityProject,
        on_delete=models.CASCADE,
        related_name="quality_project_samples",
        blank=True,
        null=True,
    )
    construction_firm = models.ForeignKey(
        Firm,
        on_delete=models.CASCADE,
        related_name="firm_quality_samples",
        blank=True,
        null=True,
    )
    occurrence_type = models.ForeignKey(
        OccurrenceType,
        on_delete=models.CASCADE,
        related_name="type_quality_samples",
    )
    reportings = models.ManyToManyField(
        Reporting, related_name="reportings_quality_samples", blank=True
    )
    construction_plant = models.ForeignKey(
        ConstructionPlant,
        on_delete=models.SET_NULL,
        related_name="construction_plant_quality_samples",
        blank=True,
        null=True,
    )
    form_data = JSONField(default=dict, blank=True, null=True)
    number = models.CharField(max_length=40)
    received_at = models.DateTimeField(blank=True, null=True)
    is_proof = models.BooleanField(default=False)

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]

    def __str__(self):
        return "[{}] {}: {}".format(self.company.name, self.uuid, self.number)


class QualityAssay(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=40)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_quality_assays"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_quality_assays",
    )
    # Defaults to request user, check perform_create()
    responsible = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_responsible_quality_assays",
    )
    quality_project = models.ForeignKey(
        QualityProject,
        on_delete=models.CASCADE,
        related_name="quality_project_assays",
        blank=True,
        null=True,
    )
    occurrence_type = models.ForeignKey(
        OccurrenceType,
        on_delete=models.CASCADE,
        related_name="type_quality_assays",
    )
    related_assays = models.ManyToManyField(
        "self",
        related_name="quality_assay_related_assays",
        blank=True,
        symmetrical=False,
    )
    quality_sample = models.ForeignKey(
        QualitySample,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quality_sample_quality_assays",
    )
    reportings = models.ManyToManyField(
        Reporting, related_name="reporting_quality_assays", blank=True
    )
    form_data = JSONField(default=dict, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    csv_import = models.ForeignKey(
        CSVImport,
        on_delete=models.SET_NULL,
        null=True,
        related_name="csv_import_assays",
    )

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]

    def __str__(self):
        return "[{}] {}: {}".format(self.company.name, self.uuid, self.number)


class QualityControlExport(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    reporting = models.ForeignKey(
        Reporting,
        on_delete=models.CASCADE,
        related_name="reporting_quality_control_exports",
    )
    exported_file = models.FileField(  # Read only
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="user_quality_control_exports",
        null=True,
        blank=True,
    )

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] {}".format(self.reporting.firm.company.name, self.uuid)

    @property
    def get_company_id(self):
        return self.reporting.firm.company_id
