import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.companies.models import Company
from apps.service_orders.models import ServiceOrder
from apps.users.models import User
from RoadLabsAPI.storage_backends import PrivateMediaStorage


class File(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        related_name="company_files",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
        blank=True,
    )
    description = models.TextField(blank=True)
    md5 = models.TextField(blank=True)
    upload = models.FileField(storage=PrivateMediaStorage(), blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    datetime = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_generic_files",
    )
    kind = models.CharField(max_length=100, blank=True, default="")
    url = models.TextField(default="", blank=True, null=True)

    # Below the mandatory fields for generic relation
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, blank=True, null=True
    )
    object_id = models.UUIDField(blank=True, null=True)
    content_object = GenericForeignKey("content_type", "object_id")

    history = HistoricalRecords(history_change_reason_field=models.TextField(null=True))

    def __str__(self):
        return "{} - {}".format(self.description, self.uploaded_at)

    @property
    def get_company_id(self):
        if hasattr(self.content_object, "get_company_id"):
            return self.content_object.get_company_id
        else:
            return None


class FileDownload(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    file = models.FileField(storage=PrivateMediaStorage(), blank=True, null=True)
    file_name = models.TextField(blank=True, null=True)

    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, blank=True, null=True
    )
    object_id = models.UUIDField(blank=True, null=True)
    content_object = GenericForeignKey("content_type", "object_id")

    user_download = models.ManyToManyField(
        "users.User", verbose_name="Download por", related_name="files_download"
    )

    service_order = models.ForeignKey(
        ServiceOrder,
        related_name="service_order_file_downloads",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )

    access_token = models.BooleanField("User ID required", default=True)

    def __str__(self):
        return "{} - {}".format(
            self.object_id,
            self.content_type.app_label,
        )

    @property
    def get_company_id(self):
        if hasattr(self.content_object, "get_company_id"):
            return self.content_object.get_company_id
        else:
            return None

    class Meta:
        ordering = ["-created_at"]


class GenericFile(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    file = models.FileField(storage=PrivateMediaStorage(), blank=True, null=True)

    def __str__(self):
        return "[{}] {}".format(
            self.created_at,
            self.file.name,
        )

    class Meta:
        ordering = ["-created_at"]
