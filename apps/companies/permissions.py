import uuid

from helpers.permissions import BaseModelAccessPermissions, PermissionManager

from .models import CompanyUsage, Firm, SingleCompanyUsage


class CompanyPermissions(BaseModelAccessPermissions):
    model_name = "Company"

    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in ["HEAD", "OPTIONS"]:
            return True

        company_id = obj.pk

        if not view.permissions:
            view.permissions = PermissionManager(
                user=request.user, company_ids=company_id, model=self.model_name
            )

        if view.action in ["retrieve", "get_reporting_section_fields"]:
            return view.permissions.has_permission(permission="can_view")

        elif view.action == "destroy":
            return view.permissions.has_permission(permission="can_delete")

        elif view.action in ["update", "partial_update"]:
            return view.permissions.has_permission(permission="can_edit")

        elif view.action == "change_metadata":
            return (
                view.permissions.has_permission(permission="can_view")
                if request.method == "GET"
                else view.permissions.has_permission(permission="can_edit")
            )

        elif view.action in ["add_field_option", "custom_options_resource"]:
            return view.permissions.has_permission(
                permission="can_change_custom_options"
            )

        else:
            return False


class SubCompanyPermissions(BaseModelAccessPermissions):
    model_name = "SubCompany"


class FirmPermissions(BaseModelAccessPermissions):
    model_name = "Firm"


class UserInCompanyPermissions(BaseModelAccessPermissions):
    model_name = "UserInCompany"


class AccessRequestPermissions(BaseModelAccessPermissions):
    model_name = "AccessRequest"

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
                return uuid.UUID(request.data["companies"][0]["id"])
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False

    def has_object_permission(self, request, view, obj):
        if view.action == "approval":
            company_id = self.get_company_id("update", request, obj)
            if not company_id and not request.user.is_supervisor:
                return False

            if not obj.approval_step:
                return False

            responsible = []

            if obj.approval_step.responsible_created_by:
                responsible.append(obj.created_by)

            if obj.approval_step.responsible_supervisor:
                responsible.append(obj.user.supervisor)

            for user in obj.approval_step.responsible_users.all():
                responsible.append(user)

            for firm in obj.approval_step.responsible_firms.all():
                if firm.manager:
                    responsible.append(firm.manager)
                for user in firm.users.all():
                    responsible.append(user)

            if len(responsible) and request.user not in responsible:
                return False

            if request.user.is_supervisor:
                return True

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )
            return view.permissions.has_permission(permission="can_approve")

        return super(AccessRequestPermissions, self).has_object_permission(
            request, view, obj
        )


class UserInFirmPermissions(BaseModelAccessPermissions):
    model_name = "UserInFirm"

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
                firm = Firm.objects.get(pk=uuid.UUID(request.data["firm"]["id"]))
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


class InspectorInFirmPermissions(BaseModelAccessPermissions):
    model_name = "InspectorInFirm"

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
                firm = Firm.objects.get(pk=uuid.UUID(request.data["firm"]["id"]))
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


class EntityPermissions(BaseModelAccessPermissions):
    model_name = "Entity"


class CompanyUsagePermissions(BaseModelAccessPermissions):
    model_name = "CompanyUsage"

    def get_company_id(self, action, request, obj=None):
        if action == "create":
            try:
                return uuid.UUID(request.data["companies"][0]["id"])
            except Exception:
                return False

        return super().get_company_id(action, request, obj)


class UserUsagePermissions(BaseModelAccessPermissions):
    model_name = "UserUsage"

    def get_company_id(self, action, request, obj=None):
        if action == "create":
            try:
                company_usage_id = uuid.UUID(request.data["company_usage"]["id"])
                return CompanyUsage.objects.get(pk=company_usage_id).company_id
            except Exception:
                return False

        return super().get_company_id(action, request, obj)


class SingleCompanyUsagePermissions(BaseModelAccessPermissions):
    """Usa o mesmo perfil de CompanyUsage (ex.: can_view, queryset), não SingleCompanyUsage."""

    model_name = "CompanyUsage"

    def get_company_id(self, action, request, obj=None):
        if action == "list":
            company_usage_id = request.query_params.get("company_usage")
            if not company_usage_id:
                return False
            try:
                return CompanyUsage.objects.get(pk=company_usage_id).company_id
            except Exception:
                return False
        if action == "create":
            try:
                company_usage_id = uuid.UUID(request.data["company_usage"]["id"])
                return CompanyUsage.objects.get(pk=company_usage_id).company_id
            except Exception:
                return False
        if action == "retrieve" and obj is not None:
            try:
                return obj.company_usage.company_id
            except Exception:
                return False
        return super().get_company_id(action, request, obj)

    def has_permission(self, request, view):
        if view.action == "retrieve" and "company" not in request.query_params:
            pk = view.kwargs.get(getattr(view, "lookup_field", "pk"))
            if not pk:
                return False
            try:
                obj = SingleCompanyUsage.objects.select_related("company_usage").get(
                    pk=pk
                )
                company_id = obj.company_usage.company_id
                if not company_id:
                    return False
                view.permissions = PermissionManager(
                    user=request.user, company_ids=company_id, model=self.model_name
                )
                return view.permissions.has_permission(permission="can_view")
            except Exception:
                return False
        return super().has_permission(request, view)
