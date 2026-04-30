from typing import Union
from uuid import UUID, uuid4

from django.db import models
from simple_history.models import HistoricalRecords


class AbstractBaseModel(models.Model):
    """Base model containing fields that should always be included in this project's models"""

    # Basic info
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_%(class)ss",
    )
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_%(class)ss",
    )

    # Activate history
    history = HistoricalRecords(
        inherit=True,
        related_name="history_%(class)ss",
        history_change_reason_field=models.TextField(null=True),
    )

    @property
    def get_company_id(self) -> Union[UUID, None]:
        """Returns the ID of the Company responsible for the permissions"""
        return self.company.pk if self.company else None

    def __str__(self) -> str:
        raise NotImplementedError(
            "Please provide a proper __str__ method for this model"
        )

    class Meta:
        abstract = True


class HashHistoricalModel(models.Model):
    """
    Abstract model for history models to save hashs
    """

    geometry_hash = models.TextField(blank=True, null=True)

    class Meta:
        abstract = True
