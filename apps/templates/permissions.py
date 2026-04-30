import uuid

from django.db.models import Q

from apps.companies.models import Company
from apps.service_orders.models import ServiceOrder
from apps.templates.models import CanvasList, ExcelImport
from helpers.permissions import BaseModelAccessPermissions, PermissionManager
from helpers.strings import is_valid_uuid


class TemplatePermissions(BaseModelAccessPermissions):
    model_name = "Template"

    def has_permission(self, request, view):
        if view.action == "create" and request.method == "POST" and request.data:
            if "companies" not in request.data:
                return False

            company_ids = []
            for company in request.data["companies"]:
                company = company.get("id", False)
                if not company or not is_valid_uuid(company):
                    return False
                else:
                    company_ids.append(company)

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_ids,
                    model=self.model_name,
                )

            return view.permissions.has_permission(permission="can_create")

        else:
            return super(TemplatePermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if request.method in ["HEAD", "OPTIONS"]:
            return any(i in obj.companies.all() for i in request.user.companies.all())

        if not view.permissions:
            view.permissions = PermissionManager(
                user=request.user,
                company_ids=obj.companies.all(),
                model=self.model_name,
            )

        if view.action == "destroy":
            return view.permissions.has_permission(permission="can_delete")

        elif view.action == "retrieve":
            return view.permissions.has_permission(permission="can_view")

        elif view.action in ["update", "partial_update"]:
            return view.permissions.has_permission(permission="can_edit")

        else:
            return False


class CanvasListPermissions(BaseModelAccessPermissions):
    model_name = "CanvasList"

    def get_company_id(self, action, request, obj=None):
        if action == "create":
            try:
                service_order = ServiceOrder.objects.get(
                    pk=uuid.UUID(request.data["service_order"]["id"])
                )
            except Exception as e:
                print(e)
                return False

            return service_order.company_id

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.service_order.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return super(CanvasListPermissions, self).get_company_id(
                action, request, obj
            )


class CanvasCardPermissions(BaseModelAccessPermissions):
    model_name = "CanvasCard"

    def get_company_id(self, action, request, obj=None):
        if action == "create":
            try:
                canvas_list = CanvasList.objects.get(
                    pk=uuid.UUID(request.data["canvas_list"]["id"])
                )
            except Exception as e:
                print(e)
                return False

            return canvas_list.service_order.company_id

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.canvas_list.service_order.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return super(CanvasCardPermissions, self).get_company_id(
                action, request, obj
            )


class ExportRequestPermissions(BaseModelAccessPermissions):
    model_name = "ExportRequest"


class MobileSyncPermissions(BaseModelAccessPermissions):
    model_name = "MobileSync"


class ActionLogPermissions(BaseModelAccessPermissions):
    model_name = "ActionLog"

    def has_object_permission(self, request, view, obj):
        if request.method in ["HEAD", "OPTIONS"]:
            return True

        companies = Company.objects.filter(
            Q(company_logs=obj) | Q(company_group__company_group_logs=obj)
        ).distinct()

        if not view.permissions:
            view.permissions = PermissionManager(
                user=request.user, company_ids=companies, model=self.model_name
            )

        if view.action == "destroy":
            return view.permissions.has_permission(permission="can_delete")

        elif view.action == "retrieve":
            return view.permissions.has_permission(permission="can_view")

        elif view.action in ["update", "partial_update"]:
            return view.permissions.has_permission(permission="can_edit")

        else:
            return False


class SearchTagPermissions(BaseModelAccessPermissions):
    model_name = "SearchTag"

    def has_permission(self, request, view):
        if view.action == "get_search_tag_tree":
            view.action = "list"

        return super(SearchTagPermissions, self).has_permission(request, view)


class ExcelImportPermissions(BaseModelAccessPermissions):
    model_name = "ExcelImport"

    def has_object_permission(self, request, view, obj):
        if view.action in [
            "upload_zip_images",
            "generate_preview",
            "execute",
            "check",
        ]:
            view.action = "retrieve"

        return super(ExcelImportPermissions, self).has_object_permission(
            request, view, obj
        )


class ExcelReportingPermissions(BaseModelAccessPermissions):
    model_name = "ExcelReporting"

    def get_company_id(self, action, request, obj=None):
        if action == "create":
            try:
                excel_import = ExcelImport.objects.get(
                    pk=uuid.UUID(request.data["excel_import"]["id"])
                )
            except Exception as e:
                print(e)
                return False

            return excel_import.company_id

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.excel_import.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return super(ExcelReportingPermissions, self).get_company_id(
                action, request, obj
            )


class PDFImportPermissions(BaseModelAccessPermissions):
    model_name = "PDFImport"

    def has_object_permission(self, request, view, obj):
        if view.action in ["generate_preview", "execute", "check"]:
            view.action = "retrieve"

        return super(PDFImportPermissions, self).has_object_permission(
            request, view, obj
        )


class CSVImportPermissions(BaseModelAccessPermissions):
    model_name = "CSVImport"

    def has_object_permission(self, request, view, obj):
        if view.action in ["generate_preview", "execute", "check", "group"]:
            view.action = "retrieve"

        return super(CSVImportPermissions, self).has_object_permission(
            request, view, obj
        )


class ReportingExportPermissions(BaseModelAccessPermissions):
    model_name = "ReportingExport"
