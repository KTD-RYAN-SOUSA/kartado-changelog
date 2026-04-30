import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.db.models import JSONField
from simple_history.models import HistoricalRecords

from apps.companies.models import Company, CompanyGroup, Firm
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import RecordMenu, Reporting
from apps.resources.models import ContractItemAdministration, ContractItemUnitPrice
from apps.service_orders.models import ServiceOrder, ServiceOrderActionStatus
from apps.users.models import User
from RoadLabsAPI.storage_backends import PrivateMediaStorage

from .const import (
    mobile_sync_connection_options,
    reporting_export_types,
    search_tag_kinds,
)


class Template(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    model_name = models.CharField(max_length=60, blank=False)
    item_name = models.CharField(max_length=60, blank=False)
    companies = models.ManyToManyField(Company, related_name="template_companies")

    options = JSONField(default=dict, blank=True, null=True)
    validation = JSONField(default=dict, blank=True, null=True)

    history = HistoricalRecords()

    def __str__(self):
        return "{}: {}".format(self.model_name, self.item_name)

    @property
    def get_company_id(self):
        return self.companies.first().uuid


class Log(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    date = models.DateTimeField(default=None)  # Required

    # not-required
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_log",
        blank=True,
        null=True,
    )

    description = JSONField(default=dict)  # Required

    def __str__(self):
        if not self.company:
            return "{}: {}".format("Sem Company", self.date)
        return "{}: {}".format(self.company.name, self.date)

    @property
    def get_company_id(self):
        return self.company_id


class CanvasList(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=100)
    order = models.IntegerField(default=0)
    color = models.CharField(max_length=100, default="#FF0000")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    service_order = models.ForeignKey(
        ServiceOrder,
        on_delete=models.CASCADE,
        related_name="service_canvas_lists",
    )

    history = HistoricalRecords()

    def __str__(self):
        return "{}: {} - {}".format(
            self.service_order.company.name, self.name, self.kind
        )

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = ["created_at"]

    @property
    def get_company_id(self):
        return self.service_order.company_id


class CanvasCard(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=100)
    color = models.CharField(max_length=100, default="#FF0000")
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    extra_info = JSONField(default=dict, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    canvas_list = models.ForeignKey(
        CanvasList, on_delete=models.CASCADE, related_name="list_canvas_cards"
    )

    history = HistoricalRecords()

    def __str__(self):
        return "{}: {}".format(self.canvas_list.service_order.company.name, self.name)

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = ["created_at"]

    @property
    def get_company_id(self):
        return self.canvas_list.service_order.company_id


class AppVersion(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    notification_title = models.TextField(blank=True, null=True)
    notification_body = models.TextField(blank=True, null=True)
    target_app = models.TextField(blank=True, null=True)
    target_platform = models.TextField(blank=True, null=True)

    start_date = models.DateTimeField(default=None, blank=True, null=True)
    deadline = models.DateTimeField(default=None, blank=True, null=True)

    version = JSONField(default=dict, blank=True, null=True)

    history = HistoricalRecords()

    def __str__(self):
        return "{}: {}-{} - {}".format(
            self.notification_title,
            self.target_app,
            self.target_platform,
            self.start_date,
        )


class ExportRequest(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_export_requests",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="user_export_requests",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )
    json_zip = JSONField(default=dict, blank=True, null=True)
    done = models.BooleanField(default=False)
    error = models.BooleanField(default=False)

    def __str__(self):
        if self.created_by:
            return "{}: {} - {}".format(
                self.company.name,
                self.created_by.username,
                self.created_at.strftime("%d/%m/%Y, %H:%M:%S"),
            )
        return "{}: {}".format(
            self.company.name, self.created_at.strftime("%d/%m/%Y, %H:%M:%S")
        )

    @property
    def get_company_id(self):
        return self.company_id


class MobileSync(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_syncs"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="user_syncs",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    kind = models.TextField(null=True, blank=True)
    done = models.BooleanField(default=False)
    email_sent = models.BooleanField(default=False)

    version = models.TextField(null=True, blank=True)
    connection = models.CharField(
        max_length=10,
        choices=mobile_sync_connection_options.CONNECTION_CHOICES,
        null=True,
        blank=True,
    )
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    speed = models.FloatField(blank=True, null=True)
    has_error = models.BooleanField(default=False)
    time_spent = models.FloatField(blank=True, null=True)
    sync_post_data = JSONField(default=dict, blank=True, null=True)
    sync_get_data = JSONField(default=dict, blank=True, null=True)
    sync_steps_duration_data = JSONField(default=dict, blank=True, null=True)

    history = HistoricalRecords()

    def __str__(self):
        if self.created_by:
            return "{}: {} - {} - {}".format(
                self.company.name,
                self.kind,
                self.created_by.username,
                self.created_at.strftime("%d/%m/%Y, %H:%M:%S"),
            )
        return "{}: {} - {}".format(
            self.company.name,
            self.kind,
            self.created_at.strftime("%d/%m/%Y, %H:%M:%S"),
        )

    @property
    def get_company_id(self):
        return self.company_id


class ActionLog(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_logs",
        null=True,
        blank=True,
    )
    company_group = models.ForeignKey(
        CompanyGroup,
        related_name="company_group_logs",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_logs")
    created_at = models.DateTimeField(auto_now_add=True)

    action = models.TextField(null=True, blank=True)
    user_ip = models.TextField(null=True, blank=True)
    user_port = models.TextField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    # Below the mandatory fields for generic relation
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, blank=True, null=True
    )
    object_id = models.UUIDField(blank=True, null=True)
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["user"]),
            models.Index(fields=["company"]),
            models.Index(fields=["company_group"]),
        ]

    def __str__(self):
        if self.company:
            return "[{}]: {} - {} - {}".format(
                self.company.name,
                self.action,
                self.user.get_full_name(),
                self.created_at.strftime("%d/%m/%Y, %H:%M:%S"),
            )
        elif self.company_group:
            return "[{}]: {} - {} - {}".format(
                self.company_group.name,
                self.action,
                self.user.get_full_name(),
                self.created_at.strftime("%d/%m/%Y, %H:%M:%S"),
            )
        else:
            return "{} - {} - {}".format(
                self.action,
                self.user.get_full_name(),
                self.created_at.strftime("%d/%m/%Y, %H:%M:%S"),
            )

    @property
    def get_company_id(self):
        return self.company_id


class SearchTag(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="search_tags"
    )

    name = models.CharField(max_length=100, blank=True)
    kind = models.CharField(
        max_length=100,
        choices=search_tag_kinds.SEARCH_TAG_KINDS,
        default=search_tag_kinds.SELECT_OPTION,
    )
    level = models.IntegerField(default=0)
    parent_tags = models.ManyToManyField(
        "self", blank=True, related_name="child_tags", symmetrical=False
    )
    description = models.TextField(blank=True)
    redirect = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return "{} - {} - {} - {}".format(
            self.company.name, self.level, self.kind, self.name
        )


class SearchTagOccurrenceType(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)

    search_tags = models.ManyToManyField(
        SearchTag, related_name="occurrence_type_relationships"
    )

    occurrence_type = models.ForeignKey(
        "occurrence_records.OccurrenceType",
        on_delete=models.CASCADE,
        related_name="search_tag_relationships",
    )

    def __str__(self):
        return "{} - {}".format(self.company.name, self.occurrence_type.name)


class ExcelImport(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="excel_imports"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="excel_imports",
        null=True,
        blank=True,
    )

    name = models.TextField(blank=True)
    zip_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )
    excel_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )
    preview_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )

    done = models.BooleanField(default=False)
    remaining_parts = models.IntegerField(default=0)
    error = models.BooleanField(default=False)
    generating_preview = models.BooleanField(default=False)
    uploading_zip_images = models.BooleanField(default=False)
    is_over_limit = models.BooleanField(default=False)
    is_forbidden = models.BooleanField(default=False)

    reportings = models.ManyToManyField(
        Reporting, through="ExcelReporting", related_name="excel_imports"
    )
    contract_items_unit_price = models.ManyToManyField(
        ContractItemUnitPrice,
        through="ExcelContractItemUnitPrice",
        related_name="excel_imports",
    )
    contract_items_administration = models.ManyToManyField(
        ContractItemAdministration,
        through="ExcelContractItemAdministration",
        related_name="excel_imports",
    )

    def __str__(self):
        return "[{}] {}: {}".format(self.company.name, self.uuid, self.name)

    @property
    def get_company_id(self):
        return self.company_id


class ExcelReporting(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    reporting = models.ForeignKey(
        Reporting, on_delete=models.CASCADE, related_name="excel_reportings"
    )
    excel_import = models.ForeignKey(
        ExcelImport, on_delete=models.CASCADE, related_name="excel_reportings"
    )

    row = models.CharField(max_length=60, blank=True, null=True)
    operation = models.CharField(max_length=60, blank=True, null=True)

    def __str__(self):
        return "[{}] {}: {}".format(
            self.excel_import.company.name, self.excel_import.name, self.row
        )

    @property
    def get_company_id(self):
        return self.excel_import.company_id


class ExcelContractItemUnitPrice(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    contract_item_unit_price = models.ForeignKey(
        ContractItemUnitPrice,
        on_delete=models.CASCADE,
        related_name="excel_contract_items_unit_price",
    )
    excel_import = models.ForeignKey(
        ExcelImport,
        on_delete=models.CASCADE,
        related_name="excel_contract_items_unit_price",
    )

    row = models.CharField(max_length=60, blank=True, null=True)
    operation = models.CharField(max_length=60, blank=True, null=True)

    def __str__(self):
        return "[{}] {}: {}".format(
            self.excel_import.company.name, self.excel_import.name, self.row
        )

    @property
    def get_company_id(self):
        return self.excel_import.company_id


class ExcelContractItemAdministration(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    contract_item_administration = models.ForeignKey(
        ContractItemAdministration,
        on_delete=models.CASCADE,
        related_name="excel_contract_items_administration",
    )
    excel_import = models.ForeignKey(
        ExcelImport,
        on_delete=models.CASCADE,
        related_name="excel_contract_items_administration",
    )

    row = models.CharField(max_length=60, blank=True, null=True)
    operation = models.CharField(max_length=60, blank=True, null=True)

    def __str__(self):
        return "[{}] {}: {}".format(
            self.excel_import.company.name, self.excel_import.name, self.row
        )

    @property
    def get_company_id(self):
        return self.excel_import.company_id


class PDFImport(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="pdf_imports"
    )
    firm = models.ForeignKey(  # Required on serializer
        Firm,
        on_delete=models.SET_NULL,
        related_name="pdf_imports",
        null=True,
        blank=True,
    )
    menu = models.ForeignKey(  # Required on serializer
        RecordMenu, on_delete=models.SET_NULL, related_name="pdf_imports", null=True
    )

    status = models.ForeignKey(  # Required on serializer
        ServiceOrderActionStatus,
        on_delete=models.SET_NULL,
        related_name="pdf_imports",
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="pdf_imports",
        null=True,
        blank=True,
    )

    name = models.TextField(blank=True)
    pdf_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )
    preview_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )

    lane = models.CharField(
        max_length=100, null=True, blank=True
    )  # Required on serializer
    track = models.TextField(null=True, blank=True)
    branch = models.TextField(null=True, blank=True)
    km_reference = models.FloatField(blank=True, null=True)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=100, blank=True, default="")

    done = models.BooleanField(default=False)
    error = models.BooleanField(default=False)

    occurrence_type = models.ForeignKey(
        OccurrenceType,
        null=True,
        on_delete=models.SET_NULL,
        related_name="pdf_import_occurrence",
        blank=True,
    )
    form_data = JSONField(default=dict, blank=True, null=True)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] {}: {}".format(self.company.name, self.uuid, self.name)

    @property
    def get_company_id(self):
        return self.company_id


class CSVImport(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="csv_imports"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="csv_imports",
        null=True,
        blank=True,
    )

    name = models.TextField(blank=True)
    csv_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )
    preview_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )

    done = models.BooleanField(default=False)
    error = models.BooleanField(default=False)

    occurrence_type = models.ForeignKey(
        OccurrenceType,
        on_delete=models.CASCADE,
        related_name="type_csv_imports",
        null=True,
    )
    form_data = JSONField(default=dict, blank=True, null=True)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] {}: {}".format(self.company.name, self.uuid, self.name)

    @property
    def get_company_id(self):
        return self.company_id


class ReportingExport(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_reporting_exports"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="user_reporting_exports",
        null=True,
        blank=True,
    )

    export_type = models.CharField(
        max_length=100,
        default=reporting_export_types.SIMPLE,
        choices=reporting_export_types.REPORTING_EXPORT_TYPES,
    )
    extra_info = JSONField(default=dict)

    is_inventory = models.BooleanField(default=False)

    filters = JSONField(default=dict)

    done = models.BooleanField(default=False)

    error = models.BooleanField(default=False)

    exported_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )

    def __str__(self):
        return "[{}] {}: {}".format(self.company.name, self.uuid, self.export_type)

    @property
    def get_company_id(self):
        return self.company_id


class ExcelDnitReport(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_excel_dnit_reports"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="user_excel_dnit_reports",
        null=True,
        blank=True,
    )

    extra_info = JSONField(default=dict)

    filters = JSONField(default=dict)

    done = models.BooleanField(default=False)

    error = models.BooleanField(default=False)

    exported_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )

    def __str__(self):
        return "[{}] {}: ExcelDnitReport".format(self.company.name, self.uuid)

    @property
    def get_company_id(self):
        return self.company_id


class PhotoReport(models.Model):
    ARTESP_REPORT = "ArtespReport"
    NEW_PHOTO_REPORT = "NewPhotoReport"

    PHOTO_REPORT_TYPES = [
        (ARTESP_REPORT, ARTESP_REPORT),
        (NEW_PHOTO_REPORT, NEW_PHOTO_REPORT),
    ]

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    export_type = models.CharField(
        max_length=100,
        choices=PHOTO_REPORT_TYPES,
        default=NEW_PHOTO_REPORT,
    )

    is_inventory = models.BooleanField(default=False)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_photo_reports"
    )

    options = JSONField(default=dict)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="created_photo_reports",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    done = models.BooleanField(default=False)

    error = models.BooleanField(default=False)

    processing_finished_at = models.DateTimeField(null=True, blank=True)

    options_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )

    exported_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )

    def __str__(self):
        return "[{}] {}: {}".format(self.company.name, self.uuid, self.export_type)

    @property
    def get_company_id(self):
        return self.company_id
