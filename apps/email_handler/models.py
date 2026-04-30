import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import JSONField
from simple_history.models import HistoricalRecords

from apps.companies.models import Company
from apps.files.models import FileDownload
from apps.users.models import User


class QueuedEmail(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company,
        related_name="company_emails",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    send_to_users = models.ManyToManyField(User)
    title = models.TextField()
    content_plain_text = models.TextField()
    content_html = models.TextField()

    cleared = models.BooleanField(default=False)
    in_progress = models.BooleanField(default=False)
    sent = models.BooleanField(default=False)
    error = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    send_anyway = models.BooleanField(default=False)
    custom_headers = JSONField(default=dict, blank=True, null=True)

    # Judiciary emails
    issuer = models.ForeignKey(
        User,
        related_name="issued_emails",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    file_download = models.ForeignKey(
        FileDownload,
        related_name="file_emails",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    opened_at = models.DateTimeField(blank=True, null=True)

    # Below the mandatory fields for generic relation
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, blank=True, null=True
    )
    object_id = models.UUIDField(blank=True, null=True)
    content_object = GenericForeignKey("content_type", "object_id")

    history = HistoricalRecords(
        excluded_fields=[
            "content_plain_text",
            "content_html",
            "custom_headers",
        ]
    )

    def __str__(self):
        sent_text = "ENVIADO" if self.sent else "NA FILA"
        return "{} - {} - {}".format(self.title, sent_text, self.created_at)

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = ["created_at"]

    @property
    def get_company_id(self):
        return self.company_id


class EmailBlacklist(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(null=True, unique=True)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    def __str__(self):
        return "{} - {}".format(self.email, self.created_at.strftime("%d/%m/%Y"))


class QueuedEmailEvent(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    queued_email = models.ForeignKey(
        QueuedEmail, related_name="email_events", on_delete=models.CASCADE
    )

    company = models.ForeignKey(
        Company,
        related_name="company_email_events",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    event_type = models.TextField()
    properties = JSONField(default=dict, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "{} - {} - {}".format(
            self.event_type,
            self.queued_email.title,
            self.created_at.strftime("%d-%m-%Y %H:%M:%S"),
        )

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = ["created_at"]

    @property
    def get_company_id(self):
        return self.company_id
