import uuid

from django.contrib.gis.db import models
from django.db.models import JSONField
from simple_history.models import HistoricalRecords

from apps.companies.models import Company, Firm
from apps.to_dos.models import ToDoAction
from apps.users.models import User
from helpers.fields import ColorField


class ApprovalFlow(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.TextField(blank=True)
    target_model = models.CharField(max_length=200)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_approval_flows"
    )

    history = HistoricalRecords()

    def __str__(self):
        return "[{}]: {} - {}".format(self.company.name, self.name, self.target_model)

    @property
    def get_company_id(self):
        return self.company_id


class ApprovalStep(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.TextField(blank=True)

    approval_flow = models.ForeignKey(
        ApprovalFlow,
        on_delete=models.CASCADE,
        related_name="approval_flow_steps",
    )

    next_steps = models.ManyToManyField(
        "self",
        through="ApprovalTransition",
        related_name="previous_steps",
        symmetrical=False,
    )

    field_options = JSONField(default=dict, blank=True, null=True)

    responsible_firms = models.ManyToManyField(
        Firm, related_name="firm_steps", blank=True
    )
    responsible_users = models.ManyToManyField(
        User, related_name="user_steps", blank=True
    )
    responsible_created_by = models.BooleanField(default=False)
    responsible_supervisor = models.BooleanField(default=False)
    responsible_firm_entity = models.BooleanField(default=False)
    responsible_firm_manager = models.BooleanField(default=False)
    auto_execute_transition = models.BooleanField(default=False)

    responsible_json_logic = JSONField(default=dict, blank=True, null=True)

    action = models.ManyToManyField(
        ToDoAction,
        through="to_dos.ToDoActionStep",
        related_name="approval_steps",
    )

    color = ColorField(default="#FF0000")

    history = HistoricalRecords()

    def __str__(self):
        return "[{}]: {}".format(self.get_company_name, self.name)

    @property
    def get_company_id(self):
        return self.approval_flow.company_id

    @property
    def get_company_name(self):
        return self.approval_flow.company.name


class ApprovalTransition(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.TextField(blank=True)

    origin = models.ForeignKey(
        ApprovalStep,
        on_delete=models.CASCADE,
        related_name="origin_transitions",
    )
    destination = models.ForeignKey(
        ApprovalStep, on_delete=models.CASCADE, related_name="dest_transitions"
    )
    condition = JSONField(default=dict, blank=True, null=True)
    callback = JSONField(default=dict, blank=True, null=True)
    button = JSONField(default=dict, blank=True, null=True)
    order = models.CharField(blank=True, max_length=10)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}]: {} - {}".format(
            self.name, self.origin.name, self.destination.name
        )

    @property
    def get_company_id(self):
        return self.origin.approval_flow.company_id
