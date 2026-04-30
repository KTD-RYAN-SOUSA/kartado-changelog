import uuid

from django.contrib.gis.db import models
from django.db.models import JSONField
from simple_history.models import HistoricalRecords

from apps.companies.models import Company
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import Reporting
from apps.users.models import User


class Service(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.TextField()  # Required
    unit_price = models.FloatField(default=0)  # Not null, default=0
    total_amount = models.FloatField(default=0)  # Not null, default=0
    current_balance = models.FloatField(default=0)  # Not null, default=0
    adjustment_coefficient = models.FloatField(default=1)  # Not null, default=1
    kind = models.CharField(max_length=200, blank=True)
    group = models.CharField(max_length=200, blank=True)
    code = models.CharField(max_length=200, blank=True)
    unit = models.TextField()  # Required

    initial_price = models.FloatField(
        null=True, blank=True, default=0
    )  # not required - read-only

    # Required
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_service"
    )

    occurrence_types = models.ManyToManyField(
        OccurrenceType,
        through="ServiceSpecs",
        related_name="occurrences_service",
        blank=True,
    )

    metadata = JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        return "[{}]{} - {}".format(self.company.name, self.uuid, self.name)

    @property
    def get_company_id(self):
        return self.company_id


class ServiceSpecs(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Required
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="service_specs"
    )
    # Required
    occurrence_type = models.ForeignKey(
        OccurrenceType,
        on_delete=models.CASCADE,
        related_name="occurrence_specs",
    )

    formula = JSONField(default=dict)  # Required

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - {}".format(self.occurrence_type, self.service)

    class Meta:
        unique_together = ("service", "occurrence_type")

    @property
    def get_company_id(self):
        return self.service.company_id


class Measurement(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    number = models.CharField(max_length=100)  # Required

    start_date = models.DateTimeField(default=None)  # Required
    end_date = models.DateTimeField(default=None)  # Required
    created_at = models.DateTimeField(auto_now_add=True)  # Auto fill

    # Required
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_measurement",
        null=True,
    )
    # Auto fill
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    # Auto fill
    previous_measurement = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="next_measurement",
    )
    approved = models.BooleanField(default=False)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - {}".format(self.company.name, self.number)

    @property
    def get_company_id(self):
        return self.company_id


class ServiceUsage(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Required
    reporting = models.ForeignKey(
        Reporting, on_delete=models.CASCADE, related_name="reporting_usage"
    )
    # Required
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="service_usage"
    )
    # not required - can be null
    measurement = models.ForeignKey(
        Measurement,
        on_delete=models.SET_NULL,
        related_name="measurement_usage",
        null=True,
        blank=True,
    )

    amount = models.FloatField(
        null=True, blank=True, default=None
    )  # not required - read-only
    formula = JSONField(default=dict, null=True, blank=True)  # not required - read-only

    def __str__(self):
        return "[{}] - {}".format(self.reporting, self.service)

    @property
    def get_company_id(self):
        return self.reporting.company_id


class MeasurementService(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Required
    service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        related_name="service_measurements",
        null=True,
    )
    # Required
    measurement = models.ForeignKey(
        Measurement,
        on_delete=models.CASCADE,
        related_name="measurement_services",
    )

    unit_price = models.FloatField(
        null=True, blank=True, default=None
    )  # not required - read-only
    balance = models.FloatField(
        null=True, blank=True, default=None
    )  # not required - read-only
    adjustment_coefficient = models.FloatField(
        null=True, blank=True, default=None
    )  # not required - read-only

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - {}".format(self.measurement, self.service)

    @property
    def get_company_id(self):
        return self.service.company_id


class GoalAggregate(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Required
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_goal"
    )

    start_date = models.DateTimeField(default=None)  # required
    end_date = models.DateTimeField(default=None)  # required
    number = models.CharField(max_length=100, default="", blank=True)
    group_goals = JSONField(default=dict, null=True, blank=True)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] : {} - {}".format(
            self.company.name, self.start_date, self.end_date
        )

    @property
    def get_company_id(self):
        return self.company_id


class Goal(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Required
    aggregate = models.ForeignKey(
        GoalAggregate, on_delete=models.CASCADE, related_name="goals"
    )
    # Required
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="service_goal"
    )
    # Required
    occurrence_type = models.ForeignKey(
        OccurrenceType, on_delete=models.CASCADE, related_name="type_goal"
    )
    amount = models.FloatField(default=0)  # required
    internal = models.BooleanField(default=False)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] : {}".format(self.aggregate, self.occurrence_type.name)

    class Meta:
        unique_together = ("aggregate", "occurrence_type")

    @property
    def get_company_id(self):
        return self.aggregate.company_id
