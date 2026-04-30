import uuid

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.db.models import JSONField
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.companies.models import Company, User
from apps.files.models import File
from apps.reportings.models import Reporting


class Construction(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_constructions"
    )

    # Basic info
    name = models.TextField()
    description = models.TextField()
    location = models.TextField()
    km = models.FloatField()
    end_km = models.FloatField()
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_constructions"
    )
    origin = models.CharField(max_length=200, null=True, blank=True)

    # Date & Time
    created_at = models.DateTimeField(default=timezone.now)
    scheduling_start_date = models.DateTimeField()
    scheduling_end_date = models.DateTimeField()
    analysis_start_date = models.DateTimeField()
    analysis_end_date = models.DateTimeField()
    execution_start_date = models.DateTimeField()
    execution_end_date = models.DateTimeField()
    spend_schedule_start_date = models.DateTimeField()
    spend_schedule_end_date = models.DateTimeField()

    construction_item = models.TextField()
    intervention_type = models.CharField(max_length=100)

    # JSON Fields
    phases = JSONField(default=list, blank=True, null=True)
    spend_schedule = JSONField(default=dict, blank=True, null=True)

    files = GenericRelation(File, related_query_name="file_constructions")

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]

    def __str__(self):
        return "[{}] {} - {}".format(self.company.name, self.uuid, self.name)


class ConstructionProgress(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_construction_progresses",
    )
    construction = models.ForeignKey(
        Construction,
        on_delete=models.CASCADE,
        related_name="construction_progresses",
    )
    progress_details = JSONField(default=list, blank=True, null=True)
    reportings = models.ManyToManyField(
        Reporting, related_name="reporting_construction_progresses", blank=True
    )
    files = GenericRelation(File, related_query_name="file_construction_progresses")

    @property
    def get_company_id(self):
        return self.construction.company_id

    class Meta:
        ordering = ["construction__company"]

    def __str__(self):
        return "[{}] {} - {}".format(
            self.construction.company.name, self.uuid, self.name
        )
