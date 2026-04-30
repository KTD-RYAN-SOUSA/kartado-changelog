import uuid
from datetime import datetime

from django.contrib.gis.db import models
from django.db.models import JSONField
from simple_history.models import HistoricalRecords

from apps.companies.models import Company
from apps.users.models import User


class TileLayer(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    type = models.TextField()
    name = models.TextField()
    description = models.TextField(default="")
    companies = models.ManyToManyField(Company, related_name="tile_layers", blank=True)
    provider_info = JSONField(default=dict, blank=True)
    mapbox_styles = JSONField(default=dict, blank=True)

    history = HistoricalRecords()

    def __str__(self):
        return "{} {}".format([a.name for a in self.companies.all()], self.name)

    @property
    def get_company_id(self):
        return self.companies.first().uuid


class ShapeFile(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="shape_files"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    synced_at = models.DateTimeField(default=datetime.now)

    name = models.TextField()
    description = models.TextField(default="", blank=True)
    companies = models.ManyToManyField(Company, related_name="shape_files", blank=True)
    private = models.BooleanField(default=False)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )

    geometry = models.GeometryCollectionField(null=True, blank=True)
    properties = JSONField(default=list, blank=True)

    metadata = JSONField(default=dict, blank=True)
    enable_default = models.BooleanField(default=False)

    def __str__(self):
        return "{} {}".format([a.name for a in self.companies.all()], self.name)

    @property
    def get_company_id(self):
        return self.companies.first().uuid
