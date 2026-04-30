import json
import logging
from abc import abstractmethod
from uuid import uuid4

import sentry_sdk
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.companies.models import Company
from apps.notifications.strategies.firebase import FirebaseNotificationService
from apps.users.models import User


# Create your models here.
class Device(models.Model):
    """User android or ios device to keep the push token"""

    id = models.AutoField(primary_key=True)
    device_id = models.CharField(
        max_length=255,
    )
    push_token = models.CharField(
        max_length=512,
    )

    class Meta:
        pass

    def send(self, push_message, firebase_token):
        """Use FirebaseNotificationService to send the push notification to firebase"""

        body = (
            push_message.body
            if hasattr(push_message, "body") and push_message.body
            else None
        )

        response = FirebaseNotificationService.send(
            title=push_message.message,
            body=body,
            token=self.push_token,
            extra_payload=push_message.extra_payload,
            firebase_token=firebase_token,
        )
        return response


class Notification(models.Model):
    """Abstract model to general notifications"""

    id = models.AutoField(primary_key=True)
    message = models.TextField(default="", null=True)
    body = models.TextField(blank=True, null=True)
    extra_payload = models.TextField(blank=True, null=True)
    cleared = models.BooleanField(default=False)
    in_progress = models.BooleanField(default=False)
    sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    devices = models.ManyToManyField(Device, related_name="user_devices")
    company = models.ForeignKey(
        Company,
        related_name="company_notifications",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    @abstractmethod
    def process(self):
        """Each notifications type implements your unique process"""
        pass

    class Meta:
        """abstract true to dont create tables for this model"""

        abstract = True


class PushNotification(Notification):
    """Model to push notifications"""

    requires_firebase = True

    sound = models.TextField(blank=True, null=True)
    has_new_content = models.BooleanField(default=False)
    context_id = models.TextField(default="none", null=True)
    context = models.TextField(default="default", null=True)
    badge_count = models.SmallIntegerField(default=0)
    message_type = models.PositiveSmallIntegerField(default=0)

    users = models.ManyToManyField(
        User, through="UserPush", related_name="user_push_notifications"
    )

    history = HistoricalRecords(excluded_fields=["message", "extra_payload", "sound"])

    def process(self, firebase_token):
        """
        Process PushNotifications and send to all devices
        """
        try:
            if self.extra_payload:
                payload_str = str(self.extra_payload).replace("'", '"')
                self.extra_payload = json.loads(payload_str)
            else:
                self.extra_payload = {}
        except (json.JSONDecodeError, AttributeError) as e:
            logging.warning(f"Error parsing extra_payload: {e}")
            self.extra_payload = {}

        for device in self.devices.all():
            try:
                response = device.send(push_message=self, firebase_token=firebase_token)

                if hasattr(response, "get") and (
                    "UNREGISTERED" in str(response.get("error", ""))
                    or "Requested entity was not found"
                    in str(response.get("error", ""))
                ):
                    sentry_sdk.capture_message(
                        f"Removendo device {device} por token inválido (via response)",
                        "Warning",
                    )
                    device.delete()

            except Exception as e:
                logging.error("exception trying to send push", exc_info=True)
                sentry_sdk.capture_exception(repr(e))

        self.sent = True
        self.in_progress = False
        self.save()

    def __str__(self):
        sent_text = "ENVIADO" if self.sent else "NA FILA"
        return "{} - {} - {}".format(self.message, sent_text, self.created_at)

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = ["created_at"]


class UserPush(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="push_user")
    push_message = models.ForeignKey(
        PushNotification, on_delete=models.CASCADE, related_name="push_message"
    )
    read = models.BooleanField(default=False)

    history = HistoricalRecords()

    def __str__(self):
        sent_text = "ENVIADO" if self.push_message.sent else "NA FILA"
        read_text = "LIDO" if self.read else "NÃO LIDO"
        return "[{}] - {} - {} - {}".format(
            self.user.username, self.push_message.message, sent_text, read_text
        )

    @property
    def get_company_id(self):
        return self.push_message.company_id
