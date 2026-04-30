import uuid

from django.db import models
from django.db.models import JSONField

from .const.frequency_types import FREQUENCY_TYPE_CHOICES
from .const.integration_types import INTEGRATION_TYPE_CHOICES


class IntegrationConfig(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    active = models.BooleanField(default=True)
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="integrations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_run_at = models.DateTimeField(null=True)
    integration_type = models.CharField(choices=INTEGRATION_TYPE_CHOICES, max_length=20)

    historiador_path = models.TextField(null=True, blank=True)

    instrument_operational_position = models.TextField(null=True, blank=True)
    instrument_occurrence_type = models.ForeignKey(
        "occurrence_records.OccurrenceType",
        on_delete=models.SET_NULL,
        related_name="integrations_instrument",
        null=True,
    )
    instrument_code_field = models.TextField()
    instrument_code_prefix = models.TextField(default="", blank=True)
    reading_occurrence_type = models.ForeignKey(
        "occurrence_records.OccurrenceType",
        on_delete=models.SET_NULL,
        related_name="integrations_reading",
        null=True,
    )
    reading_operational_control = models.ForeignKey(
        "monitorings.OperationalControl",
        on_delete=models.SET_NULL,
        related_name="integrations_reading",
        null=True,
    )
    reading_created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="integrations",
        null=True,
        blank=True,
    )
    field_map = JSONField(default=list)
    fields_to_copy = JSONField(default=list)
    frequency_type = models.CharField(choices=FREQUENCY_TYPE_CHOICES, max_length=20)
    default_status = models.ForeignKey(
        "service_orders.ServiceOrderActionStatus",
        on_delete=models.SET_NULL,
        related_name="integrations_default_status",
        null=True,
    )
    default_approval_step = models.ForeignKey(
        "approval_flows.ApprovalStep",
        on_delete=models.SET_NULL,
        related_name="integrations_default_step",
        null=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return "[{}] - {}".format(self.company.name, self.name)


class IntegrationRun(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    integration_config = models.ForeignKey(
        IntegrationConfig, on_delete=models.CASCADE, related_name="runs"
    )
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True)
    log = JSONField(default=dict)
    error = models.BooleanField(default=False)

    class Meta:
        ordering = ["started_at"]

    def __str__(self):
        return "[{}] - {}".format(
            self.integration_config.company.name,
            self.integration_config.name,
        )
