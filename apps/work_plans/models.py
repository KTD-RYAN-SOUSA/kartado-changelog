import uuid

from django.db import models
from django.db.models import JSONField
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Company, Firm, SubCompany
from apps.occurrence_records.models import OccurrenceType
from apps.service_orders.models import ServiceOrderActionStatus
from apps.users.models import User
from apps.work_plans.const.async_batches import BATCH_TYPE_CHOICES
from helpers.models import AbstractBaseModel


class Job(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    number = models.CharField(max_length=100, blank=True, default="")
    title = models.CharField(max_length=200, blank=True)
    description = models.CharField(max_length=1000, blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(blank=True, null=True)
    progress = models.FloatField(default=0)
    executed_reportings = models.IntegerField(default=0)
    reporting_count = models.IntegerField(default=0)

    worker = models.ForeignKey(
        User,
        related_name="user_jobs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    firm = models.ForeignKey(
        Firm,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="firm_jobs",
    )
    inspection = models.ForeignKey(
        "reportings.Reporting",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inspection_jobs",
    )
    parent_inventory = models.ForeignKey(
        "reportings.Reporting",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_jobs",
    )

    metadata = JSONField(default=dict, blank=True, null=True)

    created_by = models.ForeignKey(
        User,
        related_name="created_by_jobs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    archived = models.BooleanField(default=False)

    # Auto-scheduling fields
    is_automatic = models.BooleanField(default=False)
    has_auto_allocated_reportings = models.BooleanField(default=False)

    # Batch processing fields
    creating_batches = models.BooleanField(default=False, blank=False)
    pending_inventory_to_reporting_id = JSONField(default=None, blank=True, null=True)
    total_inventory_batches = models.IntegerField(default=0)
    total_reporting_in_reporting_batches = models.IntegerField(default=0)

    # watchers
    watcher_firms = models.ManyToManyField(
        Firm, related_name="watcher_firm_jobs", blank=True
    )
    watcher_users = models.ManyToManyField(
        User, related_name="watcher_user_jobs", blank=True
    )
    watcher_subcompanies = models.ManyToManyField(
        SubCompany, related_name="watcher_subcompanies_jobs", blank=True
    )
    last_notification_sent_at = models.DateTimeField(blank=True, null=True)

    history = HistoricalRecords(excluded_fields=["pending_inventory_to_reporting_id"])

    def __str__(self):
        worker_name = self.worker.username if self.worker else "Sem usuário definido"
        end_date = self.end_date if self.end_date else ""
        return "[{}][{}] - {} - {}".format(
            self.company.name, worker_name, self.start_date, end_date
        )

    @property
    def get_company_id(self):
        return self.company_id


class JobAsyncBatch(AbstractBaseModel):
    """
    Meant to queue Inventory to Inspection processing batch by batch instead of
    the whole queryset in one call.
    """

    in_progress = models.BooleanField(default=False, blank=False)
    batch_type = models.CharField(max_length=100, choices=BATCH_TYPE_CHOICES)
    job = models.ForeignKey(
        Job, on_delete=models.CASCADE, related_name="job_async_batches"
    )
    in_job_status = models.ForeignKey(
        ServiceOrderActionStatus,
        on_delete=models.CASCADE,
        related_name="in_job_status_async_batches",
    )
    approval_step = models.ForeignKey(
        ApprovalStep,
        on_delete=models.SET_NULL,
        related_name="approval_step_async_batches",
        blank=True,
        null=True,
    )
    menu = models.ForeignKey(
        "reportings.RecordMenu",
        on_delete=models.SET_NULL,
        related_name="menu_async_batches",
        blank=True,
        null=True,
    )

    inventories = models.ManyToManyField(
        "reportings.Reporting", blank=True, related_name="inventory_async_batches"
    )
    occurrence_types = models.ManyToManyField(
        OccurrenceType, blank=True, related_name="occurrence_type_async_batches"
    )
    found_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"[{self.company.name}] {self.batch_type} {'[In Progress]' if self.in_progress else ''}: {self.inventories.count()} Inventory items in this batch"


class NoticeViewManager(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notice = models.CharField(max_length=30)
    views_quantity_limit = models.IntegerField(default=0)

    def __str__(self):
        return "[{}] - {}".format(self.notice, str(self.views_quantity_limit))


class UserNoticeView(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_user_notice_views",
    )
    notice_view_manager = models.ForeignKey(
        NoticeViewManager, on_delete=models.CASCADE, related_name="notice_views"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_notice_views"
    )
    views_quantity = models.IntegerField(default=0)

    def __str__(self):
        return "[{}]: {} ({})".format(
            self.company, self.user.username, self.views_quantity
        )

    @property
    def get_company_id(self):
        return self.company_id
