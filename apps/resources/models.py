import datetime
import uuid

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import JSONField
from django.utils import timezone
from rest_framework_json_api import serializers
from simple_history.models import HistoricalRecords

from apps.companies.models import Company, Entity, Firm, SubCompany
from apps.resources.const import field_survey_approval_status
from apps.resources.manager import (
    ContractItemAdministrationManager,
    ContractItemUnitPriceManager,
    ContractManager,
)
from apps.users.models import User
from helpers.middlewares import get_current_user
from RoadLabsAPI.storage_backends import PrivateMediaStorage

from ..service_orders.const import resource_approval_status


class Resource(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.TextField()
    total_amount = models.FloatField(default=0)
    unit = models.CharField(max_length=50, blank=True)
    is_extra = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_created_resources",
    )

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - {}: {} {}".format(
            self.company.name, self.name, self.total_amount, self.unit
        )

    @property
    def get_company_id(self):
        return self.company_id


class Contract(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    performance_months = models.IntegerField(null=True, blank=True, default=0)
    name = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    contract_start = models.DateField(null=True, blank=True)
    contract_end = models.DateField(null=True, blank=True)
    survey_default = JSONField(default=dict)
    has_survey_default = models.BooleanField(default=False)
    lower_grade = models.IntegerField(null=True, default=0)
    higher_grade = models.IntegerField(null=True, default=10)
    default_grade = models.IntegerField(null=True, default=10)
    total_price = models.FloatField(null=True, blank=True, default=0)
    spent_price = models.FloatField(null=True, blank=True, default=0)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_contracts",
    )
    responsibles_hirer = models.ManyToManyField(User, related_name="hirer_contracts")
    responsibles_hired = models.ManyToManyField(User, related_name="hired_contracts")
    firm = models.ForeignKey(
        Firm,
        related_name="firm_contracts",
        on_delete=models.SET_NULL,
        null=True,
    )
    subcompany = models.ForeignKey(
        SubCompany,
        on_delete=models.SET_NULL,
        null=True,
        related_name="subcompany_contracts",
    )
    status = models.ForeignKey(
        "service_orders.ServiceOrderActionStatus",
        related_name="status_contracts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    roads = models.ManyToManyField(
        "roads.Road",
        through="resources.FieldSurveyRoad",
        related_name="survey_road_contracts",
    )

    survey_responsibles_hirer = models.ManyToManyField(
        User, related_name="survey_responsibles_hirer_contracts"
    )
    survey_responsibles_hired = models.ManyToManyField(
        User, related_name="survey_responsibles_hired_contracts"
    )

    extra_info = JSONField(default=dict, blank=True)
    spend_schedule = JSONField(default=dict, blank=True, null=True)

    service_orders = models.ManyToManyField(
        "service_orders.ServiceOrder",
        through="service_orders.AdministrativeInformation",
        related_name="contracts",
    )

    # Services
    unit_price_services = models.ManyToManyField(
        "resources.ContractService", related_name="unit_price_service_contracts"
    )
    administration_services = models.ManyToManyField(
        "resources.ContractService",
        related_name="administration_service_contracts",
    )
    performance_services = models.ManyToManyField(
        "resources.ContractService",
        related_name="performance_service_contracts",
    )

    objects = ContractManager()
    history = HistoricalRecords(m2m_fields=["responsibles_hirer", "responsibles_hired"])

    def __str__(self):
        company_name = self.firm.company.name if self.firm else ""
        return "[{}] {}: {} ({} - {})".format(
            company_name,
            self.uuid,
            self.name,
            self.contract_start,
            self.contract_end,
        )

    @property
    def get_company_id(self):
        if self.firm:
            return self.firm.company_id
        else:
            return self.subcompany.company_id


class ContractService(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    weight = models.FloatField(null=True, default=0, blank=True)
    price = models.FloatField(null=True, blank=True, default=0)
    description = models.TextField()
    firms = models.ManyToManyField(Firm, related_name="firm_contract_services")
    created_at = models.DateTimeField(auto_now_add=True)

    contract_item_unit_prices = models.ManyToManyField(
        "resources.ContractItemUnitPrice",
        related_name="contract_item_unit_price_services",
        blank=True,
    )
    contract_item_administration = models.ManyToManyField(
        "resources.ContractItemAdministration",
        related_name="contract_item_administration_services",
        blank=True,
    )
    contract_item_performance = models.ManyToManyField(
        "resources.ContractItemPerformance",
        related_name="contract_item_performance_services",
        blank=True,
    )

    history = HistoricalRecords(m2m_fields=["firms"])

    def __str__(self):
        try:
            company_name = self.firms.first().company.name
        except Exception:
            company_name = ""
        return "[{}] {}: {}".format(company_name, self.uuid, self.description)

    @property
    def get_company_id(self):
        return self.firms.first().company_id


class ContractItemUnitPrice(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    sort_string = models.TextField()
    entity = models.ForeignKey(
        Entity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entity_contract_unit_price_items",
    )
    resource = models.ForeignKey(
        "service_orders.ServiceOrderResource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resource_contract_unit_price_items",
    )
    order = models.IntegerField(null=True, blank=True)
    was_from_import = models.BooleanField(default=False)

    # TODO: Controle adicional

    objects = ContractItemUnitPriceManager()
    history = HistoricalRecords()

    def __str__(self):
        try:
            company_name = self.entity.company.name
        except Exception:
            company_name = ""
        return "[{}] {}: {} {}".format(
            company_name,
            self.uuid,
            self.sort_string,
            self.resource.resource.name,
        )

    @property
    def get_company_id(self):
        return self.entity.company_id


class ContractItemAdministration(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    sort_string = models.TextField()
    entity = models.ForeignKey(
        Entity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entity_contract_administration_items",
    )
    resource = models.ForeignKey(
        "service_orders.ServiceOrderResource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resource_contract_administration_items",
    )

    limit = (
        models.Q(app_label="daily_reports", model="dailyreportworker")
        | models.Q(app_label="daily_reports", model="dailyreportvehicle")
        | models.Q(app_label="daily_reports", model="dailyreportequipment")
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        limit_choices_to=limit,
    )

    order = models.IntegerField(null=True, blank=True)
    was_from_import = models.BooleanField(default=False)

    objects = ContractItemAdministrationManager()
    history = HistoricalRecords()

    def __str__(self):
        try:
            company_name = self.entity.company.name
        except Exception:
            company_name = ""
        return "[{}] {}: {} {}".format(
            company_name,
            self.uuid,
            self.sort_string,
            self.resource.resource.name,
        )

    @property
    def get_company_id(self):
        return self.entity.company_id


class ContractItemPerformance(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    weight = models.FloatField(null=True, default=0, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sort_string = models.TextField()
    entity = models.ForeignKey(
        Entity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entity_contract_performance_items",
    )
    resource = models.ForeignKey(
        "service_orders.ServiceOrderResource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resource_contract_performance_items",
    )

    order = models.IntegerField(null=True, blank=True)

    # TODO: Controle

    history = HistoricalRecords()

    def __str__(self):
        try:
            company_name = self.entity.company.name
        except Exception:
            company_name = ""
        return "[{}] {}: {} {}".format(
            company_name,
            self.uuid,
            self.sort_string,
            self.resource.resource.name,
        )

    @property
    def get_company_id(self):
        return self.entity.company_id


class FieldSurveyRoad(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    start_km = models.FloatField(null=False)
    end_km = models.FloatField(null=False)

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="surveys_roads",
        null=True,
    )
    road = models.ForeignKey(
        "roads.Road", on_delete=models.CASCADE, related_name="survey_roads"
    )

    history = HistoricalRecords()

    def __str__(self):
        try:
            company_name = self.contract.subcompany.company.name
        except Exception:
            company_name = ""
        return "[{}] {}".format(company_name, self.uuid)

    @property
    def get_company_id(self):
        return self.contract.subcompany.company.pk


class MeasurementBulletinExport(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="user_measurement_bulletin_exports",
        null=True,
        blank=True,
    )

    measurement_bulletin = models.ForeignKey(
        "service_orders.MeasurementBulletin",
        related_name="measurement_bulletin_exports",
        blank=True,
        on_delete=models.CASCADE,
    )

    exported_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )

    done = models.BooleanField(default=False)
    error = models.BooleanField(default=False)

    def __str__(self):
        contract = self.measurement_bulletin.contract
        if contract.firm:
            return "[{}] {}".format(contract.firm.company.name, self.uuid)
        else:
            return "[{}] {}".format(contract.subcompany.company.name, self.uuid)

    @property
    def get_company_id(self):
        contract = self.measurement_bulletin.contract

        if contract.firm:
            return contract.firm.company_id
        else:
            return contract.subcompany.company_id


class FieldSurvey(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateField(default=datetime.date.today)
    grades = JSONField(default=dict)
    name = models.TextField(blank=True, null=True)
    number = models.CharField(max_length=100, blank=True, null=True)
    approval_status = models.CharField(
        max_length=100,
        choices=resource_approval_status.APPROVAL_STATUS_CHOICES,
        default=resource_approval_status.WAITING_APPROVAL,
    )
    approval_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(
        max_length=100,
        choices=field_survey_approval_status.APPROVAL_STATUS_CHOICES,
        default=field_survey_approval_status.SURVEY_IN_PROGRESS,
        blank=True,
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="field_survey_approver",
        null=True,
        blank=True,
    )
    measurement_bulletin = models.ForeignKey(
        "service_orders.MeasurementBulletin",
        on_delete=models.SET_NULL,
        related_name="bulletin_surveys",
        blank=True,
        null=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_created_surveys",
    )
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="contract_surveys",
        null=True,
    )
    responsibles_hirer = models.ManyToManyField(
        User,
        related_name="hirer_surveys",
        blank=True,
        through="resources.FieldSurveySignature",
        through_fields=("field_survey", "hirer"),
    )
    responsibles_hired = models.ManyToManyField(
        User,
        related_name="hired_surveys",
        blank=True,
        through="resources.FieldSurveySignature",
        through_fields=("field_survey", "hired"),
    )
    added_to_measurement_bulletin_by = models.ForeignKey(
        User,
        null=True,
        related_name="modificated_field_survyes",
        on_delete=models.CASCADE,
    )
    manual = models.BooleanField(default=False, blank=True)
    final_grade = models.IntegerField(blank=True, null=False, default=0)

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        try:
            return self.contract.subcompany.company_id
        except Exception:
            return False

    @property
    def company(self):
        try:
            return self.contract.subcompany.company
        except Exception:
            return False

    def save(self, *args, **kwargs):
        incoming_fields = (
            self.created_by_id,
            self.responsibles_hirer,
            self.responsibles_hired,
            self.contract_id,
            self.grades,
            self.name,
            self.number,
            self.status,
        )

        # if the item is approved, all fields listed in orignal_fields cannot be changed anymore
        if self.original_status == "SURVEY_APPROVED":
            if self.original_fields != incoming_fields:
                raise serializers.ValidationError(
                    "Não é possível modificar um item aprovado."
                )
        if self.approval_status != "WAITING_APPROVAL":
            has_not_all_signatures = self.signatures.filter(
                signed_at__isnull=True
            ).exists()
            if has_not_all_signatures:
                raise serializers.ValidationError(
                    "Apenas um item com todas as assinaturas pode ser aprovado ou reprovado"
                )
            if self.approval_status != self.original_approval_status:
                self.approved_by = get_current_user()
                self.approval_date = timezone.now()
        if self.approval_status != "APPROVED_APPROVAL" and self.measurement_bulletin:
            raise serializers.ValidationError(
                "Apenas itens aprovados podem ser adicionados a um boletim de medição"
            )

        if self.approval_status != self.original_approval_status:
            self.approval_date = timezone.now()

        if self.measurement_bulletin:
            self.added_to_measurement_bulletin_by = get_current_user()

        else:
            self.added_to_measurement_bulletin_by = None
        super(FieldSurvey, self).save(*args, **kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # fields that cannot be changed if status == "SURVEY_APPROVED"
        self.original_fields = (
            self.created_by_id,
            self.responsibles_hirer,
            self.responsibles_hired,
            self.contract_id,
            self.grades,
            self.name,
            self.number,
            self.status,
        )
        self.original_status = self.status
        self.original_approval_status = self.approval_status
        self.request_user = None


class FieldSurveySignature(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    signed_at = models.DateTimeField(null=True, blank=True)
    hirer = models.ForeignKey(
        User,
        related_name="hirer_signature",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    hired = models.ForeignKey(
        User,
        related_name="hired_signature",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    field_survey = models.ForeignKey(
        FieldSurvey,
        related_name="signatures",
        on_delete=models.CASCADE,
        blank=True,
    )


class FieldSurveyExport(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="user_field_survey_exports",
        null=True,
        blank=True,
    )

    field_survey = models.ForeignKey(
        FieldSurvey,
        related_name="field_survey_exports",
        blank=True,
        on_delete=models.CASCADE,
    )

    exported_file = models.FileField(
        storage=PrivateMediaStorage(), blank=True, default=None, null=True
    )

    done = models.BooleanField(default=False)
    error = models.BooleanField(default=False)

    def __str__(self):
        contract = self.field_survey.contract

        if contract.firm:
            return "[{}] {}".format(contract.firm.company.name, self.uuid)
        else:
            return "[{}] {}".format(contract.subcompany.company.name, self.uuid)

    @property
    def get_company_id(self):
        contract = self.field_survey.contract

        if contract.firm:
            return contract.firm.company_id
        else:
            return contract.subcompany.company_id


class ContractServiceBulletin(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_uuid = models.UUIDField(editable=False, db_index=True)
    weight = models.FloatField(null=True, default=0, blank=True)
    price = models.FloatField(null=True, blank=True, default=0)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    contract = models.ForeignKey(
        "resources.Contract",
        on_delete=models.CASCADE,
        related_name="contract_services_bulletins",
    )

    contract_item_performance = models.ManyToManyField(
        "resources.ContractItemPerformanceBulletin",
        blank=True,
        related_name="contract_item_performance_bulletin_services",
    )

    measurement_bulletins = models.ManyToManyField(
        "service_orders.MeasurementBulletin",
        blank=True,
        related_name="measurement_bulletin_contract_services_bulletins",
    )

    history = HistoricalRecords()

    def __str__(self):
        contract = self.contract
        if contract.firm:
            company_name = contract.firm.company_id
        else:
            company_name = contract.subcompany.company_id
        return "[{}] {}: {}".format(company_name, self.uuid, self.description)

    @property
    def get_company_id(self):
        contract = self.contract
        if contract.firm:
            return contract.firm.company_id
        else:
            return contract.subcompany.company_id


class ContractItemPerformanceBulletin(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_uuid = models.UUIDField(editable=False, db_index=True)
    weight = models.FloatField(null=True, default=0, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sort_string = models.TextField()

    resource = models.ForeignKey(
        "service_orders.ServiceOrderResource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resource_contract_items_performance_bulletin",
    )

    measurement_bulletins = models.ManyToManyField(
        "service_orders.MeasurementBulletin",
        blank=True,
        related_name="measurement_bulletin_contract_items_performance_bulletin",
    )

    history = HistoricalRecords()

    def __str__(self):
        return "{}: {}".format(
            self.uuid,
            self.resource.resource.name,
        )

    @property
    def get_company_id(self):
        return self.resource.resource.company_id


class ContractAdditive(models.Model):

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    number = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    notes = models.TextField(blank=True)

    additional_percentage = models.FloatField(default=0)
    old_price = models.FloatField(default=0)
    new_price = models.FloatField(default=0)

    done = models.BooleanField(default=False)
    error = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_additives"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_additives",
    )
    contract = models.ForeignKey(
        Contract, on_delete=models.CASCADE, related_name="contract_additives"
    )

    @property
    def get_company_id(self):
        return self.company_id

    def __str__(self):
        return "[{}] - [{}]: {}".format(
            self.company.name, self.contract.name, self.number
        )


class ContractPeriod(models.Model):

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_contract_periods",
    )
    contract = models.ForeignKey(
        Contract, on_delete=models.CASCADE, related_name="contract_periods"
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_contract_periods"
    )
    firms = models.ManyToManyField(Firm, related_name="firm_contract_periods")

    hours = models.FloatField(default=0)
    working_schedules = JSONField(default=list)

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.company_id

    def __str__(self):
        return "[{}] - [{}]: {}h".format(
            self.company.name, self.contract.name, self.hours
        )
