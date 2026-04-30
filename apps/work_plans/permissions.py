from uuid import UUID

import sentry_sdk

from helpers.permissions import BaseModelAccessPermissions, PermissionManager


class JobPermissions(BaseModelAccessPermissions):
    model_name = "Job"

    def get_company_id(self, action, request, obj=None):
        if action == "check_async_creation":
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                sentry_sdk.capture_exception(e)
                return False

        return super().get_company_id(action, request, obj)

    def has_permission(self, request, view):
        if view.action == "check_async_creation":
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

        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        company_id = self.get_company_id(view.action, request, obj)
        if not company_id:
            return False

        if not view.permissions:
            view.permissions = PermissionManager(
                user=request.user, company_ids=company_id, model=self.model_name
            )

        if view.action == "check_async_creation":
            return view.permissions.has_permission(permission="can_view")

        return super().has_object_permission(request, view, obj)


class NoticeViewManagerPermissions(BaseModelAccessPermissions):
    model_name = "NoticeViewManager"

    def has_permission(self, request, view):
        if request.method in ["HEAD", "OPTIONS"]:
            return True
        if view.action in ["must_display", "notice_displayed"]:
            return True

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


class UserNoticeViewPermissions(BaseModelAccessPermissions):
    model_name = "UserNoticeView"
