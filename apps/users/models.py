import random
from uuid import uuid4

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import JSONField
from django.utils import timezone
from simple_history.models import HistoricalRecords

from helpers.validators.brazilian_documents import validate_CPF
from RoadLabsAPI.storage_backends import PrivateMediaStorage

from .const.notification_types import NOTIFICATION_TYPES
from .const.time_intervals import DEFAULT_INTERVAL, NOTIFICATION_INTERVALS


def default_jwt_secret():
    jwt_secret = "".join(
        [
            random.SystemRandom().choice(
                "abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)"
            )
            for i in range(50)
        ]
    )
    return jwt_secret


class User(AbstractUser):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    cpf = models.CharField(
        unique=True,
        blank=True,
        null=True,
        max_length=50,
        validators=[validate_CPF],
    )
    avatar = models.FileField(
        storage=PrivateMediaStorage(),
        upload_to="avatars/",
        blank=True,
        default=None,
        null=True,
    )
    metadata = JSONField(default=dict, null=True, blank=True)
    configuration = JSONField(default=dict, null=True, blank=True)
    push_devices = models.ManyToManyField(
        "notifications.Device", related_name="device_users"
    )

    jwt_secret = models.CharField(max_length=50, default=default_jwt_secret)
    saml_idp = models.CharField(blank=True, null=True, max_length=255)
    saml_nameid = models.CharField(unique=True, blank=True, null=True, max_length=255)
    company_group = models.ForeignKey(
        "companies.CompanyGroup",
        related_name="group_users",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    supervisor = models.ForeignKey(
        "self",
        related_name="supervisor_users",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    is_supervisor = models.BooleanField(default=False)
    is_internal = models.BooleanField(default=False)
    has_accepted_tos = models.BooleanField(default=False)
    responsible = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsible_users",
    )
    birth_date = models.DateTimeField(blank=True, null=True)
    firm_name = models.TextField(null=True, blank=True)
    phone = models.TextField(null=True, blank=True)
    legacy_uuid = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    auth_error = models.CharField(blank=True, null=True, max_length=255)

    history = HistoricalRecords()

    def __str__(self):
        return "{} - {} {}".format(self.username, self.first_name, self.last_name)

    @property
    def full_name(self):
        return self.get_full_name()

    def get_companies_permissions(self) -> dict:
        data = {}
        try:
            for company in self.companies.all():
                data[company.name] = {}
                for user_permission in company.permission_companies.all():
                    data[company.name][
                        user_permission.name
                    ] = user_permission.permissions
        except Exception:
            pass
        return data


class UserNotification(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_notifications"
    )
    companies = models.ManyToManyField(
        "companies.Company", related_name="user_notifications"
    )
    notification = models.TextField()
    notification_type = models.CharField(max_length=5, choices=NOTIFICATION_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    # Notification Debounce
    in_progress = models.BooleanField(default=False)
    time_interval = models.DurationField(
        choices=NOTIFICATION_INTERVALS, default=DEFAULT_INTERVAL
    )
    preferred_time = models.TimeField(blank=True, null=True)
    last_notified = models.DateTimeField(default=None, blank=True, null=True)
    last_checked = models.DateTimeField(default=timezone.now)
    debounce_data = JSONField(null=True, blank=True)

    @property
    def get_company_id(self):
        return self.companies.first()

    class Meta:
        ordering = ["notification"]
        unique_together = [
            "user",
            "notification",
            "notification_type",
            "time_interval",
        ]

    def __str__(self):
        return "[{}] [{}]: {}{}".format(
            self.user.get_full_name(),
            self.notification_type,
            self.notification,
            " (IN PROGRESS)" if self.in_progress else "",
        )


class UserSignature(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_signatures"
    )
    company = models.ForeignKey(
        "companies.Company",
        related_name="company_signatures",
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    md5 = models.TextField(blank=True)
    upload = models.FileField(storage=PrivateMediaStorage())

    class Meta:
        unique_together = ["user", "company"]

    @property
    def get_company_id(self):

        return self.company_id

    def __str__(self):
        return "[{}] {}".format(self.company.name, self.user.username)
