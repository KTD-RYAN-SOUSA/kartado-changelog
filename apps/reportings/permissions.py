import uuid

from rest_framework.exceptions import ValidationError

from apps.approval_flows.models import ApprovalStep
from helpers.apps.json_logic import apply_json_logic
from helpers.permissions import BaseModelAccessPermissions, PermissionManager

from .models import RecordMenu, Reporting, ReportingFile, ReportingMessage


class ReportingPermissions(BaseModelAccessPermissions):
    model_name = "Reporting"

    def has_permission(self, request, view):
        if view.action == "approval_status":
            company_id = self.get_company_id("list", request)
            if not company_id:
                return False
            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )
            return view.permissions.has_permission(permission="can_view")

        if view.action in [
            "zip_pictures",
            "spreadsheet_reporting_list",
            "spreadsheet_resource_list",
            "csp_results",
            "csp_graph_results",
            "single_excel_photo_export",
            "elo_export",
            "excel_report_dnit",
        ]:
            company_id = self.get_company_id("list", request)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            if view.action == "spreadsheet_resource_list":
                return view.permissions.has_permission(
                    permission="can_create"
                ) and view.permissions.has_permission(permission="can_view_money")

            if view.action == "excel_report_dnit":
                return view.permissions.has_permission(permission="can_download")

            if view.action == "elo_export":
                return view.permissions.has_permission(
                    permission="can_download_elo_export"
                )

            return view.permissions.has_permission(permission="can_create")

        if view.action == "bulk":
            try:
                first_reporting = Reporting.objects.get(
                    pk=request.data["reportings"][0]["id"]
                )
            except Exception:
                raise ValidationError("É necessário especificar ao menos um Reporting")

            company_id = first_reporting.company_id

            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            if request.method == "POST":
                return view.permissions.has_permission(permission="can_create")

            elif request.method == "DELETE":
                return view.permissions.has_permission(permission="can_delete")

            else:
                return False

        if view.action == "bulk_approval":

            reportings = None
            if "reportings" not in request.data or len(request.data["reportings"]) == 0:
                try:
                    from apps.reportings.views import ReportingFilter

                    filters = request.data["filters"]
                    company_id = filters.get("company")
                    if not company_id:
                        return False
                    reportings = (
                        ReportingFilter(filters)
                        .qs.prefetch_related("approval_step", "created_by")
                        .distinct()
                    )
                except Exception:
                    raise ValidationError("Erro ao filtrar reportings")

                if len(reportings) == 0:
                    raise ValidationError(
                        "É necessário especificar ao menos um Reporting"
                    )

            else:
                try:
                    first_reporting = Reporting.objects.get(
                        pk=request.data["reportings"][0]["id"]
                    )
                except Exception:
                    raise ValidationError(
                        "É necessário especificar ao menos um Reporting"
                    )

                company_id = first_reporting.company_id
                if not company_id:
                    return False

                reporting_ids = [item["id"] for item in request.data["reportings"]]
                reportings = (
                    Reporting.objects.filter(pk__in=reporting_ids)
                    .prefetch_related("approval_step", "created_by")
                    .distinct()
                )

            if reportings.filter(approval_step__isnull=True).exists():
                raise ValidationError(
                    "Um ou mais apontamentos não pode ser aprovado. Contate nossa equipe."
                )

            reportings_get_created_by = reportings.filter(
                approval_step__responsible_created_by=True
            ).values_list("created_by", flat=True)

            created_by_set = set(reportings_get_created_by)
            created_by_count = len(created_by_set)

            approval_steps = (
                ApprovalStep.objects.filter(step_reportings__in=reportings)
                .prefetch_related(
                    "responsible_users",
                    "responsible_firms",
                    "responsible_firms__users",
                )
                .distinct()
            )

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            user_firms = request.user.user_firms.filter(company_id=company_id)

            for obj in approval_steps:
                data = {
                    "user": request.user.__dict__,
                    "user_permission": view.permissions.all_permissions,
                    "user_firms": user_firms.values(),
                }

                user_in_responsibles = apply_json_logic(
                    obj.responsible_json_logic, data
                )

                responsible = []
                for user in obj.responsible_users.all():
                    responsible.append(user)

                for firm in obj.responsible_firms.all():
                    if firm.manager:
                        responsible.append(firm.manager)
                    for user in firm.users.all():
                        responsible.append(user)

                if (not user_in_responsibles) and (
                    len(responsible) and request.user not in responsible
                ):
                    if (
                        obj.responsible_created_by
                        and request.user.uuid in created_by_set
                        and created_by_count == 1
                    ):
                        pass
                    else:
                        raise ValidationError(
                            "Erro ao aprovar apontamentos. Usuário não pode aprovar este estágio."
                        )

            return view.permissions.has_permission(permission="can_approve")

        if view.action == "create_jobs_from_inspections":
            company_id = self.get_company_id("list", request)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )
            can_create_job = view.permissions.get_specific_model_permision(
                "Job", "can_create"
            )
            can_create_reporting = view.permissions.has_permission(
                permission="can_create"
            )
            return can_create_job and can_create_reporting
        return super(ReportingPermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if view.action == "approval" and request.method == "POST":
            company_id = self.get_company_id("update", request, obj)
            if not company_id:
                return False

            if not obj.approval_step:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            data = {
                "reporting": obj.__dict__,
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

        if view.action in ["update", "partial_update"]:
            company_id = self.get_company_id(view.action, request, obj)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            if not obj.editable:
                raise ValidationError("kartado.error.reporting.not_editable")
            else:
                return view.permissions.has_permission(permission="can_edit")

        if view.action == "IsSharedWithAgency":
            view.action = "retrieve"

        return super(ReportingPermissions, self).has_object_permission(
            request, view, obj
        )


class InventoryPermissions(BaseModelAccessPermissions):
    model_name = "Inventory"


class ReportingChildPermissions(BaseModelAccessPermissions):
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
                reporting = Reporting.objects.get(
                    pk=uuid.UUID(request.data["reporting"]["id"])
                )
            except Reporting.DoesNotExist as e:
                print(e)
                raise ValidationError("kartado.error.reporting.not_found")
            except Exception as e:
                print(e)
                return False

            allow_edit = self.model_name == "ReportingMessage"

            if not reporting.editable and not allow_edit:
                raise ValidationError("kartado.error.reporting.not_editable")
            else:
                return reporting.company_id

        elif action in ["update", "partial_update", "destroy"]:
            try:
                company_id = obj.reporting.company_id
            except Exception as e:
                print(e)
                return False

            try:
                request_data = list(request.data.keys())
            except Exception:
                request_data = []

            allow_edit = (
                (self.model_name == "ReportingFile")
                and (
                    "include_dnit" in request_data
                    or "include_rdo" in request_data
                    or "is_shared" in request_data
                )
            ) or (self.model_name == "ReportingMessage")

            if not obj.reporting.editable and not allow_edit:
                raise ValidationError("kartado.error.reporting.not_editable")
            else:
                return company_id

        else:
            return False


class ReportingFilePermissions(ReportingChildPermissions):
    model_name = "ReportingFile"

    def has_permission(self, request, view):
        if view.action == "bulk":
            try:
                request_data = dict(request.data)
                first_rep_file_id = request_data["reporting_files"][0]["id"]
                first_reporting_file = ReportingFile.objects.get(pk=first_rep_file_id)
            except Exception:
                raise ValidationError(
                    "É necessário especificar ao menos um Reporting File"
                )

            company_id = first_reporting_file.reporting.company_id

            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            if request.method == "POST":
                return view.permissions.has_permission(permission="can_create")

            else:
                return False

        return super(ReportingFilePermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if view.action == "check":
            view.action = "retrieve"

        elif view.action == "redirect_to_s3":
            view.action = "retrieve"

        elif view.action == "IsSharedWithAgency":
            view.action = "retrieve"

        return super(ReportingFilePermissions, self).has_object_permission(
            request, view, obj
        )


class ReportingMessagePermissions(ReportingChildPermissions):
    model_name = "ReportingMessage"


class ReportingMessageReadReceiptPermissions(BaseModelAccessPermissions):
    model_name = "ReportingMessageReadReceipt"

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
                reporting_message = ReportingMessage.objects.get(
                    pk=uuid.UUID(request.data["reporting_message"]["id"])
                )
            except Exception as e:
                print(e)
                return False

            return reporting_message.reporting.company_id

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.reporting_message.reporting.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class RecordMenuPermissions(BaseModelAccessPermissions):
    model_name = "RecordMenu"

    def get_company_id(self, action, request, obj=None):
        if action == "move_down_menu" or action == "move_up_menu":
            try:
                return obj.company_id
            except Exception:
                return False

        return super().get_company_id(action, request, obj)

    def has_object_permission(self, request, view, obj):
        company_id = self.get_company_id(view.action, request, obj)
        if not company_id:
            return False

        if not view.permissions:
            view.permissions = PermissionManager(
                user=request.user, company_ids=company_id, model=self.model_name
            )

        if view.action == "destroy":
            if obj.system_default is True:
                raise ValidationError(
                    "kartado.error.record_menu.system_default_menu_cannot_be_deleted"
                )
            if obj.record_menu_reportings.exists():
                raise ValidationError(
                    "kartado.error.record_menu.menu_with_reportings_cannot_be_deleted"
                )

            if (
                RecordMenu.objects.filter(
                    company=obj.company, system_default=False
                ).count()
                == 1
            ):
                raise ValidationError(
                    "kartado.error.record_menu.there_is_only_one_menu"
                )
            return (
                obj.created_by == request.user
                and view.permissions.has_permission(permission="can_delete")
            ) or view.permissions.has_permission(permission="can_delete_all")

        if view.action == "update" or view.action == "partial_update":
            if obj.system_default is True:
                raise ValidationError(
                    "kartado.error.record_menu.system_default_menu_records_cannot_be_edited"
                )
            else:
                return (
                    view.permissions.has_permission(permission="can_edit")
                    or obj.created_by == request.user
                )

        if view.action in ["move_down_menu", "move_up_menu", "bulk_order"]:
            return view.permissions.has_permission(permission="can_edit")

        return super(RecordMenuPermissions, self).has_object_permission(
            request, view, obj
        )

    def has_permission(self, request, view):
        if view.action == "can_be_deleted":
            view.action = "retrieve"

        if view.action == "bulk_order":
            view.action = "create"

        return super().has_permission(request, view)


class ReportingRelationPermissions(BaseModelAccessPermissions):
    model_name = "ReportingRelation"


class ReportingInReportingPermissions(BaseModelAccessPermissions):
    model_name = "ReportingInReporting"

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

    def has_permission(self, request, view):
        if view.action in ["list", "retrieve"]:
            company_id = self.get_company_id(view.action, request)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            return view.permissions.has_permission(permission="can_view")
        else:
            return False

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

        if view.action == "retrieve":
            return view.permissions.has_permission(permission="can_view")
        else:
            return False
