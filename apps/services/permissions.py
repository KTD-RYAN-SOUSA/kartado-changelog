import uuid

from rest_framework.exceptions import ValidationError

from apps.reportings.models import Reporting
from helpers.permissions import BaseModelAccessPermissions, PermissionManager

from .models import GoalAggregate, Service


class ServicePermissions(BaseModelAccessPermissions):
    model_name = "Service"


class ServiceChildPermissions(BaseModelAccessPermissions):
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
                service = Service.objects.get(
                    pk=uuid.UUID(request.data["service"]["id"])
                )
                return service.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.service.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class ServiceSpecsPermissions(ServiceChildPermissions):
    model_name = "ServiceSpecs"


class ServiceUsagePermissions(ServiceChildPermissions):
    model_name = "ServiceUsage"

    def get_company_id(self, action, request, obj=None):

        if action == "create":
            # check if reporting is editable
            if "reporting" in request.data:
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

                if not reporting.editable:
                    raise ValidationError("kartado.error.reporting.not_editable")

        elif action in ["update", "partial_update", "destroy"]:
            # check if reporting is editable
            if obj.reporting and not obj.reporting.editable:
                raise ValidationError("kartado.error.reporting.not_editable")

        # for other methods, fall back to the parent's method
        return super(ServiceUsagePermissions, self).get_company_id(action, request, obj)


class MeasurementServicePermissions(ServiceChildPermissions):
    model_name = "MeasurementService"


class MeasurementPermissions(BaseModelAccessPermissions):
    model_name = "Measurement"

    def has_object_permission(self, request, view, obj):
        if view.action == "update_services" and request.method == "POST":
            # We can retrieve the id with 'update' because our operation is the
            # same as an update request
            company = self.get_company_id("update", None, obj)

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company,
                    model=self.model_name,
                )

            return view.permissions.has_permission(permission="can_edit")

        if view.action in ["transports", "dnit_rdo", "summary"]:
            company = self.get_company_id("update", None, obj)

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company,
                    model=self.model_name,
                )

            return view.permissions.has_permission(permission="can_view")

        else:
            return super(MeasurementPermissions, self).has_object_permission(
                request, view, obj
            )


class GoalPermissions(BaseModelAccessPermissions):
    model_name = "Goal"

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
                aggregate = GoalAggregate.objects.get(
                    pk=uuid.UUID(request.data["aggregate"]["id"])
                )
                return aggregate.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.aggregate.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False

    def has_permission(self, request, view):
        if view.action == "bulk_create":
            company_id = self.get_company_id("create", request)
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
            return super(GoalPermissions, self).has_permission(request, view)


class GoalAggregatePermissions(BaseModelAccessPermissions):
    model_name = "GoalAggregate"
