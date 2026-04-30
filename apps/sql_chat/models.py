import uuid

from django.contrib.gis.db import models
from django.db.models import JSONField

from apps.companies.models import Company
from apps.users.models import User


class SqlChatMessage(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chat_id = models.UUIDField(db_index=True)
    session_id = models.CharField(max_length=100, null=True, blank=True)
    request_id = models.CharField(max_length=100, null=True, blank=True)

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="sql_chat_messages",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="user_sql_chat_messages",
        null=True,
        blank=True,
    )

    input = models.TextField()
    status = models.CharField(max_length=50, default="STARTED")
    result = JSONField(default=dict, blank=True)
    error = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.company.name}: {self.chat_id} - {self.status}"

    @property
    def get_company_id(self):
        return self.company_id
