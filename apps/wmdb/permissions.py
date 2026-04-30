import uuid

from rest_framework.permissions import BasePermission

from apps.companies.models import UserInCompany


class WmdbPermissions(BasePermission):
    def has_permission(self, request, view):
        try:
            company_id = uuid.UUID(request.query_params.get("company"))
        except Exception:
            return False

        if not company_id and not request.user.is_supervisor:
            return False

        return UserInCompany.objects.filter(
            company_id=company_id, user=request.user
        ).exists()
