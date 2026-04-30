import uuid
from typing import Any, Dict, Iterable, List

from django.db.models.query import QuerySet
from rest_framework import permissions

from apps.companies.models import UserInCompany
from apps.permissions.models import PermissionOccurrenceKindRestriction, UserPermission
from helpers.strings import get_obj_from_path, keys_to_snake_case, to_snake_case


def join_queryset(queryset, other_queryset):
    if queryset is None:
        return other_queryset
    if isinstance(queryset, QuerySet) and isinstance(other_queryset, QuerySet):
        return queryset | other_queryset
    return queryset


class PermissionManager:
    def __init__(self, company_ids, user, model):
        self.model = to_snake_case(model)
        if not isinstance(company_ids, (list, QuerySet)):
            company_ids = [company_ids]

        # Just User/engie_create and OccurrenceRecord/get_serializer_context
        # use this for now, I think it's okay to get the first one
        self.company_id = company_ids[0]

        # Get UserPermissions
        perms = list(
            UserInCompany.objects.filter(
                company_id__in=company_ids, user=user, is_active=True
            ).values_list("permissions_id", "added_permissions")
        )

        perms_ids = []
        for a, b in perms:
            if a:
                perms_ids.append(str(a))
            if b and isinstance(b, list):
                perms_ids += b
        self.user_permissions_objs = (
            UserPermission.objects.filter(uuid__in=perms_ids)
            if perms_ids
            else UserPermission.objects.none()
        )
        self.user_permissions = self.user_permissions_objs.values_list(
            "permissions", flat=True
        )
        self.all_permissions = self.get_all_permission()

    def get_all_permission(self):
        permission = {}

        self.user_permissions_dict = {
            str(item.uuid): keys_to_snake_case(item.permissions)
            for item in self.user_permissions_objs
        }
        permissions_dicts = self.user_permissions_dict.values()

        for perm_dict in permissions_dicts:
            for model_name, model_perms in perm_dict.items():
                if model_name not in permission:
                    permission[model_name] = {}
                for perm_name, perm_value in model_perms.items():
                    if perm_name not in permission[model_name]:
                        permission[model_name][perm_name] = []
                    permission[model_name][perm_name].append(perm_value)

        return permission

    def has_profile(self, permission):
        return (
            self.all_permissions
            and self.model in self.all_permissions
            and permission in self.all_permissions[self.model]
        )

    def has_permission(self, permission):
        """
        Checks the system's permissionability

        Expects:
        Returns:
            Default: False
            True if any given permission is True for that specific
            model permissionability
        """
        if self.has_profile(permission):
            return any(self.all_permissions[self.model][permission])
        return False

    def has_all_required_permissions(
        self, required_permissions: Dict[str, Any]
    ) -> bool:
        """
        Ensure that, given a dict of required permissions for a model, the User's
        permissions are matched.

        Args:
            needed_permissions (Dict[str, Any]): Dict with all the required permissions
            for the model.

        Returns:
            bool: Returns True if the User has all the provided permissions.
        """

        for permission, value in required_permissions.items():
            # Require at least one of the required querysets (if there's any)
            if permission == "queryset" and not self.has_required_queryset(value):
                return False

            # Ensure all required permissions are in place
            if permission != "queryset" and not self.has_permission(permission):
                return False

        # If we get to the end this means all required permissions match that User's permissions
        return True

    def companies_which_has_permission(self, permission):
        if self.has_profile(permission):
            user_permissions_ids = [
                key
                for key, value in self.user_permissions_dict.items()
                if get_obj_from_path(value, "{}__{}".format(self.model, permission))
            ]
            return (
                self.user_permissions_objs.filter(uuid__in=user_permissions_ids)
                .values_list("companies", flat=True)
                .distinct()
            )
        return []

    def get_permission(self, permission):
        if self.has_profile(permission):
            return self.all_permissions[self.model][permission]
        return []

    def get_model_permission(self, model_name):
        if self.all_permissions and to_snake_case(model_name) in self.all_permissions:
            return self.all_permissions[to_snake_case(model_name)]
        return {}

    def has_flow_permission(self, permission, origin_status, final_status):
        if (
            self.has_profile(permission)
            and self.all_permissions[self.model][permission]
            and isinstance(self.all_permissions[self.model][permission], list)
        ):
            # Probably we need a better way to join this
            # permissions instead of getting the first one
            flow_permission = self.all_permissions[self.model][permission][0]
            return final_status in flow_permission.get(origin_status, [])
        return False

    def get_allowed_queryset(self) -> List[str]:
        if self.has_profile("queryset"):
            return self.all_permissions[self.model]["queryset"]
        return ["none"]

    def has_required_queryset(
        self, required_queryset: Iterable[str], require_all=False
    ) -> bool:
        """
        Receives a list of the required querysets and check if they
        match the User's permissions.

        Args:
            required_queryset (Iterable[str]): List of the required querysets
            require_all (bool, optional): Set to true if you want all querysets to match the User permissions,
            not just one. Defaults to False.

        Returns:
            bool: Returns True if the User has permission to the provided querysets.
        """

        allowed_querysets = self.get_allowed_queryset()

        # In case a non iterable is provided attempt to create one
        iter_required_querysets = (
            [required_queryset]
            if not isinstance(required_queryset, Iterable)
            else required_queryset
        )

        # Check if the iterable is part of the superset allowed_queryset
        matches_list = [
            req_queryset_item in allowed_querysets
            for req_queryset_item in iter_required_querysets
        ]

        return all(matches_list) if require_all else any(matches_list)

    def get_specific_model_permision(self, model_name, permission):
        if self.all_permissions and to_snake_case(model_name) in self.all_permissions:
            try:
                return self.all_permissions[to_snake_case(model_name)][permission][0]
            except Exception:
                return None

        return {}

    def get_allowed_occurrence_kinds(self) -> List[str]:
        """
        Returns the list of allowed occurrence kinds for the current user's permissions.

        Queries PermissionOccurrenceKindRestriction for all user permission profiles
        and the current company. Merges values from multiple profiles if the user
        has added_permissions.

        Returns:
            List[str]: List of allowed occurrence kind values (e.g., ["1", "2", "3"]).
                       Empty list means no restriction (full access).
        """
        if not self.user_permissions_objs.exists():
            return []

        restrictions = PermissionOccurrenceKindRestriction.objects.filter(
            user_permission__in=self.user_permissions_objs,
            company_id=self.company_id,
        ).values_list("allowed_occurrence_kinds", flat=True)

        if not restrictions:
            return []

        # Merge all allowed kinds from multiple permission profiles
        allowed_kinds = set()
        for kinds_list in restrictions:
            if kinds_list:
                allowed_kinds.update(kinds_list)

        return list(allowed_kinds)


class BaseModelAccessPermissions(permissions.BasePermission):
    model_name = None
    company_filter_key = "company"

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
                return uuid.UUID(request.data["company"]["id"])
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

        elif view.action == "create" and request.method == "POST" and request.data:
            company_id = self.get_company_id(view.action, request)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )
            return view.permissions.has_permission(permission="can_create")

        else:
            return True

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

        elif view.action == "destroy":
            return view.permissions.has_permission(permission="can_delete")

        elif view.action in ["update", "partial_update"]:
            return view.permissions.has_permission(permission="can_edit")

        else:
            return False
