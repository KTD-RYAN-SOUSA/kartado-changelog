import uuid

from django.utils import timezone
from fnc.mappings import get
from rest_framework_json_api.serializers import ValidationError

from apps.companies.models import Firm
from apps.monitorings.models import (
    MaterialItem,
    MonitoringCycle,
    MonitoringPlan,
    OperationalControl,
)
from apps.occurrence_records.models import OccurrenceRecord
from helpers.permissions import BaseModelAccessPermissions, PermissionManager


class MonitoringPlanPermissions(BaseModelAccessPermissions):
    model_name = "MonitoringPlan"

    def has_object_permission(self, request, view, obj):
        if view.action in ["update", "partial_update"]:
            company_id = self.get_company_id(view.action, request, obj)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            is_homologator = view.permissions.has_permission(permission="can_create")
            can_edit = view.permissions.has_permission(permission="can_edit")
            return is_homologator and can_edit

        if view.action == "monitoring_schedule":
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

        return super(MonitoringPlanPermissions, self).has_object_permission(
            request, view, obj
        )

    def get_company_id(self, action, request, obj=None):

        if action in ["monitoring_schedule"]:

            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        else:
            return super(MonitoringPlanPermissions, self).get_company_id(
                action, request, obj
            )


class MonitoringPlanChildPermissions(BaseModelAccessPermissions):
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
                monitoring_plan = MonitoringPlan.objects.get(
                    pk=uuid.UUID(request.data["monitoring_plan"]["id"])
                )
            except Exception as e:
                print(e)
                return False

            return monitoring_plan.company_id

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.monitoring_plan.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class MonitoringPointPermissions(MonitoringPlanChildPermissions):
    model_name = "MonitoringPoint"

    def has_permission(self, request, view):
        if view.action == "create" and request.method == "POST" and request.data:
            company_id = self.get_company_id(view.action, request)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            all_permission = view.permissions.all_permissions
            can_edit_monitoring = any(
                get("monitoring_plan.can_edit", all_permission, default=[])
            )
            is_homologator = any(
                get("monitoring_plan.can_create", all_permission, default=[])
            )
            can_create = view.permissions.has_permission(permission="can_create")
            if is_homologator:
                return can_edit_monitoring and can_create

            try:
                now = timezone.now()
                monitoring = MonitoringPlan.objects.get(
                    pk=request.data["monitoring_plan"]["id"]
                )
                monitoring_in_final_status = monitoring.status.is_final
                is_responsible_active = MonitoringCycle.objects.filter(
                    monitoring_plan=monitoring,
                    start_date__date__lte=now.date(),
                    end_date__date__gte=now.date(),
                    responsibles=request.user,
                ).exists()
            except Exception:
                is_responsible_active = False
                monitoring_in_final_status = False

            return (
                can_edit_monitoring
                and can_create
                and is_responsible_active
                and not monitoring_in_final_status
            )

        return super(MonitoringPointPermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if view.action in ["update", "partial_update"]:
            company_id = self.get_company_id(view.action, request, obj)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            all_permission = view.permissions.all_permissions
            can_edit_monitoring = any(
                get("monitoring_plan.can_edit", all_permission, default=[])
            )
            is_homologator = any(
                get("monitoring_plan.can_create", all_permission, default=[])
            )
            can_edit = view.permissions.has_permission(permission="can_edit")
            if is_homologator:
                return can_edit_monitoring and can_edit

            try:
                now = timezone.now()
                monitoring_in_final_status = obj.monitoring_plan.status.is_final
                is_responsible_active = MonitoringCycle.objects.filter(
                    monitoring_plan=obj.monitoring_plan,
                    start_date__date__lte=now.date(),
                    end_date__date__gte=now.date(),
                    responsibles=request.user,
                ).exists()
            except Exception:
                is_responsible_active = False
                monitoring_in_final_status = False

            return (
                can_edit_monitoring
                and can_edit
                and is_responsible_active
                and not monitoring_in_final_status
            )

        return super(MonitoringPointPermissions, self).has_object_permission(
            request, view, obj
        )


class MonitoringCyclePermissions(MonitoringPlanChildPermissions):
    model_name = "MonitoringCycle"

    def has_permission(self, request, view):
        if view.action == "create" and request.method == "POST" and request.data:
            company_id = self.get_company_id(view.action, request)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            all_permission = view.permissions.all_permissions
            can_edit_monitoring = any(
                get("monitoring_plan.can_edit", all_permission, default=[])
            )
            is_homologator = any(
                get("monitoring_plan.can_create", all_permission, default=[])
            )
            can_create = view.permissions.has_permission(permission="can_create")
            return is_homologator and can_edit_monitoring and can_create

        return super(MonitoringCyclePermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if view.action in ["update", "partial_update"]:
            company_id = self.get_company_id(view.action, request, obj)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            all_permission = view.permissions.all_permissions
            can_edit_monitoring = any(
                get("monitoring_plan.can_edit", all_permission, default=[])
            )
            is_homologator = any(
                get("monitoring_plan.can_create", all_permission, default=[])
            )
            can_edit = view.permissions.has_permission(permission="can_edit")
            return is_homologator and can_edit_monitoring and can_edit

        return super(MonitoringCyclePermissions, self).has_object_permission(
            request, view, obj
        )


class MonitoringFrequencyPermissions(MonitoringPlanChildPermissions):
    model_name = "MonitoringFrequency"

    def has_permission(self, request, view):
        if view.action == "create" and request.method == "POST" and request.data:
            company_id = self.get_company_id(view.action, request)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            all_permission = view.permissions.all_permissions
            can_edit_monitoring = any(
                get("monitoring_plan.can_edit", all_permission, default=[])
            )
            is_homologator = any(
                get("monitoring_plan.can_create", all_permission, default=[])
            )
            can_create = view.permissions.has_permission(permission="can_create")
            if is_homologator:
                return can_edit_monitoring and can_create

            try:
                now = timezone.now()
                monitoring = MonitoringPlan.objects.get(
                    pk=request.data["monitoring_plan"]["id"]
                )
                monitoring_in_final_status = monitoring.status.is_final
                is_responsible_active = MonitoringCycle.objects.filter(
                    monitoring_plan=monitoring,
                    start_date__date__lte=now.date(),
                    end_date__date__gte=now.date(),
                    responsibles=request.user,
                ).exists()
            except Exception:
                is_responsible_active = False
                monitoring_in_final_status = False

            return (
                can_edit_monitoring
                and can_create
                and is_responsible_active
                and not monitoring_in_final_status
            )

        return super(MonitoringFrequencyPermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if view.action == "destroy":
            if obj.frequency_collects.exists():
                raise ValidationError(
                    "Não é possível apagar frequências com coletas realizadas."
                )

        if view.action in ["update", "partial_update"]:
            company_id = self.get_company_id(view.action, request, obj)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            all_permission = view.permissions.all_permissions
            can_edit_monitoring = any(
                get("monitoring_plan.can_edit", all_permission, default=[])
            )
            is_homologator = any(
                get("monitoring_plan.can_create", all_permission, default=[])
            )
            can_edit = view.permissions.has_permission(permission="can_edit")
            if is_homologator:
                return can_edit_monitoring and can_edit

            try:
                now = timezone.now()
                monitoring_in_final_status = obj.monitoring_plan.status.is_final
                is_responsible_active = MonitoringCycle.objects.filter(
                    monitoring_plan=obj.monitoring_plan,
                    start_date__date__lte=now.date(),
                    end_date__date__gte=now.date(),
                    responsibles=request.user,
                ).exists()
            except Exception:
                is_responsible_active = False
                monitoring_in_final_status = False

            return (
                can_edit_monitoring
                and can_edit
                and is_responsible_active
                and not monitoring_in_final_status
            )

        return super(MonitoringFrequencyPermissions, self).has_object_permission(
            request, view, obj
        )


class MonitoringCampaignPermissions(MonitoringPlanChildPermissions):
    model_name = "MonitoringCampaign"

    def has_object_permission(self, request, view, obj):
        if view.action == "destroy":
            if obj.monitoring_records.count():
                raise ValidationError(
                    "Não é possível apagar campanhas com coletas realizadas."
                )

        return super(MonitoringCampaignPermissions, self).has_object_permission(
            request, view, obj
        )


class MonitoringRecordPermissions(BaseModelAccessPermissions):
    model_name = "MonitoringRecord"


class MonitoringCollectPermissions(BaseModelAccessPermissions):
    model_name = "MonitoringCollect"

    def has_permission(self, request, view):
        if view.action == "create" and request.method == "POST" and request.data:
            company_id = self.get_company_id(view.action, request)
            if not company_id:
                return False

            try:
                occurrence_record = OccurrenceRecord.objects.get(
                    pk=request.data["occurrence_record"]["id"]
                )
            except OccurrenceRecord.DoesNotExist:
                return False

            monitoring = occurrence_record.monitoring_plan
            if not monitoring:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            all_permission = view.permissions.all_permissions
            can_view_monitoring = any(
                get("monitoring_plan.can_view", all_permission, default=[])
            )
            can_create_record = any(
                get("occurrence_record.can_create", all_permission, default=[])
            )
            can_create_monitoring = any(
                get(
                    "occurrence_record.can_create_monitoring",
                    all_permission,
                    default=[],
                )
            )
            can_create_collect = view.permissions.has_permission(
                permission="can_create"
            )

            try:
                now = timezone.now()
                monitoring_in_final_status = monitoring.status.is_final
                is_executer_active = MonitoringCycle.objects.filter(
                    monitoring_plan=monitoring,
                    start_date__date__lte=now.date(),
                    end_date__date__gte=now.date(),
                    executers__in=request.user.user_firms.all(),
                ).exists()
            except Exception:
                is_executer_active = False
                monitoring_in_final_status = False

            return (
                can_create_collect
                and can_view_monitoring
                and can_create_record
                and monitoring_in_final_status
                and (can_create_monitoring or is_executer_active)
            )

        return super(MonitoringCollectPermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if view.action in ["update", "partial_update"]:
            company_id = self.get_company_id(view.action, request, obj)
            if not company_id:
                return False

            monitoring = obj.occurrence_record.monitoring_plan
            if not monitoring:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            all_permission = view.permissions.all_permissions
            can_view_monitoring = any(
                get("monitoring_plan.can_view", all_permission, default=[])
            )
            can_edit_record = any(
                get("occurrence_record.can_edit", all_permission, default=[])
            )
            can_create_monitoring = any(
                get(
                    "occurrence_record.can_create_monitoring",
                    all_permission,
                    default=[],
                )
            )
            can_edit_collect = view.permissions.has_permission(permission="can_edit")

            try:
                now = timezone.now()
                monitoring_in_final_status = monitoring.status.is_final
                is_executer_active = MonitoringCycle.objects.filter(
                    monitoring_plan=monitoring,
                    start_date__date__lte=now.date(),
                    end_date__date__gte=now.date(),
                    executers__in=request.user.user_firms.all(),
                ).exists()
            except Exception:
                is_executer_active = False
                monitoring_in_final_status = False

            return (
                can_edit_collect
                and can_view_monitoring
                and can_edit_record
                and monitoring_in_final_status
                and (can_create_monitoring or is_executer_active)
            )

        return super(MonitoringCollectPermissions, self).has_object_permission(
            request, view, obj
        )


class OperationalControlPermissions(BaseModelAccessPermissions):
    model_name = "OperationalControl"

    def get_company_id(self, action, request, obj=None):

        if action == "create":
            try:
                firm = Firm.objects.get(pk=uuid.UUID(request.data["firm"]["id"]))
            except Exception as e:
                print(e)
                return False

            return firm.company_id

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.firm.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return super(OperationalControlPermissions, self).get_company_id(
                action, request, obj
            )

    def has_object_permission(self, request, view, obj):

        if view.action == "get_plots":
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

        return super(OperationalControlPermissions, self).has_object_permission(
            request, view, obj
        )


class OperationalCyclePermissions(BaseModelAccessPermissions):
    model_name = "OperationalCycle"

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
                operational_control = OperationalControl.objects.get(
                    pk=uuid.UUID(request.data["operational_control"]["id"])
                )
            except Exception as e:
                print(e)
                return False

            return operational_control.firm.company_id

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.operational_control.firm.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class MaterialItemPermissions(BaseModelAccessPermissions):
    model_name = "MaterialItem"


class MaterialUsagePermissions(BaseModelAccessPermissions):
    model_name = "MaterialUsage"

    def get_company_id(self, action, request, obj=None):
        if action == "create":
            try:
                material_item = MaterialItem.objects.get(
                    pk=uuid.UUID(request.data["material_item"]["id"])
                )
            except Exception as e:
                print(e)
                return False

            return material_item.company_id

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.material_item.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return super(MaterialUsagePermissions, self).get_company_id(
                action, request, obj
            )
