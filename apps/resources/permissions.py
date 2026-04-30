import uuid

from rest_framework_json_api import serializers

from apps.companies.models import Company, Entity, Firm, SubCompany
from apps.resources.models import Contract, FieldSurvey
from apps.service_orders.models import MeasurementBulletin
from apps.service_orders.permissions import (
    ProcedureResourcePermissions,
    ServiceOrderResourcePermissions,
)
from helpers.permissions import BaseModelAccessPermissions, PermissionManager
from helpers.strings import get_obj_from_path


class ResourcePermissions(BaseModelAccessPermissions):
    model_name = "Resource"

    def has_object_permission(self, request, view, obj):

        if view.action in ["history"]:
            company = self.get_company_id("retrieve", request, obj)
            if not company:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company, model=self.model_name
                )

            return view.permissions.has_permission(permission="can_view")

        else:
            return super(ResourcePermissions, self).has_object_permission(
                request, view, obj
            )


class FirmChildPermissions(BaseModelAccessPermissions):
    def get_company_id(self, action, request, obj=None):
        if action in ["list", "retrieve"]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        elif action == "create":
            try:
                if "firm" in request.data:
                    firm = Firm.objects.get(pk=uuid.UUID(request.data["firm"]["id"]))
                    return firm.company_id
                elif "subcompany" in request.data:
                    subcompany = SubCompany.objects.get(
                        pk=uuid.UUID(request.data["subcompany"]["id"])
                    )
                    return subcompany.company_id
                else:
                    return False
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                if obj.get_company_id:
                    return obj.get_company_id
                else:
                    return False
            except Exception as e:
                print(e)
                return False

        else:
            return False


class ContractPermissions(FirmChildPermissions):

    model_name = "Contract"

    def has_object_permission(self, request, view, obj):
        if view.action in [
            "pdf_contract",
            "preview_download",
            "history_download",
            "extra_hours_download",
        ]:
            company = self.get_company_id("retrieve", request, obj)
            if not company:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company, model=self.model_name
                )

            return view.permissions.has_permission(permission="can_download")

        elif view.action == "bulk_approval":
            company = self.get_company_id("update", request, obj)
            if not company:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company, model=obj.__class__.__name__
                )

            return view.permissions.has_permission(permission="can_approve")

        else:
            return super(ContractPermissions, self).has_object_permission(
                request, view, obj
            )


class ContractServicePermissions(BaseModelAccessPermissions):
    model_name = "ContractService"

    def has_object_permission(self, request, view, obj):

        if view.action in ["resource_summary"]:
            company = self.get_company_id("retrieve", request, obj)
            if not company:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company, model=self.model_name
                )

            return view.permissions.has_permission(permission="can_view")

        else:
            return super(ContractServicePermissions, self).has_object_permission(
                request, view, obj
            )

    def has_permission(self, request, view):
        if view.action in ["contract_items_ordering"]:
            company = self.get_company_id("retrieve", request)
            if not company:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company, model=self.model_name
                )

            return view.permissions.has_permission(permission="can_edit")

        else:
            return super(ContractServicePermissions, self).has_permission(request, view)

    def get_company_id(self, action, request, obj=None):
        if action in [
            "list",
            "retrieve",
            "resource_summary",
            "contract_items_ordering",
        ]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        elif action == "create":
            try:
                firm_id = request.data["firms"][0]["id"]
                firm = Firm.objects.get(pk=uuid.UUID(firm_id))
                return firm.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.firms.first().company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class ContractItemUnitPricePermissions(BaseModelAccessPermissions):
    model_name = "ContractItemUnitPrice"

    def has_object_permission(self, request, view, obj):

        if view.action in ["history"]:
            company = self.get_company_id("retrieve", request, obj)
            if not company:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company, model=self.model_name
                )

            return view.permissions.has_permission(permission="can_view")

        else:
            return super(ContractItemUnitPricePermissions, self).has_object_permission(
                request, view, obj
            )

    def get_company_id(self, action, request, obj=None):
        if action in ["list", "retrieve"]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        elif action == "create":
            try:
                entity_id = request.data["entity"]["id"]
                entity = Entity.objects.get(pk=entity_id)
                return entity.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            if obj.entity:
                try:
                    return obj.entity.company_id
                except Exception as e:
                    print(e)
                    return False

            try:
                return obj.resource.contract.subcompany.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class ContractItemAdministrationPermissions(BaseModelAccessPermissions):
    model_name = "ContractItemAdministration"

    def get_company_id(self, action, request, obj=None):
        if action in ["list", "retrieve"]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        elif action == "create":
            try:
                entity_id = request.data["entity"]["id"]
                entity = Entity.objects.get(pk=entity_id)
                return entity.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            if obj.entity:
                try:
                    return obj.entity.company_id
                except Exception as e:
                    print(e)
                    return False

            try:
                return obj.resource.contract.subcompany.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class ContractItemPerformancePermissions(BaseModelAccessPermissions):
    model_name = "ContractItemPerformance"

    def get_company_id(self, action, request, obj=None):
        if action in ["list", "retrieve"]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        elif action == "create":
            try:
                entity_id = request.data["entity"]["id"]
                entity = Entity.objects.get(pk=entity_id)
                return entity.company_id
            except Exception:
                return False

        elif action in ["update", "partial_update", "destroy"]:
            if obj.entity:
                try:
                    return obj.entity.company_id
                except Exception:
                    return False

            try:
                return obj.resource.contract.subcompany.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class HumanResourcePermissions(FirmChildPermissions):
    model_name = "HumanResource"

    def has_object_permission(self, request, view, obj):
        if view.action == "summary":
            company = self.get_company_id("update", None, obj)

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company, model=self.model_name
                )

            return view.permissions.has_permission(permission="can_view")

        else:
            return super(HumanResourcePermissions, self).has_object_permission(
                request, view, obj
            )


class HumanResourceItemPermissions(ServiceOrderResourcePermissions):
    model_name = "HumanResourceItem"

    def get_company_id(self, action, request, obj=None):
        def verify_data(contract):
            if contract.firm:
                if contract.firm.company:
                    return contract.firm.company_id

            elif contract.subcompany:
                if contract.subcompany.company:
                    return contract.firm.company_id
            else:
                return False

        if action == "create":
            if "human_resource" not in request.data.keys():
                raise serializers.ValidationError(
                    "É necessário especificar o recurso humano."
                )
            contract = Contract.objects.get(
                pk=uuid.UUID(request.data["human_resource"]["id"])
            )
            return verify_data(contract)

        elif action in ["update", "partial_update", "destroy"]:
            return verify_data(contract)

        else:
            return super(HumanResourceItemPermissions, self).get_company_id(
                action, request, obj
            )


class HumanResourceUsagePermissions(ProcedureResourcePermissions):
    model_name = "HumanResourceUsage"


class MeasurementBulletinExportPermissions(BaseModelAccessPermissions):
    model_name = "MeasurementBulletinExport"

    def get_company_id(self, action, request, obj=None):
        if action in ["list", "retrieve"]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        elif action == "create":

            try:
                measurement_bulletins = get_obj_from_path(
                    request.data, "measurementBulletin"
                )
                measurement_bulletin_id = (
                    measurement_bulletins["id"] if measurement_bulletins else None
                )

                if measurement_bulletin_id:
                    bulletin = MeasurementBulletin.objects.get(
                        pk=measurement_bulletin_id
                    )
                else:
                    return False
                if bulletin.contract.firm:
                    return bulletin.contract.firm.company_id
                else:
                    return bulletin.contract.subcompany.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            if obj.measurement_bulletin.exists():
                if obj.measurement_bulletin.contract.firm:
                    return obj.measurement_bulletin.contract.firm.company_id
                else:
                    return obj.measurement_bulletin.contract.subcompany.company_id
            else:
                return False

        else:
            return False


class FieldSurveyRoadPermissions(BaseModelAccessPermissions):
    model_name = "FieldSurveyRoad"

    def get_company_id(self, action, request, obj=None):

        if action in ["list", "retrieve"]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        elif action == "create":
            try:
                contract_id = request.data["contract"]["id"]
                contract = Contract.objects.get(pk=contract_id)
                return contract.subcompany.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.contract.subcompany.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class FieldSurveyPermissions(BaseModelAccessPermissions):
    model_name = "FieldSurvey"

    def get_company_id(self, action, request, obj=None):

        if action in ["list", "retrieve"]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        elif action == "create":
            try:
                contract_id = request.data["contract"]["id"]
                contract = Contract.objects.get(pk=contract_id)
                return contract.subcompany.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy", "approval"]:
            try:
                return obj.contract.subcompany.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False

    def has_object_permission(self, request, view, obj):
        if view.action == "approval" and request.method == "POST":
            company_id = self.get_company_id(view.action, None, obj)
            try:
                _ = Company.objects.get(pk=company_id)
            except Exception:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company_id, model=self.model_name
                )

            is_contract_responsible = (
                request.user.uuid
                in obj.contract.responsibles_hirer.values_list("uuid", flat=True)
            )

            return (
                view.permissions.has_permission(permission="can_approve")
                and is_contract_responsible
            )

        elif view.action == "destroy":
            company_id = self.get_company_id(view.action, request, obj)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company_id, model=self.model_name
                )

            if view.permissions.has_permission(permission="can_delete"):
                if not (obj.approval_status == "APPROVED_APPROVAL"):
                    return True
                else:
                    raise serializers.ValidationError(
                        "Somente pode ser deletado se não for aprovado"
                    )

        else:
            return super(FieldSurveyPermissions, self).has_object_permission(
                request, view, obj
            )


class FieldSurveySignaturePermissions(BaseModelAccessPermissions):
    model_name = "FieldSurveySignature"
    not_allowed_actions = ("create", "destroy")

    def get_company_id(self, action, request, obj=None):
        if action in self.not_allowed_actions:
            return False

        elif action in ["list", "retrieve"]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.field_survey.contract.subcompany.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False

    def has_object_permission(self, request, view, obj):
        if view.action in ["update", "partial_update"]:
            if request.user not in (obj.hirer, obj.hired):
                return False

        return True


class FieldSurveyExportPermissions(BaseModelAccessPermissions):
    model_name = "FieldSurveyExport"

    def get_company_id(self, action, request, obj=None):
        if action in ["list", "retrieve"]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        elif action == "create":

            try:
                field_surveys = get_obj_from_path(request.data, "field_survey")
                field_survey_id = field_surveys["id"] if field_surveys else None

                if field_survey_id:
                    field_survey = FieldSurvey.objects.get(pk=field_survey_id)
                else:
                    return False
                if field_survey.contract.firm:
                    return field_survey.contract.firm.company_id
                else:
                    return field_survey.contract.subcompany.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            if obj.field_survey.exists():
                if field_survey.contract.firm:
                    return obj.field_survey.contract.firm.company_id
                else:
                    return obj.field_survey.contract.subcompany.company_id
            else:
                return False

        else:
            return False


class ContractAdditivePermissions(BaseModelAccessPermissions):
    model_name = "ContractAdditive"

    def has_permission(self, request, view):
        if request.method in ["HEAD", "OPTIONS"] or view.action in [
            "list",
            "retrieve",
            "create",
        ]:
            return super().has_permission(request, view)
        else:
            return False

    def has_object_permission(self, request, view, obj):
        if request.method in ["HEAD", "OPTIONS"] or view.action in [
            "retrieve",
        ]:
            return super().has_object_permission(request, view, obj)
        else:
            return False


class ContractPeriodPermissions(BaseModelAccessPermissions):
    model_name = "ContractPeriod"
