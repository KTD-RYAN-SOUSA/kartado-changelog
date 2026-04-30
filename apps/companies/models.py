import uuid
from datetime import date

from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.db.models import JSONField, Q
from simple_history.models import HistoricalRecords

from apps.permissions.models import UserPermission
from apps.users.models import User
from helpers.strings import keys_to_snake_case
from helpers.validators.brazilian_documents import validate_CNPJ
from RoadLabsAPI.storage_backends import PrivateMediaStorage

from .const import app_types


class CompanyGroup(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    key_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_company_groups"
    )
    saml_idp = models.CharField(blank=True, null=True, max_length=255)
    metadata = JSONField(default=dict, blank=True, null=True)

    mobile_app = models.CharField(
        max_length=100,
        choices=app_types.APP_TYPE_CHOICES,
        default=app_types.UNDEFINED,
    )

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] {}".format(self.key_user.username, self.name)


class Company(models.Model):
    """
    Company models are the key of the software
    Each company englobes users, patologies, firms,
    equipments, materials, jobs, rdos, and others.
    It works like a center table that links almost everything
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=300, blank=False, default="")
    active = models.BooleanField(default=False)
    users = models.ManyToManyField(
        User, through="UserInCompany", related_name="companies"
    )
    owner = models.ForeignKey(
        User,
        related_name="companies_owned",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    cnpj = models.CharField(max_length=50, validators=[validate_CNPJ])
    logo = models.FileField(
        storage=PrivateMediaStorage(),
        upload_to="companies-logos/",
        blank=True,
        default=None,
        null=True,
    )
    provider_logo = models.FileField(
        storage=PrivateMediaStorage(),
        upload_to="companies-logos/",
        blank=True,
        default=None,
        null=True,
    )
    company_group = models.ForeignKey(
        CompanyGroup,
        related_name="group_companies",
        on_delete=models.SET_NULL,
        null=True,
    )
    street_address = models.CharField(max_length=300, blank=True, default="")
    custom_options = JSONField(default=dict, blank=True, null=True)
    metadata = JSONField(default=dict, blank=True, null=True)

    shape = models.MultiPolygonField(null=True, blank=True)

    key_users = models.ManyToManyField(
        User, related_name="key_users_company", blank=True
    )

    mobile_app_override = models.CharField(
        max_length=100,
        choices=app_types.APP_TYPE_CHOICES,
        null=True,
        blank=True,
    )

    history = HistoricalRecords()

    def get_process_type_option(self, process_type):
        try:
            custom_options = keys_to_snake_case(self.custom_options)
            custom_service_order = keys_to_snake_case(
                custom_options["service_order"]["fields"]
            )
            custom_process_type = keys_to_snake_case(
                custom_service_order["process_type"]
            )
            options = custom_process_type["select_options"]["options"]
            for option in options:
                if option["value"] == process_type:
                    return option
        except Exception:
            pass

    def get_judiciary_users(self):
        try:
            return User.objects.filter(
                user_firms__company=self, user_firms__is_judiciary=True
            )
        except Exception:
            pass

    class Meta:
        verbose_name_plural = "Companies"

    def __str__(self):
        return "{}: {}".format(self.uuid, self.name)

    @property
    def get_company_id(self):
        return self.uuid

    def get_active_users_id(self):
        return (
            self.userincompany_set.filter(
                # The User is active
                Q(is_active=True)
                # And not expired (if there's such date)
                & (
                    Q(expiration_date__isnull=True)
                    | Q(expiration_date__gt=date.today())
                )
            )
            .values_list("user", flat=True)
            .distinct()
        )


class SubCompany(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subcompany_type = models.CharField(
        max_length=6, choices=[("HIRING", "HIRING"), ("HIRED", "HIRED")]
    )
    company = models.ForeignKey(
        Company, related_name="company_subcompanies", on_delete=models.CASCADE
    )

    name = models.CharField(max_length=300, blank=False, default="")
    cnpj = models.CharField(max_length=50, validators=[validate_CNPJ])
    responsible = models.ForeignKey(
        User,
        related_name="user_responsible_subcompanies",
        on_delete=models.SET_NULL,
        blank=False,
        default=None,
        null=True,
    )

    contract = models.CharField(max_length=300, blank=True, default="")
    contract_start_date = models.DateField(blank=True, null=True, default=None)
    contract_end_date = models.DateField(blank=True, null=True, default=None)

    office = models.TextField(blank=True)
    construction_name = models.TextField(blank=True)

    logo = models.FileField(
        storage=PrivateMediaStorage(),
        upload_to="subcompanies-logos/",
        blank=True,
        default=None,
        null=True,
    )

    # Hired subcompany
    hired_by_subcompany = models.ForeignKey(
        "self",
        related_name="subcompany_hired_subcompanies",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    active = models.BooleanField(default=True)
    legacy_uuid = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "Sub companies"

    def __str__(self):
        return "[{}] {}: {}".format(self.company, self.uuid, self.name)

    @property
    def get_company_id(self):
        return self.company_id


class UserInCompany(models.Model):
    """
    Users Companies are used to link users to companies
    This model also allows us to add users levels and expirations dates
    With that we control user accesses and restrictions
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="companies_membership"
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    expiration_date = models.DateField(blank=True, null=True, default=None)
    level = models.IntegerField(default=2)  # TODO: Use enum here
    permissions = models.ForeignKey(
        UserPermission,
        null=True,
        on_delete=models.SET_NULL,
        related_name="permission_memberships",
    )
    added_permissions = ArrayField(models.UUIDField(), blank=True, null=True)
    is_active = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["company"]
        verbose_name_plural = "Users in companies"
        unique_together = ["user", "company"]

    def __str__(self):
        return "[{}] {}".format(self.company, self.user.username)

    @property
    def get_company_id(self):
        return self.company_id


class Firm(models.Model):
    """
    Firms are third-party companies that work to execute the jobs
    They can be either internal to the company or external (contractors, etc)
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=300, blank=False, default="")
    manager = models.ForeignKey(
        User,
        related_name="user_firms_manager",
        on_delete=models.SET_NULL,
        blank=False,
        default=None,
        null=True,
    )
    users = models.ManyToManyField(
        User, through="UserInFirm", related_name="user_firms"
    )
    inspectors = models.ManyToManyField(
        User,
        through="InspectorInFirm",
        related_name="inspector_firms",
        blank=True,
    )
    company = models.ForeignKey(
        Company,
        related_name="company_firms",
        on_delete=models.CASCADE,
        default=None,
        null=True,
    )
    subcompany = models.ForeignKey(
        SubCompany,
        related_name="subcompany_firms",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    entity = models.ForeignKey(
        "companies.Entity",
        related_name="firms",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
        blank=True,
    )
    cnpj = models.CharField(max_length=50, blank=True, validators=[validate_CNPJ])
    is_company_team = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    logo = models.FileField(
        storage=PrivateMediaStorage(),
        upload_to="companies-logos/",
        blank=True,
        default=None,
        null=True,
    )
    custom_options = JSONField(default=dict, blank=True, null=True)
    metadata = JSONField(default=dict, blank=True, null=True)
    members_amount = models.IntegerField(default=0, blank=True, null=True)
    street_address = models.CharField(max_length=300, blank=True, default="")
    city = models.ForeignKey(
        "locations.City",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
        blank=True,
    )
    can_use_ecm_integration = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_created_firms",
    )

    is_judiciary = models.BooleanField(default=False)

    delete_in_progress = models.BooleanField(default=False)
    legacy_uuid = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    history = HistoricalRecords()

    class Meta:
        unique_together = ("company", "name")
        ordering = ["company"]

    def __str__(self):
        return "[{}] {}: {}".format(self.company, self.uuid, self.name)

    def save(self, *args, **kwargs):
        # If CNPJ is blank and team is internal, fill it with the parent company's CNPJ
        if self.is_company_team and not self.cnpj:
            self.cnpj = self.company.cnpj

        super(Firm, self).save(*args, **kwargs)

    @property
    def get_company_id(self):
        return self.company_id


class UserInFirm(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_userinfirm"
    )
    firm = models.ForeignKey(
        Firm, on_delete=models.CASCADE, related_name="firm_userinfirm"
    )

    history = HistoricalRecords()

    class Meta:
        unique_together = ["user", "firm"]

    def __str__(self):
        return "[{}] {}".format(self.firm.name, self.user.username)

    @property
    def get_company_id(self):
        return self.firm.company_id


class InspectorInFirm(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_inspectorinfirm"
    )
    firm = models.ForeignKey(
        Firm, on_delete=models.CASCADE, related_name="firm_inspectorinfirm"
    )

    history = HistoricalRecords()

    class Meta:
        unique_together = ["user", "firm"]

    def __str__(self):
        return "[{}] {}".format(self.firm.name, self.user.username)

    @property
    def get_company_id(self):
        return self.firm.company_id


class AccessRequest(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_requests"
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    companies = models.ManyToManyField(Company, related_name="access_requests")

    expiration_date = models.DateField(blank=True, null=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True)
    approved = models.BooleanField(default=False)
    done = models.BooleanField(default=False)

    permissions = models.ForeignKey(
        UserPermission,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="permission_requests",
    )

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    approval_step = models.ForeignKey(
        "approval_flows.ApprovalStep",
        on_delete=models.SET_NULL,
        related_name="step_requests",
        null=True,
        blank=True,
    )

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] {}".format(self.company.name, self.user.username)

    @property
    def get_company_id(self):
        return self.company_id


class Entity(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.TextField(blank=True)
    approver_firm = models.ForeignKey(
        Firm,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approver_entities",
    )
    address = models.TextField(blank=True)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] {}".format(self.company.name if self.company else "", self.name)


class CompanyUsage(models.Model):
    """Tracks the usage of a plan for that Company at that date"""

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateField()
    plan_name = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    companies = models.ManyToManyField(Company, related_name="company_usages")
    users = models.ManyToManyField(
        User, through="UserUsage", related_name="user_company_usages", blank=True
    )

    # Auto fields (not manually set)
    cnpj = models.TextField(blank=True)
    company_names = JSONField(default=list, blank=True)
    user_count = models.PositiveIntegerField(default=0)

    history = HistoricalRecords()

    def __str__(self) -> str:
        month = self.date.strftime("%B")
        cnpj = self.cnpj

        return f"[{cnpj}] {month}"

    @property
    def company_id(self):
        return self.companies.first().uuid

    class Meta:
        verbose_name = "Company Usage"
        verbose_name_plural = "Company Usages"
        ordering = ["-date"]
        get_latest_by = ["date"]


class SingleCompanyUsage(models.Model):
    """Tracks the usage count for a single Company within a CompanyUsage period."""

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_usage = models.ForeignKey(
        CompanyUsage, on_delete=models.CASCADE, related_name="single_company_usages"
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="single_company_usages"
    )
    user_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    def __str__(self):
        return f"[{self.company_usage.cnpj}] {self.company.name}"

    class Meta:
        unique_together = ("company_usage", "company")
        ordering = ["-user_count"]
        verbose_name = "Single Company Usage"
        verbose_name_plural = "Single Company Usages"


class UserUsage(models.Model):
    """Tracks the usage of a plan by a particular user of a company"""

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_usages")
    company_usage = models.ForeignKey(
        CompanyUsage, on_delete=models.CASCADE, related_name="user_usages"
    )

    is_counted = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Auto fields (not manually set)
    full_name = models.TextField(blank=True)
    email = models.TextField(blank=True)
    username = models.TextField(blank=True)
    companies = JSONField(default=list, blank=True)
    usage_date = models.DateField(blank=True, null=True)

    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        # Autofill fields
        self.full_name = self.user.get_full_name()
        self.email = self.user.email
        self.username = self.user.username
        self.usage_date = self.company_usage.date

        super(UserUsage, self).save(*args, **kwargs)

    def __str__(self):
        month = self.company_usage.date.strftime("%B")
        cnpj = self.company_usage.cnpj

        return f"[{cnpj}] {month} - {self.user.username}"

    @property
    def company_id(self):
        return self.company_usage.company_id

    class Meta:
        verbose_name = "User Usage"
        verbose_name_plural = "User Usages"
        unique_together = ("user", "company_usage")
        ordering = ["-company_usage__date"]
        get_latest_by = ["company_usage__date"]
