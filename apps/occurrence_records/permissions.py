import uuid

from django.utils import timezone
from fnc.mappings import get
from rest_framework_json_api.serializers import ValidationError

from apps.companies.models import UserInCompany
from apps.monitorings.models import (
    MonitoringCycle,
    MonitoringPlan,
    OperationalControl,
    OperationalCycle,
)
from helpers.apps.json_logic import apply_json_logic
from helpers.apps.occurrence_records import is_responsible_approval_monitoring_record
from helpers.permissions import BaseModelAccessPermissions, PermissionManager
from helpers.strings import is_valid_uuid, to_snake_case

from .models import OccurrenceRecord


class OccurrenceTypePermissions(BaseModelAccessPermissions):
    model_name = "OccurrenceType"

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
            return super(OccurrenceTypePermissions, self).has_permission(request, view)

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

        elif view.action in ["retrieve", "get_gzip", "get_pbf"]:
            return view.permissions.has_permission(permission="can_view")

        elif view.action in ["update", "partial_update"]:
            return view.permissions.has_permission(permission="can_edit")

        else:
            return False


class ParameterGroupPermissions(OccurrenceTypePermissions):
    model_name = "ParameterGroup"

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
                    model="OccurrenceType",
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

        return super(ParameterGroupPermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if view.action == "destroy":
            if obj.parameter_group_collects.exists():
                raise ValidationError(
                    "Não é possível apagar grupos de parâmetros com coletas realizadas."
                )

        if view.action in ["update", "partial_update"]:
            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=obj.company.all(),
                    model="OccurrenceType",
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

        return super(ParameterGroupPermissions, self).has_object_permission(
            request, view, obj
        )


class OccurrenceTypeSpecsPermissions(BaseModelAccessPermissions):
    model_name = "OccurrenceTypeSpecs"


class OccurrenceRecordPermissions(BaseModelAccessPermissions):
    model_name = "OccurrenceRecord"
    companies_with_permission = []

    def has_object_permission(self, request, view, obj):
        if request.method in ["HEAD", "OPTIONS"]:
            return True

        if view.action in ["update", "partial_update"]:
            view.has_permission_operational = True

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
            can_view_monitoring = any(
                get("monitoring_plan.can_view", all_permission, default=[])
            )
            can_view_operational = any(
                get("operational_control.can_view", all_permission, default=[])
            )

            # Check if it is operational
            if obj.operational_control:
                now = timezone.now()
                current_cycle = OperationalCycle.objects.filter(
                    operational_control__firm__company_id=company_id,
                    operational_control=obj.operational_control,
                    start_date__date__lte=now.date(),
                    end_date__date__gte=now.date(),
                    creators__in=request.user.user_firms.all(),
                )

                try:
                    is_user_responsible = (
                        obj.operational_control.responsible == request.user
                    )
                except Exception:
                    is_user_responsible = False

                has_permission = (
                    can_view_operational
                    and view.permissions.has_permission(permission="can_edit")
                    and (
                        view.permissions.has_permission(
                            permission="can_create_operational"
                        )
                        or (current_cycle.exists())
                        or is_user_responsible
                    )
                )

                # if is from mobile just return True and the update method
                # from the view will check about the permission
                if get("form_data.record_source", request.data, default="") == "MOBILE":
                    view.has_permission_operational = has_permission
                    return True

                enable_edit = obj.approval_step and obj.approval_step.field_options.get(
                    "enable_edit", False
                )

                if has_permission and (obj.editable or enable_edit):
                    return True

            elif obj.monitoring_plan:
                if not obj.monitoring_plan.status.is_final:
                    return False

                now = timezone.now()
                current_cycle = MonitoringCycle.objects.filter(
                    monitoring_plan__company_id=company_id,
                    monitoring_plan=obj.monitoring_plan,
                    start_date__date__lte=now.date(),
                    end_date__date__gte=now.date(),
                    executers__in=request.user.user_firms.all(),
                )

                has_permission = (
                    can_view_monitoring
                    and view.permissions.has_permission(permission="can_edit")
                    and (
                        view.permissions.has_permission(
                            permission="can_create_monitoring"
                        )
                        or (current_cycle.exists())
                    )
                )
                if has_permission:
                    return True
            # Possible to update watcher_users and/or watcher_firms with editable flag false
            possible_fields = ["watcher_users", "watcher_firms", "uuid", "id"]
            boolean_fields = [item in possible_fields for item in request.data.keys()]
            # Possible to update if has flag enable_edit
            enable_edit = obj.approval_step and obj.approval_step.field_options.get(
                "enable_edit", False
            )

            if all(boolean_fields) or enable_edit:
                return view.permissions.has_permission(permission="can_edit")
            else:
                return obj.editable

        elif view.action in [
            "pdf_occurrence_record",
            "find_intersects",
            "pdf_report_occurrence_record",
        ]:
            company = self.get_company_id("update", None, obj)
            if not company:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company,
                    model=self.model_name,
                )

            return view.permissions.has_permission(permission="can_view")

        elif (
            view.action == "approval" or view.action == "change_status"
        ) and request.method == "POST":
            company_id = self.get_company_id("update", request, obj)
            if not company_id:
                return False

            if not obj.approval_step:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            user_firms = request.user.user_firms.filter(company_id=company_id)

            # Check if it is monitoring
            if obj.monitoring_plan:
                can_approve = view.permissions.has_permission(permission="can_approve")
                has_perm = is_responsible_approval_monitoring_record(
                    obj, user_firms, can_approve
                )
                return has_perm

            data = {
                "occurrence_record": obj.__dict__,
                "user": request.user.__dict__,
                "user_permission": view.permissions.all_permissions,
                "user_firms": user_firms.values(),
            }

            user_in_responsibles = apply_json_logic(
                obj.approval_step.responsible_json_logic, data
            )

            user_in_firm_entity = False
            if (
                obj.approval_step.responsible_firm_entity
                and obj.firm
                and obj.firm.entity
                and obj.firm.entity.approver_firm
                and obj.firm.entity.approver_firm.uuid
                in [
                    a.uuid
                    for a in request.user.user_firms.filter(company_id=company_id)
                ]
            ):
                user_in_firm_entity = True

            responsibles = []
            if obj.approval_step.responsible_created_by:
                responsibles.append(obj.created_by)

            if obj.approval_step.responsible_firm_manager and obj.firm.manager:
                responsibles.append(obj.firm.manager)

            for user in obj.approval_step.responsible_users.all():
                responsibles.append(user)

            for firm in obj.approval_step.responsible_firms.all():
                if firm.manager:
                    responsibles.append(firm.manager)
                for user in firm.users.all():
                    responsibles.append(user)

            if (
                not user_in_responsibles
                and not user_in_firm_entity
                and request.user not in responsibles
            ):
                return False

            return view.permissions.has_permission(permission="can_approve")

        elif view.action == "change_service_order" and request.method == "POST":
            company = obj.company

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company.uuid,
                    model=self.model_name,
                )

            return view.permissions.has_permission(permission="can_edit")

        else:
            return super(OccurrenceRecordPermissions, self).has_object_permission(
                request, view, obj
            )

    def has_permission(self, request, view):
        if view.action == "occurrence_record_bi":
            # Checks if the user has `can_view_bi` in any of his companies to use
            # the OccurrenceRecord/BI endpoint.
            all_permissions = []
            perm = "can_view_bi"
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
        elif view.action == "create" and request.method == "POST" and request.data:
            view.has_permission_operational = True

            company_id = self.get_company_id(view.action, request)
            if not company_id:
                return False

            is_operational = get("operational_control.id", request.data, default=False)
            is_monitoring = get("monitoring_plan.id", request.data, default=False)

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
            can_view_operational = any(
                get("operational_control.can_view", all_permission, default=[])
            )

            if is_operational:
                now = timezone.now()
                current_cycle = OperationalCycle.objects.filter(
                    operational_control__firm__company_id=company_id,
                    operational_control_id=is_operational,
                    start_date__date__lte=now.date(),
                    end_date__date__gte=now.date(),
                    creators__in=request.user.user_firms.all(),
                )

                try:
                    is_user_responsible = (
                        OperationalControl.objects.get(pk=is_operational).responsible
                        == request.user
                    )
                except Exception:
                    is_user_responsible = False

                has_permission = (
                    can_view_operational
                    and view.permissions.has_permission(permission="can_create")
                    and (
                        view.permissions.has_permission(
                            permission="can_create_operational"
                        )
                        or (current_cycle.exists())
                        or is_user_responsible
                    )
                )

                # if it is from mobile just return True and the create method
                # from the view will check about the permission
                if get("form_data.record_source", request.data, default="") == "MOBILE":
                    view.has_permission_operational = has_permission
                    return True

                return has_permission
            elif is_monitoring:
                monitoring = MonitoringPlan.objects.filter(
                    pk=is_monitoring, status__is_final=True
                )
                if not monitoring.exists():
                    return False

                now = timezone.now()
                current_cycle = MonitoringCycle.objects.filter(
                    monitoring_plan__company_id=company_id,
                    monitoring_plan_id=is_monitoring,
                    start_date__date__lte=now.date(),
                    end_date__date__gte=now.date(),
                    executers__in=request.user.user_firms.all(),
                )

                has_permission = (
                    can_view_monitoring
                    and view.permissions.has_permission(permission="can_create")
                    and (
                        view.permissions.has_permission(
                            permission="can_create_monitoring"
                        )
                        or (current_cycle.exists())
                    )
                )
                return has_permission
            else:
                return view.permissions.has_permission(permission="can_create")
        else:
            return super(OccurrenceRecordPermissions, self).has_permission(
                request, view
            )


class AdditionalDocumentPermissions(OccurrenceRecordPermissions):
    model_name = "AdditionalDocument"


class OccurrenceRecordChildPermissions(BaseModelAccessPermissions):
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
                occurrence_record = OccurrenceRecord.objects.get(
                    pk=uuid.UUID(request.data["occurrence_record"]["id"])
                )
                return occurrence_record.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.occurrence_record.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class OccurrenceRecordWatcherPermissions(OccurrenceRecordChildPermissions):
    model_name = "OccurrenceRecordWatcher"


class RecordPanelPermissions(BaseModelAccessPermissions):
    model_name = "RecordPanel"

    def get_company_id(self, action, request, obj=None):
        if action in ["get_kanban", "get_gzip", "mark_panel_as_seen", "get_pbf"]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        return super().get_company_id(action, request, obj)

    def has_permission(self, request, view):
        if view.action in ["get_kanban", "get_gzip", "mark_panel_as_seen", "get_pbf"]:
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
        if view.action in ["get_kanban", "get_gzip", "mark_panel_as_seen", "get_pbf"]:
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

        if view.action in ["update", "partial_update"]:
            user_firms = request.user.user_firms.all()
            user_permissions = UserInCompany.objects.filter(
                company_id=obj.company, user=request.user
            ).values_list("permissions", flat=True)

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=obj.company,
                    model=self.model_name,
                )

            has_all_permissions = view.permissions.has_required_queryset(["all"])
            is_creator = request.user == obj.created_by
            is_viewer = obj.viewer_users.filter(pk=request.user.uuid).exists()
            is_editor = obj.editor_users.filter(pk=request.user.uuid).exists()

            part_of_editor_firm = obj.editor_firms.filter(pk__in=user_firms)
            part_of_viewer_firm = obj.viewer_firms.filter(pk__in=user_firms)

            has_editor_user_permission = obj.editor_permissions.filter(
                pk__in=user_permissions
            )
            has_viewer_user_permission = obj.viewer_permissions.filter(
                pk__in=user_permissions
            )
            has_editor_subcompanies_permission = obj.editor_subcompanies.filter(
                subcompany_firms__in=user_firms
            )

            return any(
                [
                    is_creator,
                    is_editor,
                    part_of_editor_firm,
                    has_editor_user_permission,
                    is_viewer,
                    part_of_viewer_firm,
                    has_viewer_user_permission,
                    has_editor_subcompanies_permission,
                    has_all_permissions,
                ]
            )

        if view.action == "destroy":
            if request.user != obj.created_by:
                return False

        return super().has_object_permission(request, view, obj)


class CustomDashboardPermissions(BaseModelAccessPermissions):
    model_name = "CustomDashboard"

    def has_object_permission(self, request, view, obj):
        is_viewer = obj.can_be_viewed_by.filter(uuid=request.user.uuid).exists()
        is_editor = obj.can_be_edited_by.filter(uuid=request.user.uuid).exists()

        if (is_viewer or is_editor) and view.action == "retrieve":
            return True
        if is_editor and view.action in ["update", "partial_update"]:
            return True

        return super().has_object_permission(request, view, obj)


class DataSeriesPermissions(BaseModelAccessPermissions):
    model_name = "DataSeries"

    def has_object_permission(self, request, view, obj):
        if view.action == "get_data":
            company_id = self.get_company_id("list", request, obj)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            return view.permissions.has_permission(permission="can_view")

        return super().has_object_permission(request, view, obj)


class CustomTablePermissions(BaseModelAccessPermissions):
    model_name = "CustomTable"

    def has_object_permission(self, request, view, obj):
        is_viewer = obj.can_be_viewed_by.filter(uuid=request.user.uuid).exists()
        is_editor = obj.can_be_edited_by.filter(uuid=request.user.uuid).exists()

        if view.action == "get_excel":
            return True

        if (is_viewer or is_editor) and view.action == "retrieve":
            return True
        if is_editor and view.action in ["update", "partial_update"]:
            return True

        return super().has_object_permission(request, view, obj)


class TableDataSeriesPermissions(BaseModelAccessPermissions):
    model_name = "TableDataSeries"

    def has_object_permission(self, request, view, obj):
        if view.action == "get_data":
            company_id = self.get_company_id("list", request, obj)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            return view.permissions.has_permission(permission="can_view")

        return super().has_object_permission(request, view, obj)


class InstrumentMapPermissions(BaseModelAccessPermissions):
    model_name = "InstrumentMap"


class SIHMonitoringPointMapPermissions(BaseModelAccessPermissions):
    model_name = "SIHMonitoringPointMap"
