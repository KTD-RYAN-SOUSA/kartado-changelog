import uuid

from django.contrib.gis.db import models
from django.db.models import JSONField

from apps.companies.models import Company
from apps.users.models import User


class FormsIARequest(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="forms_ia_requests",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="user_forms_ia_requests",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    occurrence_kind = models.CharField(max_length=200)
    name = models.TextField()
    input_text = models.TextField()

    request_id = models.CharField(max_length=255, null=True, blank=True)
    output_json = JSONField(default=dict, blank=True, null=True)

    done = models.BooleanField(default=False)
    error = models.BooleanField(default=False)
    error_message = models.TextField(null=True, blank=True)

    def __str__(self):
        return "{}: {} - {}".format(
            self.company.name,
            self.name,
            self.created_at.strftime("%d/%m/%Y, %H:%M:%S"),
        )

    @property
    def get_company_id(self):
        return self.company_id
