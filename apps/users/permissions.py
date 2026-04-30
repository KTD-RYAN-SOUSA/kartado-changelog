from uuid import UUID

from rest_framework import permissions

from apps.companies.models import Company
from helpers.permissions import BaseModelAccessPermissions, PermissionManager


class UserPermissions(BaseModelAccessPermissions):
    model_name = "User"

    def has_permission(self, request, view):
        if view.action == "engie_preview":
            company_id = self.get_company_id("list", request)
        elif view.action == "engie_create":
            company_id = self.get_company_id("create", request)
        elif view.action == "history":
            company_id = self.get_company_id("retrieve", request)
        else:
            return super(UserPermissions, self).has_permission(request, view)

        if not company_id:
            return False

        if not view.permissions:
            view.permissions = PermissionManager(
                user=request.user, company_ids=company_id, model=self.model_name
            )
        if view.action == "history":
            return view.permissions.has_permission(permission="can_edit")

        return view.permissions.has_permission(permission="can_use_rh_api")

    def has_object_permission(self, request, view, obj):
        # allow logged in user to view own details, allows staff to view all records
        if request.method in ["HEAD", "OPTIONS"]:
            return any(i in obj.companies.all() for i in request.user.companies.all())

        if view.action in ["email_unsubscribe", "register_push", "accept_tos"]:
            return True

        if view.action in ["update", "partial_update"] and request.data.get(
            "active_company"
        ):
            try:
                companies = [Company.objects.get(pk=request.data.get("active_company"))]
            except Exception:
                return False
        else:
            if obj.company_group and obj.company_group.group_companies.exists():
                companies = obj.company_group.group_companies.all()
            elif obj.companies.exists():
                companies = obj.companies.all()
            else:
                return False

        if not view.permissions:
            view.permissions = PermissionManager(
                user=request.user, company_ids=companies, model=self.model_name
            )
        if view.action == "destroy":
            return view.permissions.has_permission(permission="can_delete")

        elif view.action == "retrieve":
            return view.permissions.has_permission(permission="can_view")

        elif view.action == "history":
            return view.permissions.has_permission(permission="can_edit")

        elif view.action in ["update", "partial_update"]:
            levels = []
            for item in view.permissions.get_permission(permission="can_edit"):
                if item == "self":
                    levels.append(True if obj == request.user else False)
                else:
                    levels.append(item)
            return any(levels)

        else:
            return False


class UserNotificationPermissions(BaseModelAccessPermissions):
    model_name = "UserNotification"

    def get_company_id(self, action, request, obj=None):
        if action == "create":
            try:
                provided_id = request.data["companies"][0]["id"]
                return UUID(provided_id)
            except Exception:
                return False
        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.get_company_id
            except Exception:
                return False

        return super().get_company_id(action, request, obj)


class IsUserAuthenticated(permissions.BasePermission):
    """
    Allows access only to authenticated users.
    """

    def has_permission(self, request, view):
        if view.action in ["list", "retrieve"]:
            return request.user and request.user.is_authenticated

        elif view.action == "create":
            return False

        else:
            return True

    def has_object_permission(self, request, view, obj):
        if request.method in ["HEAD", "OPTIONS"]:
            return True

        if view.action in ["retrieve", "update", "partial_update"]:
            if obj == request.user:
                return True

        if view.action == "destroy":
            return False

        return False


class UserSignaturePermissions(BaseModelAccessPermissions):
    model_name = "UserSignature"

    def has_object_permission(self, request, view, obj):
        if view.action == "check":
            view.action = "retrieve"
        return super().has_object_permission(request, view, obj)
