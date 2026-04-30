from helpers.permissions import BaseModelAccessPermissions, PermissionManager
from helpers.strings import is_valid_uuid


class RoadPermissions(BaseModelAccessPermissions):
    model_name = "Road"

    def has_permission(self, request, view):
        if view.action == "create" and request.method == "POST" and request.data:
            if "company" not in request.data:
                return False

            company_ids = []
            for company in request.data["company"]:
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
            return super(RoadPermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if request.method in ["HEAD", "OPTIONS"]:
            return any(i in obj.company.all() for i in request.user.companies.all())

        if not view.permissions:
            view.permissions = PermissionManager(
                user=request.user,
                company_ids=obj.company.all(),
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
