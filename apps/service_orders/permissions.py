import uuid

from rest_framework_json_api import serializers

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Company
from apps.reportings.models import Reporting
from apps.resources.models import Contract, Resource
from apps.users.models import User
from helpers.permissions import BaseModelAccessPermissions, PermissionManager
from helpers.strings import is_valid_uuid

from .const import kind_types
from .models import (
    Procedure,
    ProcedureResource,
    ServiceOrder,
    ServiceOrderAction,
    ServiceOrderResource,
)


def can_edit_service_order(obj, user, user_permissions, model_name, user_entity):
    if obj.is_closed:
        return "Não é possível alterar um Serviço fechado"

    if user in obj.responsibles.all():
        return True

    permissions = user_permissions.get_model_permission(model_name)
    if permissions and "can_edit" in permissions:
        level = permissions["can_edit"]
    else:
        return "Permissão não encontrada"

    levels = []
    for item in level:
        if item == "entity":
            if obj.entity and obj.entity.uuid not in user_entity:
                return "Não é possível alterar um Serviço de outra entidade"
            else:
                levels.append(True)
        else:
            levels.append(item)
    return any(levels)


def can_create_or_edit_action(
    service_order, user, user_permissions, model_name, action, user_entity
):
    if user in service_order.responsibles.all() or user in service_order.managers.all():
        return True

    error_string_action = "criar" if action == "can_create" else "editar"

    if service_order.is_closed:
        return "Não é possível {} entregas em um Serviço fechado".format(
            error_string_action
        )

    permissions = user_permissions.get_model_permission(model_name)
    if permissions and action in permissions:
        level = permissions[action]
    else:
        return "Permissão não encontrada"

    levels = []
    for item in level:
        if item == "entity":
            if service_order.entity and service_order.entity.uuid not in user_entity:
                return (
                    "Não é possível {} entregas em um Serviço de outra entidade".format(
                        error_string_action
                    )
                )
            else:
                levels.append(True)
        else:
            levels.append(item)
    return any(levels)


class ServiceOrderPermissions(BaseModelAccessPermissions):
    model_name = "ServiceOrder"

    def has_permission(self, request, view):
        if view.action == "pending_procedures":
            company_id = self.get_company_id("list", request)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            return view.permissions.has_permission(
                permission="can_view_pending_procedures"
            )

        return super(ServiceOrderPermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if request.method in ["HEAD", "OPTIONS"]:
            return True

        if view.action in [
            "pdf_service_order",
        ]:
            view.action = "retrieve"

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
            user_entity = request.user.user_firms.values_list("entity__uuid", flat=True)

            permission = can_edit_service_order(
                obj,
                request.user,
                view.permissions,
                self.model_name,
                user_entity,
            )

            if isinstance(permission, str):
                raise serializers.ValidationError(permission)
            else:
                return permission

        else:
            return False


class ServiceOrderActionStatusPermissions(BaseModelAccessPermissions):
    model_name = "ServiceOrderActionStatus"

    def has_permission(self, request, view):
        if view.action == "create" and request.method == "POST" and request.data:
            if "companies" not in request.data:
                return False

            if isinstance(request.data["companies"], list):
                companies_list = request.data["companies"]
            else:
                companies_list = [request.data["companies"]]

            company_ids = []
            for company in companies_list:
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
            return super(ServiceOrderActionStatusPermissions, self).has_permission(
                request, view
            )

    def has_object_permission(self, request, view, obj):
        if request.method in ["HEAD", "OPTIONS"]:
            return any(i in obj.companies.all() for i in request.user.companies.all())

        if not view.permissions:
            view.permissions = PermissionManager(
                user=request.user,
                company_ids=obj.companies.all(),
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


class ServiceOrderActionStatusSpecsPermissions(BaseModelAccessPermissions):
    model_name = "ServiceOrderActionStatusSpecs"


class AdditionalControlPermissions(BaseModelAccessPermissions):
    model_name = "AdditionalControl"


class ActionChildPermissions(BaseModelAccessPermissions):
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
                action = ServiceOrderAction.objects.get(
                    pk=uuid.UUID(request.data["action"]["id"])
                )
            except Exception as e:
                print(e)
                return False
            if not action.service_order.is_closed:
                return action.service_order.company_id
            else:
                raise serializers.ValidationError(
                    "Não é possível criar um elemento associado à uma ordem de serviço que já foi encerrada"
                )

        elif action in ["update", "partial_update", "destroy"]:
            if not obj.action.service_order.is_closed:
                return obj.action.service_order.company_id
            else:
                raise serializers.ValidationError(
                    "Não é possível criar um elemento associado à uma ordem de serviço que já foi encerrada"
                )

        else:
            return False


class ProcedurePermissions(ActionChildPermissions):
    model_name = "Procedure"

    def has_object_permission(self, request, view, obj):
        if view.action in ["send_judiciary_email"]:
            company = self.get_company_id("retrieve", request, obj)
            if not company:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company,
                    model=self.model_name,
                )

            return view.permissions.has_permission(permission="can_view")
        else:
            return super().has_object_permission(request, view, obj)


class ServiceOrderChildPermissions(BaseModelAccessPermissions):
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
                service_order = ServiceOrder.objects.get(
                    pk=uuid.UUID(request.data["service_order"]["id"])
                )
            except Exception as e:
                print(e)
                return False
            if not service_order.is_closed:
                return service_order.company_id
            else:
                raise serializers.ValidationError(
                    "Não é possível criar um elemento associado à uma ordem de serviço que já foi encerrada"
                )

        elif action in ["update", "partial_update", "destroy"]:
            if not obj.service_order.is_closed:
                return obj.service_order.company_id
            else:
                raise serializers.ValidationError(
                    "Não é possível atualizar um elemento associado à uma ordem de serviço que já foi encerrada"
                )

        else:
            return False


class ServiceOrderActionPermissions(ServiceOrderChildPermissions):
    model_name = "ServiceOrderAction"

    def has_permission(self, request, view):
        if view.action == "create" and request.method == "POST":
            company_id = self.get_company_id("create", request)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            service_order_id = request.data["service_order"]["id"]
            try:
                service_order = ServiceOrder.objects.get(uuid=service_order_id)
            except Exception as e:
                print(e)
                return False

            if request.data["allow_forwarding"] is True:
                if service_order.kind != kind_types.LAND:
                    raise serializers.ValidationError(
                        "kartado.error.service_order_kind_is_not_land"
                    )

            user_entity = request.user.user_firms.values_list("entity__uuid", flat=True)

            permission = can_create_or_edit_action(
                service_order,
                request.user,
                view.permissions,
                self.model_name,
                "can_create",
                user_entity,
            )

            if isinstance(permission, str):
                raise serializers.ValidationError(permission)
            else:
                return permission

        return super(ServiceOrderActionPermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if view.action in [
            "pdf_service_order_action",
            "service_order_check_data_email_judiciary",
        ]:
            company = self.get_company_id("retrieve", request, obj)
            if not company:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company,
                    model=self.model_name,
                )

            return view.permissions.has_permission(permission="can_view")

        else:
            return super(ServiceOrderActionPermissions, self).has_object_permission(
                request, view, obj
            )


class ServiceOrderWatcherPermissions(ServiceOrderChildPermissions):
    model_name = "ServiceOrderWatcher"


class MeasurementBulletinPermissions(BaseModelAccessPermissions):
    model_name = "MeasurementBulletin"

    def get_company_id(self, action, request, obj=None):
        def verify_data(contract):
            if contract.firm:
                if contract.firm.company:
                    return contract.firm.company_id
            elif contract.subcompany:
                if contract.subcompany.company:
                    return contract.subcompany.company_id
            else:
                return False

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
                contract = Contract.objects.get(
                    pk=uuid.UUID(request.data["contract"]["id"])
                )
            except Exception as e:
                print(e)
                return False
            return verify_data(contract)

        elif action in ["update", "partial_update", "destroy"]:
            contract = obj.contract
            if not contract:
                return False

            return verify_data(contract)

        else:
            return False

    def has_object_permission(self, request, view, obj):
        if request.method in ["HEAD", "OPTIONS"]:
            return True

        if view.action in [
            "pdf_measurement_bulletin",
            "summary_measurement_bulletin",
            "preview",
        ]:
            company = self.get_company_id("retrieve", request, obj)
            if not company:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company,
                    model=self.model_name,
                )

            return view.permissions.has_permission(permission="can_view")

        if view.action == "approval" and request.method == "POST":
            company_id = self.get_company_id("update", request, obj)
            if not company_id:
                return False

            if not obj.approval_step:
                return False

            if not obj.contract:
                return False

            responsible = []
            if obj.approval_step.responsible_created_by:
                responsible.append(obj.created_by)

            for user in obj.approval_step.responsible_users.all():
                responsible.append(user)

            for firm in obj.approval_step.responsible_firms.all():
                if firm.manager:
                    responsible.append(firm.manager)
                for user in firm.users.all():
                    responsible.append(user)

            if len(responsible) and request.user not in responsible:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )
            return view.permissions.has_permission(permission="can_approve")

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
            if view.permissions.has_permission(permission="can_delete"):
                usage_count = ProcedureResource.objects.filter(
                    service_order_resource=obj.uuid
                ).count()
                if usage_count == 0:
                    return True
                else:
                    raise serializers.ValidationError(
                        "Não é possível desprovisionar um recurso que já foi utilizado"
                    )

        elif view.action in ["update", "partial_update"]:
            if view.permissions.has_permission(permission="can_edit"):
                if "amount" in request.data:
                    if obj.amount - request.data["amount"] <= obj.remaining_amount:
                        return True
                    else:
                        raise serializers.ValidationError(
                            "A nova quantidade provisionada é menor que a quantidade já utilizada"
                        )
                else:
                    return True

        else:
            return False


class AdministrativeInformationPermissions(ServiceOrderChildPermissions):
    model_name = "AdministrativeInformation"


class ServiceOrderResourcePermissions(BaseModelAccessPermissions):
    model_name = "ServiceOrderResource"

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
            resource = Resource.objects.get(
                pk=uuid.UUID(request.data["resource"]["id"])
            )
            return resource.company_id

        elif action in ["update", "partial_update", "destroy"]:
            return obj.resource.company_id

        else:
            return False

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
            if view.permissions.has_permission(permission="can_delete"):
                usage_count = ProcedureResource.objects.filter(
                    service_order_resource=obj.uuid
                ).count()
                if usage_count == 0:
                    return True
                else:
                    raise serializers.ValidationError(
                        "Não é possível desprovisionar um recurso que já foi utilizado"
                    )

        elif view.action in ["update", "partial_update"]:
            if view.permissions.has_permission(permission="can_edit"):
                if "amount" in request.data:
                    if obj.amount - request.data["amount"] <= obj.remaining_amount:
                        return True
                    else:
                        raise serializers.ValidationError(
                            "A nova quantidade provisionada é menor que a quantidade já utilizada"
                        )
                else:
                    return True

        else:
            return False


class ProcedureFlowPermissions(ProcedurePermissions):
    def has_permission(self, request, view):
        if view.action == "create":
            company_id = self.get_company_id(view.action, request)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            if "service_order_action_status" in request.data.keys():
                service_order_action_uuid = uuid.UUID(request.data["action"]["id"])
                try:
                    latest_procedure = Procedure.objects.filter(
                        service_order_action_status__isnull=False,
                        action=service_order_action_uuid,
                    ).latest()
                except Procedure.DoesNotExist:
                    latest_procedure = None

                try:
                    service_order = ServiceOrder.objects.get(
                        actions__uuid=service_order_action_uuid
                    )
                    if (
                        request.user in service_order.managers.all()
                        or request.user in service_order.responsibles.all()
                    ):
                        return True
                except ServiceOrder.DoesNotExist:
                    pass

                allowed_queryset = view.permissions.get_allowed_queryset()

                if view.permissions.has_permission(permission="can_create"):
                    is_user_responsible = ("self" in allowed_queryset) and (
                        latest_procedure
                        and latest_procedure.responsible == request.user
                    )

                    is_responsible_in_user_firms = False
                    # Check firm before do any query
                    if "firm" in allowed_queryset:
                        user_firms = request.user.user_firms.all()
                        firms_members = User.objects.filter(
                            user_firms__in=user_firms
                        ).distinct()
                        is_responsible_in_user_firms = (latest_procedure) and (
                            latest_procedure.responsible in firms_members
                        )

                    if (
                        ("all" in allowed_queryset)
                        or is_user_responsible
                        or is_responsible_in_user_firms
                    ):
                        if latest_procedure:
                            return view.permissions.has_flow_permission(
                                permission="allowed_status_transitions",
                                origin_status=str(
                                    latest_procedure.service_order_action_status.uuid
                                ),
                                final_status=request.data[
                                    "service_order_action_status"
                                ]["id"],
                            )
                        else:
                            return True
                    else:
                        return False
                else:
                    return False

        return True

    def has_object_permission(self, request, view, obj):
        return True


class ProcedureChildPermissions(BaseModelAccessPermissions):
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
                if hasattr(request, "data"):
                    if "procedure" in request.data:
                        procedure = Procedure.objects.get(
                            pk=uuid.UUID(request.data["procedure"]["id"])
                        )
                    elif "procedures" in request.data:
                        procedure = Procedure.objects.get(
                            pk=uuid.UUID(request.data["procedures"][0]["id"])
                        )
            except Exception as e:
                print(e)
                return False
            if not procedure.action.service_order.is_closed:
                return procedure.action.service_order.company_id
            else:
                raise serializers.ValidationError(
                    "Não é possível criar um elemento associado à uma ordem de serviço que já foi encerrada"
                )

        elif action in ["update", "partial_update", "destroy"]:
            if not obj.procedures.first().action.service_order.is_closed:
                return obj.procedures.first().action.service_order.company_id
            else:
                raise serializers.ValidationError(
                    "Não é possível atualizar um elemento associado à uma ordem de serviço que já foi encerrada"
                )

        else:
            return False


class ProcedureFilePermissions(ProcedureChildPermissions):
    model_name = "ProcedureFile"

    def has_object_permission(self, request, view, obj):
        if view.action == "check":
            view.action = "retrieve"

        return super(ProcedureFilePermissions, self).has_object_permission(
            request, view, obj
        )


class ProcedureResourcePermissions(ServiceOrderChildPermissions):
    model_name = "ProcedureResource"

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
                    raise serializers.ValidationError(
                        "kartado.error.reporting.not_found"
                    )
                except Exception as e:
                    print(e)
                    return False

                if not reporting.editable:
                    raise serializers.ValidationError(
                        "kartado.error.reporting.not_editable"
                    )

            # if a service_order is provided, we can fall back to the parent's method
            if "service_order" not in request.data and "procedure" in request.data:
                # however, if only a procedure is provided, fill the service_order field, then
                # use the parent's method
                try:
                    procedure = Procedure.objects.get(
                        pk=request.data["procedure"]["id"]
                    )
                except Exception:
                    return False
                request.data["service_order"] = {
                    "type": "ServiceOrder",
                    "id": str(procedure.action.service_order.uuid),
                }

            elif "service_order_resource" in request.data:
                # if there is no service_order nor procedure provided, use the information from
                # the service_order_resource. this is the case for roads customers that don't
                # use the ServiceOrder module
                try:
                    service_order_resource = ServiceOrderResource.objects.get(
                        pk=uuid.UUID(request.data["service_order_resource"]["id"])
                    )
                except Exception as e:
                    print(e)
                    return False
                return service_order_resource.resource.company_id

        elif action in ["update", "partial_update", "destroy", "approval"]:
            # check if reporting is editable
            if obj.reporting and not obj.reporting.editable and action != "approval":
                raise serializers.ValidationError(
                    "kartado.error.reporting.not_editable"
                )

            # for customers that use the ServiceOrder module, check if it has been closed
            if obj.service_order:
                if not obj.service_order.is_closed:
                    return obj.service_order.company_id
                else:
                    raise serializers.ValidationError(
                        "Não é possível atualizar um elemento associado à uma ordem de serviço que já foi encerrada"
                    )
            # otherwise, just return the company_id from the associated Resource
            return obj.service_order_resource.resource.company_id

        # for other methods, fall back to the parent's method
        return super(ProcedureResourcePermissions, self).get_company_id(
            action, request, obj
        )

    def has_permission(self, request, view):
        if view.action == "bulk_approval" and request.method == "POST":
            try:
                first_resource = ProcedureResource.objects.get(
                    pk=request.data["procedure_resources"][0]["id"]
                )
            except Exception:
                raise serializers.ValidationError(
                    "É necessário especificar ao menos um Resource"
                )

            if first_resource.service_order:
                company_id = first_resource.service_order.company_id
            else:
                company_id = first_resource.service_order_resource.resource.company_id

            if not company_id:
                return False

            try:
                company = Company.objects.get(pk=company_id)
            except Exception:
                return False

            # for customers that use the ServiceOrder module, check they are closed
            resource_ids_list = [
                resource["id"] for resource in request.data["procedure_resources"]
            ]
            if any(
                ServiceOrder.objects.filter(
                    resources_service_order__uuid__in=resource_ids_list
                ).values_list("is_closed", flat=True)
            ):
                raise serializers.ValidationError(
                    "Não é possível atualizar um elemento associado à uma ordem de serviço que já foi encerrada"
                )

            if "approved_approval_steps" in company.metadata:
                steps_ids = (
                    ApprovalStep.objects.filter(
                        step_reportings__reporting_resources__uuid__in=resource_ids_list
                    )
                    .distinct()
                    .values_list("uuid", flat=True)
                )
                steps_ids_list = [str(item) for item in steps_ids]
                metadata_steps_ids = company.metadata["approved_approval_steps"]
                if any(elem not in metadata_steps_ids for elem in steps_ids_list):
                    raise serializers.ValidationError(
                        "O apontamento associado não foi aprovado"
                    )

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            is_contract_responsible = (
                request.user.uuid
                in first_resource.service_order_resource.contract.responsibles_hirer.values_list(
                    "uuid", flat=True
                )
            )

            return (
                view.permissions.has_permission(permission="can_approve")
                and is_contract_responsible
            )
        if view.action == "procedure_resource_export":
            view.action = "list"
        return super(ProcedureResourcePermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if view.action == "approval" and request.method == "POST":
            company_id = self.get_company_id(view.action, None, obj)
            try:
                company = Company.objects.get(pk=company_id)
            except Exception:
                return False

            if (
                obj.reporting
                and obj.reporting.approval_step
                and "approved_approval_steps" in company.metadata
            ):
                steps_ids = company.metadata["approved_approval_steps"]
                if str(obj.reporting.approval_step.pk) not in steps_ids:
                    raise serializers.ValidationError(
                        "O apontamento associado não foi aprovado"
                    )

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            is_contract_responsible = (
                request.user.uuid
                in obj.service_order_resource.contract.responsibles_hirer.values_list(
                    "uuid", flat=True
                )
            )

            return (
                view.permissions.has_permission(permission="can_approve")
                and is_contract_responsible
            )

        elif view.action == "destroy":
            company_id = self.get_company_id(view.action, request, obj)
            if not company_id:
                return False

            if not view.permissions:
                view.permissions = PermissionManager(
                    user=request.user,
                    company_ids=company_id,
                    model=self.model_name,
                )

            if view.permissions.has_permission(permission="can_delete"):
                if not (obj.approval_status == "APPROVED_APPROVAL"):
                    return True
                else:
                    raise serializers.ValidationError(
                        "Somente pode ser deletado se não for aprovado"
                    )

        else:
            return super(ProcedureResourcePermissions, self).has_object_permission(
                request, view, obj
            )


class PendingProceduresExportPermissions(BaseModelAccessPermissions):
    model_name = "PendingProceduresExport"

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

            return view.permissions.has_permission(permission="can_create")

        else:
            return super(PendingProceduresExportPermissions, self).has_permission(
                request, view
            )

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
