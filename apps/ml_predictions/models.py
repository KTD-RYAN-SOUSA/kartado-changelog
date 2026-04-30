import uuid

from django.contrib.gis.db import models
from django.db.models import JSONField

from apps.companies.models import Company
from apps.daily_reports.models import MultipleDailyReport


class MLPredictionConfig(models.Model):
    company = models.OneToOneField(Company, on_delete=models.CASCADE, primary_key=True)

    def __str__(self):
        return self.company.name


class MLPrediction(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="ml_predictions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    multiple_daily_report = models.ForeignKey(
        MultipleDailyReport,
        on_delete=models.SET_NULL,
        related_name="ml_predictions",
        null=True,
        blank=True,
    )
    output_data = JSONField(default=dict)
    feedback = models.BooleanField(null=True, blank=True)
    feedback_notes = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company.name} - {self.created_at}"
