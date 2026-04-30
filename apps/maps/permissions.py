import uuid

from rest_framework import permissions

from apps.companies.models import Firm, UserInCompany
from helpers.permissions import BaseModelAccessPermissions, PermissionManager
from helpers.strings import to_snake_case


class TileLayerPermissions(BaseModelAccessPermissions):
    model_name = "TileLayer"

    def get_company_id(self, action, request, obj=None):

        if action == "create":
            try:
                return uuid.UUID(request.data["companies"][0]["id"])
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.companies.first().uuid
            except Exception as e:
                print(e)
                return False

        else:
            return super(TileLayerPermissions, self).get_company_id(
                action, request, obj
            )

    def has_object_permission(self, request, view, obj):

        if view.action == "styles_json":
            company_id = self.get_company_id("retrieve", request, obj)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )
            return view.permissions.has_permission(permission="can_view")

        return super(TileLayerPermissions, self).has_object_permission(
            request, view, obj
        )


class ShapeFilePermissions(BaseModelAccessPermissions):
    model_name = "ShapeFile"

    def has_object_permission(self, request, view, obj):
        if view.action in ["get_gzip", "get_pbf"]:
            company_id = self.get_company_id(view.action, request, obj)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )
            return view.permissions.has_permission(permission="can_view")

        return super(ShapeFilePermissions, self).has_object_permission(
            request, view, obj
        )

    def get_company_id(self, action, request, obj=None):

        if action == "create":
            try:
                return uuid.UUID(request.data["companies"][0]["id"])
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.companies.first().uuid
            except Exception as e:
                print(e)
                return False

        elif action in ["get_gzip", "get_pbf"]:
            if self.company_filter_key not in request.query_params:
                return False
            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        else:
            return super(ShapeFilePermissions, self).get_company_id(
                action, request, obj
            )


class ECMPermissions(BaseModelAccessPermissions):
    model_name = "ECMSearch"

    def has_permission(self, request, view):
        if view.action == "list":
            company_id = self.get_company_id(view.action, request)
            if not company_id:
                return False

            firms_can_use_ecm_integration = Firm.objects.filter(
                company=company_id, users=request.user
            ).values_list("can_use_ecm_integration", flat=True)
            return any(firms_can_use_ecm_integration)

        else:
            return False


class EngieSearchPermissions(permissions.BasePermission):
    model_name = "EngieSearch"
    companies_with_permission = []

    def has_permission(self, request, view):
        all_permissions = []
        if view.action == "list":
            perm = "can_view"
            user_companies = request.user.company_group.group_companies.all()

            user_permissions = UserInCompany.objects.filter(
                company__in=user_companies, user=request.user
            ).values_list("permissions__permissions", "company_id")

            for permission, company_id in user_permissions:
                model = ""
                if self.model_name in permission.keys():
                    model = self.model_name
                if to_snake_case(self.model_name) in permission.keys():
                    model = to_snake_case(self.model_name)

                if model:
                    has_perm = permission[model].get(perm, False)
                    all_permissions.append(has_perm)
                    if has_perm:
                        self.companies_with_permission.append(company_id)
                else:
                    all_permissions.append(False)

            return any(all_permissions)
        else:
            return False
