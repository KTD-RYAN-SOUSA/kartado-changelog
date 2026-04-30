import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import JSONField
from simple_history.models import HistoricalRecords

from apps.companies.models import Company, CompanyGroup
from apps.users.models import User


class ToDoAction(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_group = models.ForeignKey(
        CompanyGroup, on_delete=models.CASCADE, related_name="todos_actions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="todo_actions",
    )
    name = models.TextField()

    default_options = models.CharField(
        max_length=100,
        choices=[("see", "see"), ("resource", "resource")],
        null=True,
        blank=True,
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = ["created_at"]

    def __str__(self):
        return "[{}]: {}".format(self.company_group.name, self.name)


class ToDoActionStep(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    todo_action = models.ForeignKey(
        ToDoAction, related_name="action_steps", on_delete=models.CASCADE
    )
    approval_step = models.ForeignKey(
        "approval_flows.ApprovalStep",
        related_name="action_steps",
        on_delete=models.CASCADE,
    )
    destinatary = models.CharField(
        max_length=100,
        choices=[
            ("responsible", "responsible"),
            ("notified", "notified"),
            ("creator", "creator"),
        ],
    )

    history = HistoricalRecords()

    def __str__(self):
        return "[{}]: {}".format(self.todo_action.name, self.approval_step.name)


class ToDo(models.Model):
    # If a field is changed, remove or added here remember to update the generate_todo() helper
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_todos"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField(default=None, null=True)
    read_at = models.DateTimeField(default=None, null=True, blank=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_todos",
    )
    responsibles = models.ManyToManyField(User, related_name="responsible_todos")
    action = models.ForeignKey(
        ToDoAction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="todos",
    )
    description = JSONField(default=dict, blank=True, null=True)
    is_done = models.BooleanField(default=False)
    url = models.TextField(blank=True)
    destination = models.TextField(blank=True)

    # resource field
    resource_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="resource_todos",
    )
    resource_obj_id = models.UUIDField(blank=True, null=True)
    resource = GenericForeignKey("resource_type", "resource_obj_id")

    # destination_resource field
    destination_resource_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="destination_resource_todos",
    )
    destination_resource_obj_id = models.UUIDField(blank=True, null=True)
    destination_resource = GenericForeignKey(
        "destination_resource_type", "destination_resource_obj_id"
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = ["created_at"]

    def __str__(self):
        return "[{}]: {} - {}".format(
            self.company.name,
            self.action.name if self.action else "",
            self.due_at,
        )

    @property
    def get_company_id(self):
        return self.company_id
