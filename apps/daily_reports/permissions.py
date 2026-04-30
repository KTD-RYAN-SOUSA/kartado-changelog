import uuid

from rest_framework.exceptions import ValidationError

from apps.companies.models import Firm
from apps.daily_reports.models import DailyReport, MultipleDailyReport
from apps.resources.models import Resource
from apps.service_orders.models import MeasurementBulletin
from apps.services.models import Service
from helpers.apps.json_logic import apply_json_logic
from helpers.permissions import BaseModelAccessPermissions, PermissionManager
from helpers.strings import get_obj_from_path


class DailyReportPermissions(BaseModelAccessPermissions):
    model_name = "DailyReport"

    def has_object_permission(self, request, view, obj):
        company_id = self.get_company_id(view.action, request, obj)
        if not company_id:
            return False

        if not view.permissions:
            view.permissions = PermissionManager(
                user=request.user, company_ids=company_id, model=self.model_name
            )

        if view.action in ["update", "partial_update"] and not obj.editable:
            return False

        if view.action == "approval":
            if not obj.approval_step:
                return False

            data = {
                "daily_report": obj.__dict__,
                "user": request.user.__dict__,
                "user_permission": view.permissions.all_permissions,
            }

            user_in_responsibles = apply_json_logic(
                obj.approval_step.responsible_json_logic, data
            )

            responsible = []
            if obj.approval_step.responsible_created_by:
                responsible.append(obj.created_by)

            for user in obj.approval_step.responsible_users.all():
                responsible.append(user)

            for firm in obj.approval_step.responsible_firms.all():
                if firm.manager:
                    responsible.append(firm.manager)
                for user in firm.users.all():
                    responsible.append(user)

            if (not user_in_responsibles) and (
                len(responsible) and request.user not in responsible
            ):
                return False

            return view.permissions.has_permission(permission="can_approve")

        return super().has_object_permission(request, view, obj)


class MultipleDailyReportPermissions(BaseModelAccessPermissions):
    model_name = "MultipleDailyReport"

    def get_company_id(self, action, request, obj=None):
        if action in [
            "list",
            "retrieve",
            "get_aggregate_resources",
            "history",
            "history_reportings",
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
                return uuid.UUID(request.data["company"]["id"])
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy", "approval"]:
            try:
                return obj.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False

    def get_company_id_from_objs(self, id_list: dict, request, model, view):
        """
        Gets the company from the request body. First filter the data based on objects_id AND user companies,
        then check if all objects have the same company. If all objects have the same company and also belongs to the user
        companies, that's user company.
        """

        try:
            obj_ids = [obj["id"] for obj in request.data[id_list]]
        except Exception as e:
            raise ValidationError("Requisicao mal formatada.") from e
        user_companies_ids = request.user.companies.all().values_list("uuid", flat=True)
        objs = model.objects.filter(pk__in=obj_ids, company_id__in=user_companies_ids)

        if not objs.exists():
            return False
        # ensure that all multiple daily reports have the same company
        first_obj = objs.first()
        if not all([first_obj.company_id == obj.company_id for obj in objs]):
            return False
        view.validated_objs = objs
        return objs.first().company_id

    def has_object_permission(self, request, view, obj):
        if request.method in ["HEAD", "OPTIONS"]:
            return True

        company_id = self.get_company_id(view.action, request, obj)
        if not company_id:
            return False

        if not view.permissions:
            view.permissions = PermissionManager(
                user=request.user, company_ids=company_id, model=self.model_name
            )

        if view.action in [
            "retrieve",
            "get_aggregate_resources",
            "history",
            "history_reportings",
        ]:
            return view.permissions.has_permission(permission="can_view")

        elif view.action == "destroy":
            return view.permissions.has_permission(permission="can_delete")

        elif view.action in ["update", "partial_update"]:
            if not obj.editable:
                raise ValidationError(
                    "kartado.error.multiple_daily_report.not_editable"
                )

            return view.permissions.has_permission(permission="can_edit")

        elif view.action == "approval":
            if not obj.approval_step:
                return False

            data = {
                "multiple_daily_report": obj.__dict__,
                "user": request.user.__dict__,
                "user_permission": view.permissions.all_permissions,
            }

            user_in_responsibles = apply_json_logic(
                obj.approval_step.responsible_json_logic, data
            )

            responsible = []
            if obj.approval_step.responsible_created_by:
                responsible.append(obj.created_by)

            for user in obj.approval_step.responsible_users.all():
                responsible.append(user)

            for firm in obj.approval_step.responsible_firms.all():
                if firm.manager:
                    responsible.append(firm.manager)
                for user in firm.users.all():
                    responsible.append(user)

            if (not user_in_responsibles) and (
                len(responsible) and request.user not in responsible
            ):
                return False

            return view.permissions.has_permission(permission="can_approve")

        else:
            return False

    def has_permission(self, request, view):
        if view.action == "bulk_approval":
            company_id = self.get_company_id_from_objs(
                "multiple_daily_reports", request, MultipleDailyReport, view
            )
            if not company_id:
                return False

            rdos = view.validated_objs.prefetch_related(
                "approval_step",
                "approval_step__responsible_users",
                "approval_step__responsible_firms",
                "approval_step__responsible_firms__users",
                "created_by",
            )

            if rdos.filter(approval_step__isnull=True).exists():
                raise ValidationError(
                    "Um ou mais RDO não pode ser aprovado. Contate nossa equipe."
                )

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company_id, model=self.model_name
                )

            for rdo in rdos:
                data = {
                    "multiple_daily_report": rdo.__dict__,
                    "user": request.user.__dict__,
                    "user_permission": view.permissions.all_permissions,
                }
                user_in_responsibles = apply_json_logic(
                    rdo.approval_step.responsible_json_logic, data
                )

                responsible = []
                if rdo.approval_step.responsible_created_by:
                    responsible.append(rdo.created_by)
                for user in rdo.approval_step.responsible_users.all():
                    responsible.append(user)
                for firm in rdo.approval_step.responsible_firms.all():
                    if firm.manager:
                        responsible.append(firm.manager)
                    for user in firm.users.all():
                        responsible.append(user)

                if (not user_in_responsibles) and (
                    len(responsible) and request.user not in responsible
                ):
                    raise ValidationError(
                        "Erro ao aprovar RDOs. Usuário não tem permissão para aprovar."
                    )

            return view.permissions.has_permission(permission="can_approve")

        if view.action == "bulk":
            company_id = self.get_company_id_from_objs(
                "multiple_daily_reports", request, MultipleDailyReport, view
            )
            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company_id, model=self.model_name
                )
            return view.permissions.has_permission(
                permission="can_delete"
            ) or view.permissions.has_permission(permission="can_delete_all")
        if view.action in [
            "spreadsheet_multiple_daily_report",
            "spreadsheet_daily_report_vehicle",
            "spreadsheet_daily_report_equipment",
            "spreadsheet_daily_report_worker",
            "spreadsheet_daily_report_occurrence",
            "spreadsheet_daily_report_resource",
            "spreadsheet_reporting_resource",
            "spreadsheet_reporting",
            "spreadsheet_reporting_relationship",
        ]:
            company_id = self.get_company_id("list", request)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company_id, model=self.model_name
                )
            return view.permissions.has_permission(permission="can_view")

        return super(MultipleDailyReportPermissions, self).has_permission(request, view)


class DailyReportWorkerPermissions(BaseModelAccessPermissions):
    model_name = "DailyReportWorker"

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
                    firm_id = uuid.UUID(request.data["firm"]["id"])
                    firm = Firm.objects.only("company_id").get(pk=firm_id)
                    return firm.company_id
                elif "company" in request.data:
                    company_id = uuid.UUID(request.data["company"]["id"])
                    return company_id
                else:
                    return False
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy", "approval"]:
            try:
                if obj.firm:
                    return obj.firm.company_id
                elif obj.company:
                    return obj.company_id
                else:
                    return False
            except Exception as e:
                print(e)
                return False

        else:
            return False

    def has_object_permission(self, request, view, obj):
        if view.action == "approval" and request.method == "POST":
            company_id = self.get_company_id(view.action, None, obj)

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company_id, model=self.model_name
                )

            return view.permissions.has_permission(permission="can_approve")
        else:
            return super().has_object_permission(request, view, obj)


class DailyReportRelationPermissions(BaseModelAccessPermissions):
    model_name = "DailyReportRelation"

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
                if "daily_report" in request.data:
                    report_id = uuid.UUID(request.data["daily_report"]["id"])
                    report = DailyReport.objects.get(pk=report_id)
                elif "multiple_daily_report" in request.data:
                    report_id = uuid.UUID(request.data["multiple_daily_report"]["id"])
                    report = MultipleDailyReport.objects.get(pk=report_id)
                else:
                    return False

                return report.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                if obj.daily_report:
                    return obj.daily_report.company_id
                elif obj.multiple_daily_report:
                    return obj.multiple_daily_report.company_id
                else:
                    return False
            except Exception as e:
                print(e)
                return False

        else:
            return False


class DailyReportExternalTeamPermissions(BaseModelAccessPermissions):
    model_name = "DailyReportExternalTeam"


class DailyReportEquipmentPermissions(BaseModelAccessPermissions):
    model_name = "DailyReportEquipment"

    def get_company_id(self, action, request, obj=None):
        if action == "approval":
            try:
                return obj.company_id
            except Exception:
                return False
        else:
            return super().get_company_id(action, request, obj)

    def has_object_permission(self, request, view, obj):
        if view.action == "approval" and request.method == "POST":
            company_id = self.get_company_id(view.action, None, obj)

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company_id, model=self.model_name
                )

            return view.permissions.has_permission(permission="can_approve")
        else:
            return super().has_object_permission(request, view, obj)


class DailyReportVehiclePermissions(BaseModelAccessPermissions):
    model_name = "DailyReportVehicle"

    def get_company_id(self, action, request, obj=None):
        if action == "approval":
            try:
                return obj.company_id
            except Exception:
                return False
        else:
            return super().get_company_id(action, request, obj)

    def has_object_permission(self, request, view, obj):
        if view.action == "approval" and request.method == "POST":
            company_id = self.get_company_id(view.action, None, obj)

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company_id, model=self.model_name
                )

            return view.permissions.has_permission(permission="can_approve")
        else:
            return super().has_object_permission(request, view, obj)


class DailyReportSignalingPermissions(BaseModelAccessPermissions):
    model_name = "DailyReportSignaling"


class DailyReportOccurrencePermissions(BaseModelAccessPermissions):
    model_name = "DailyReportOccurrence"

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
                firm_id = uuid.UUID(request.data["firm"]["id"])
                firm = Firm.objects.only("company_id").get(pk=firm_id)
                return firm.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.firm.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class DailyReportResourcePermissions(BaseModelAccessPermissions):
    model_name = "DailyReportResource"

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
                resource_id = uuid.UUID(request.data["resource"]["id"])
                resource = Resource.objects.only("company_id").get(pk=resource_id)
                return resource.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.resource.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class ProductionGoalPermissions(BaseModelAccessPermissions):
    model_name = "ProductionGoal"

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
                service_id = uuid.UUID(request.data["service"]["id"])
                service = Service.objects.get(pk=service_id)
                return service.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.service.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class DailyReportExportPermissions(BaseModelAccessPermissions):
    model_name = "DailyReportExport"

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
                daily_reports = get_obj_from_path(request.data, "dailyReports")
                daily_report_id = daily_reports[0]["id"] if daily_reports else None
                multiple_daily_reports = get_obj_from_path(
                    request.data, "multipleDailyReports"
                )
                multiple_daily_report_id = (
                    multiple_daily_reports[0]["id"] if multiple_daily_reports else None
                )
                measurement_bulletins = get_obj_from_path(
                    request.data, "measurementBulletins"
                )
                measurement_bulletin_id = (
                    measurement_bulletins[0]["id"] if measurement_bulletins else None
                )

                if daily_report_id:
                    report = DailyReport.objects.get(pk=daily_report_id)
                elif multiple_daily_report_id:
                    report = MultipleDailyReport.objects.get(
                        pk=multiple_daily_report_id
                    )
                elif measurement_bulletin_id:
                    report = MeasurementBulletin.objects.get(pk=measurement_bulletin_id)
                    return (
                        report.contract.firm.company_id
                        if report.contract.firm
                        else report.contract.subcompany.company_id
                    )
                else:
                    return False

                return report.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            if obj.daily_reports.exists():
                return obj.daily_reports.first().company_id
            elif obj.multiple_daily_reports.exists():
                return obj.multiple_daily_reports.first().company_id
            elif obj.measurement_bulletins.exists():
                return (
                    obj.contract.firm.company_id
                    if obj.contract.firm
                    else obj.contract.subcompany.company_id
                )
            else:
                return False

        else:
            return False


class DailyReportContractUsagePermissions(BaseModelAccessPermissions):
    model_name = "DailyReportContractUsage"

    def get_company_id(self, action, request, obj=None):
        if action in ["list", "retrieve"]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False
        else:
            return False


class MultipleDailyReportFilePermissions(BaseModelAccessPermissions):
    model_name = "MultipleDailyReportFile"

    def get_company_id(self, action, request, obj=None):

        if action == "create":
            try:
                return MultipleDailyReport.objects.get(
                    pk=request.data["multiple_daily_report"]["id"]
                ).company.uuid
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.multiple_daily_report.company_id
            except Exception as e:
                print(e)
                return False

        return super().get_company_id(action, request, obj)

    def has_object_permission(self, request, view, obj):
        if view.action == "check":
            view.action = "retrieve"
        return super().has_object_permission(request, view, obj)


class MultipleDailyReportSignaturePermissions(BaseModelAccessPermissions):
    model_name = "MultipleDailyReportSignature"

    def get_company_id(self, action, request, obj=None):

        if action == "create":
            try:
                return MultipleDailyReport.objects.get(
                    pk=request.data["multiple_daily_report"]["id"]
                ).company.uuid
            except Exception:
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.multiple_daily_report.company_id
            except Exception:
                return False

        return super().get_company_id(action, request, obj)

    def has_object_permission(self, request, view, obj):
        if view.action == "check":
            view.action = "retrieve"
        return super().has_object_permission(request, view, obj)
