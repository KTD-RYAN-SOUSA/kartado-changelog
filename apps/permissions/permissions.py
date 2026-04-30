import uuid

from rest_framework import permissions

from helpers.permissions import PermissionManager


class UserPermissionAccessPermissions(permissions.BasePermission):
    model_name = "UserPermission"

    def has_permission(self, request, view):
        if request.method in ["HEAD", "OPTIONS"]:
            return True

        if view.action in ["list", "retrieve"]:
            return True

        if view.action == "create" and request.method == "POST":
            try:
                company_id = uuid.UUID(request.data["companies"][0]["id"])
            except Exception:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )
            return view.permissions.has_permission(permission="can_create")

        return True

    def has_object_permission(self, request, view, obj):
        if request.method in ["HEAD", "OPTIONS"]:
            return True

        try:
            company_id = obj.get_company_id
        except Exception:
            return False

        if not view.permissions:
            view.permissions = PermissionManager(
                user=request.user,
                company_ids=company_id,
                model=self.model_name,
            )

        if view.action == "destroy":
            return view.permissions.has_permission(permission="can_delete")

        elif view.action in ["update", "partial_update"]:
            return False

        return True
