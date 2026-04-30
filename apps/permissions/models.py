import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import JSONField
from simple_history.models import HistoricalRecords


class UserPermission(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    companies = models.ManyToManyField(
        "companies.Company", related_name="permission_companies"
    )
    name = models.CharField(max_length=100)
    permissions = JSONField(default=dict, blank=True, null=True)
    is_inactive = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)

    history = HistoricalRecords()

    def __str__(self):
        companies_names = [company.name for company in self.companies.all()]
        return "{} - {}".format(companies_names, self.name)

    @property
    def get_company_id(self):
        return self.companies.first().uuid


class PermissionOccurrenceKindRestriction(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_permission = models.ForeignKey(
        UserPermission,
        on_delete=models.CASCADE,
        related_name="occurrence_kind_restrictions",
    )
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
    )
    allowed_occurrence_kinds = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        default=list,
    )

    history = HistoricalRecords()

    class Meta:
        unique_together = ("user_permission", "company")

    def __str__(self):
        return f"{self.user_permission.name} - {self.company.name}"
