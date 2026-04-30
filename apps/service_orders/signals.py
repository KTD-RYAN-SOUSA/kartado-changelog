from datetime import datetime

from django.conf import settings
from django.db.models.signals import (
    m2m_changed,
    post_delete,
    post_save,
    pre_delete,
    pre_save,
)
from django.dispatch import receiver
from fieldsignals.signals import post_save_changed, pre_save_changed
from rest_framework.exceptions import ValidationError

from apps.approval_flows.models import ApprovalTransition
from apps.companies.models import Firm
from apps.occurrence_records.notifications import get_description
from apps.service_orders.const import kind_types
from apps.service_orders.const.status_types import (
    ENVIRONMENTAL_SERVICE_PROGRESS,
    LAND_SERVICE_PROGRESS,
)
from apps.service_orders.models import (
    AdministrativeInformation,
    MeasurementBulletin,
    Procedure,
    ProcedureResource,
    ServiceOrder,
    ServiceOrderAction,
    ServiceOrderActionStatusSpecs,
    ServiceOrderResource,
)
from apps.to_dos.models import ToDo, ToDoAction, ToDoActionStep
from apps.users.models import User
from helpers.apps.contract_utils import get_spent_price, get_total_price
from helpers.apps.todo import (
    field_has_changed,
    generate_todo,
    handle_todos_procedure_resource,
    handle_todos_service_order_resource,
    mark_to_dos_as_read,
)
from helpers.middlewares import get_current_user
from helpers.signals import DisableSignals, disable_signal_for_loaddata
from helpers.strings import get_autonumber_array


@receiver(pre_save, sender=Procedure)
def fill_procedure_fields(sender, instance, **kwargs):
    if instance._state.adding:
        """
        If we are creating a new procedure whitout specifying procedure_previous,
        automatically links with latest procedure created, if it exists
        """
        try:
            qs = Procedure.objects.filter(action=instance.action)
            if qs.exists():
                instance.procedure_previous = qs.latest()
                if not instance.service_order_action_status:
                    instance.service_order_action_status = (
                        instance.procedure_previous.service_order_action_status
                    )
        except Exception as e:
            # TODO: Use specific exception
            print(e)
        """
        If procedure is routed to a Firm without specifying a person, routes to
        Firm manager
        """
        if instance.responsible is None and instance.firm is not None:
            instance.responsible = instance.firm.manager

        if not instance.created_by and not instance.procedure_previous:
            instance.created_by = instance.action.created_by


@receiver(post_save, sender=ServiceOrder)
@disable_signal_for_loaddata
def set_service_order_status(sender, instance, created, **kwargs):
    if created:
        if instance.kind in [kind_types.LAND, kind_types.ENVIRONMENT]:
            company = instance.company

            # Check whether the created service is of the PATRIMONIAL or ENVIRONMENTAL type,
            # and create it with an initial status based on the type of service.
            # The choice of initial status is in accordance with the lowest order created status.
            status_kind = None
            if instance.kind == kind_types.LAND:
                status_kind = LAND_SERVICE_PROGRESS
            elif instance.kind == kind_types.ENVIRONMENT:
                status_kind = ENVIRONMENTAL_SERVICE_PROGRESS

            status_spec = ServiceOrderActionStatusSpecs.objects.filter(
                company=company,
                status__kind=status_kind,
            ).order_by("order")

            if status_spec.exists():
                instance.status = status_spec.first().status
                instance.save()


@receiver(post_save, sender=Procedure)
def update_action_fields(sender, instance, created, **kwargs):
    if created:
        try:
            action = instance.action

            action.firm = instance.firm
            action.responsible = instance.responsible
            action.service_order_action_status = instance.service_order_action_status

            action.save()
        except Exception as e:
            print(e)
            pass


@receiver(pre_save, sender=Procedure)
def set_is_allow_forwarding(sender, instance, **kwargs):
    if instance.action.allow_forwarding and not instance.forward_to_judiciary:
        instance.forward_to_judiciary = True
    elif not instance.action.allow_forwarding and instance.forward_to_judiciary:
        instance.forward_to_judiciary = False


@receiver(post_save, sender=ServiceOrderAction)
def record_actions_done(sender, instance, created, **kwargs):
    try:
        if created:
            pass
        else:
            # Check if there is a record to be solved
            if instance.parent_record:
                # Check if still some action to be executed on this record
                record_completed_actions = [
                    1
                    for action in instance.parent_record.record_actions.all()
                    if (action.service_order_action_status.is_final is False)
                ]
                # If all actions to be executed on this record are done
                if len(record_completed_actions) < 1:
                    record = instance.parent_record
                    company = instance.service_order.company
                    description = get_description(record)
                    action_step = record.approval_step
                    todo_action = ToDoAction.objects.filter(
                        company_group=company.company_group,
                        action_steps__approval_step=action_step,
                        action_steps__destinatary="responsible",
                    ).first()

                    # Get responsibles
                    send_to = []
                    for user in action_step.responsible_users.all():
                        send_to.append(user)
                    for firm in action_step.responsible_firms.all():
                        send_to.append(firm.manager)
                        for user in firm.users.all():
                            send_to.append(user)
                    if action_step.responsible_created_by:
                        send_to.append(record.created_by)
                    if action_step.responsible_firm_manager:
                        send_to.append(record.firm.manager)
                    if action_step.responsible_firm_entity:
                        firm_entity = record.firm.entity.approver_firm
                        send_to.append(firm_entity.manager)
                        for user in firm_entity.users.all():
                            send_to.append(user)
                    # responsible_supervisor is only used for AccessRequests, so will not be used here
                    # Get url
                    url = "{}/#/SharedLink/OccurrenceRecord/{}/show?company={}".format(
                        settings.FRONTEND_URL,
                        str(record.uuid),
                        str(company.uuid),
                    )

                    # If there is responsibles, generate todos
                    send_to = set(send_to)
                    if len(send_to):
                        generate_todo(
                            company=company,
                            responsibles=send_to,
                            action=todo_action,
                            due_at=None,
                            is_done=False,
                            description=description,
                            url=url,
                            created_by=get_current_user(),
                            independent_todos=False,
                            resource=instance,
                        )
    except Exception as e:
        print(e)
        pass


@receiver(post_save, sender=Procedure)
def task_created_todo(sender, instance, created, **kwargs):
    try:
        if instance.service_order_action_status.is_final:
            action = ToDoAction.objects.get(
                company_group=instance.action.service_order.company.company_group,
                default_options="see",
            )

            service_order = instance.action.service_order
            # Get send_to
            send_to = []
            # Add managers
            for user in service_order.managers.all():
                send_to.append(user)
            # Add responsibles
            for user in service_order.responsibles.all():
                send_to.append(user)

            # Due at is none, cause is the final status
            due_at = None
            independent_todos = False

        else:
            action = ToDoAction.objects.get(
                company_group=instance.action.service_order.company.company_group,
                name=instance.service_order_action_status.name,
            )

            # Get send_to
            send_to = []
            if instance.responsible:
                send_to.append(instance.responsible)
            else:
                firm = instance.firm
                send_to.append(firm.manager)

            due_at = instance.deadline
            independent_todos = True

        description = {}
        description["service"] = instance.action.service_order.number
        description["description"] = instance.action.service_order.description
        description["action"] = instance.action.name
        description["procedure"] = instance.to_do
        description["procedure_status"] = str(instance.service_order_action_status.name)

        # Create url
        url = "{}/#/SharedLink/Procedure/{}/show?company={}".format(
            settings.FRONTEND_URL,
            str(instance.uuid),
            str(instance.action.service_order.company.uuid),
        )
        send_to = set(send_to)
        # If there is responsibles, generate todos
        if len(send_to):
            generate_todo(
                company=instance.action.service_order.company,
                responsibles=send_to,
                action=action,
                due_at=due_at,
                is_done=False,
                description=description,
                url=url,
                created_by=get_current_user(),
                independent_todos=independent_todos,
                resource=instance,
            )
    except Exception as e:
        print(e)
        pass


@receiver(pre_save, sender=ProcedureResource)
@disable_signal_for_loaddata
def auto_fill_procedure_resource(sender, instance, **kwargs):
    """
    Auto fill Firm field.
    Auto fill ServiceOrder field when a Procedure is filled on ProcedureResource.
    The ServiceOrder must be set with that Procedure ServiceOrder.
    """
    if instance.firm is None:
        instance.firm = instance.service_order_resource.contract.firm

    if instance.procedure:
        instance.service_order = instance.procedure.action.service_order


@receiver(pre_save_changed, sender=ProcedureResource)
def save_field_after_approval_changes(sender, instance, changed_fields, **kwargs):
    try:
        if not instance._state.adding:
            for field, (old, new) in changed_fields.items():
                if field == "total_price" and instance.measurement_bulletin:
                    instance.total_price = old
                if (
                    field == "total_price"
                    and not instance.measurement_bulletin
                    and instance.approval_status == "WAITING_APPROVAL"
                ):
                    instance.service_order_resource.used_price -= old
                    instance.service_order_resource.used_price += new
                if field == "measurement_bulletin":
                    if instance.measurement_bulletin:
                        instance.service_order_resource.remaining_amount -= (
                            instance.amount
                        )
                        instance.service_order_resource.used_price += (
                            instance.total_price
                        )
                    else:
                        instance.service_order_resource.remaining_amount += (
                            instance.amount
                        )
                        instance.service_order_resource.used_price -= (
                            instance.total_price
                        )
            with DisableSignals(disabled_signals=[post_save, pre_save]):
                instance.service_order_resource.save()
    except Exception as e:
        # TODO: Use specific exception
        print(e)


@receiver(pre_save, sender=ServiceOrderResource)
def auto_fill_service_order_resource(sender, instance, **kwargs):
    if instance._state.adding:
        instance.remaining_amount = instance.amount


@receiver(post_save, sender=ProcedureResource)
def generate_resource_usage_todo_and_fill_contract_prices(
    sender, instance, created, **kwargs
):
    handle_todos_procedure_resource(str(instance.uuid), created)
    # instance_has_measurement_bulletin = instance.measurement_bulletin is not None
    # if not instance_has_measurement_bulletin:
    #     try:
    #         if not instance._state.adding:
    #             contract = instance.service_order_resource.contract
    #             prefetch_related_objects(
    #                 [contract],
    #                 "firm",
    #                 "subcompany",
    #                 "firm__company",
    #                 "subcompany__company",
    #                 "resources",
    #                 "resources__serviceorderresource_procedures",
    #                 "resources__serviceorderresource_procedures__measurement_bulletin",
    #                 "bulletins",
    #                 "performance_services",
    #             )
    #             contract.total_price = get_total_price(contract)
    #             contract.spent_price = get_spent_price(contract)
    #             with DisableSignals():
    #                 contract.save()
    #     except Exception as e:
    #         print(e)
    #         pass


@receiver(post_save, sender=ServiceOrderResource)
def generate_contract_resource_todos(sender, instance, created, **kwargs):
    handle_todos_service_order_resource(str(instance.uuid))


def generate_so_todos(sender, instance, remove_message, add_message, kwargs):
    try:
        if (kwargs["action"] == "post_remove") or (kwargs["action"] == "post_add"):
            # try:
            service_order = ServiceOrder.objects.get(pk=instance.pk)
            send_to = []
            # Get service_order responsibles and fill send_to
            if len(kwargs["pk_set"]):
                for pk in kwargs["pk_set"]:
                    send_to.append(User.objects.get(pk=pk))
            # Get view to do action
            action = ToDoAction.objects.get(
                default_options="see",
                company_group=service_order.company.company_group,
            )

            # Set description
            description = {}
            description["service"] = service_order.number
            description["description"] = service_order.description
            if kwargs["action"] == "post_remove":
                description["activity"] = remove_message
            elif kwargs["action"] == "post_add":
                description["activity"] = add_message

            # Create url
            url = "{}/#/SharedLink/ServiceOrder/{}/show?company={}".format(
                settings.FRONTEND_URL,
                str(service_order.uuid),
                str(service_order.company.uuid),
            )

            send_to = set(send_to)
            # If there is responsibles, generate todos
            if len(send_to):
                generate_todo(
                    company=service_order.company,
                    responsibles=send_to,
                    action=action,
                    is_done=False,
                    description=description,
                    url=url,
                    created_by=get_current_user(),
                    independent_todos=True,
                    resource=instance,
                )
    except Exception as e:
        print(e)
        pass


@receiver(m2m_changed, sender=ServiceOrder.responsibles.through)
def generate_so_responsible_todos(sender, instance, **kwargs):
    generate_so_todos(
        sender,
        instance,
        "kartado.info.service_order.no_longer_responsible",
        "kartado.info.service_order.now_responsible",
        kwargs,
    )


@receiver(m2m_changed, sender=ServiceOrder.managers.through)
def generate_so_managers_todos(sender, instance, **kwargs):
    generate_so_todos(
        sender,
        instance,
        "kartado.info.service_order.no_longer_manager",
        "kartado.info.service_order.now_manager",
        kwargs,
    )


@receiver(pre_save, sender=MeasurementBulletin)
def auto_add_bm_number(sender, instance, **kwargs):
    if instance.number in [None, ""]:
        instance_type = "BM"
        key_name = "{}_name_format".format(instance_type)
        # Get datetime and serial arrays
        company = (
            instance.firm.company
            if instance.firm
            else instance.contract.subcompany.company
        )
        data = get_autonumber_array(company.uuid, instance_type)
        # Get company prefix
        if "company_prefix" in company.metadata:
            data["prefixo"] = company.metadata["company_prefix"]
        else:
            data["prefixo"] = "[{}]".format(company.name)
        # Make number
        try:
            if key_name in company.metadata:
                number = company.metadata[key_name].format(**data)
            else:
                raise Exception("Variáveis de nome inválidas!")
        except Exception as e:
            print(e)
            # Fallback
            # UHIT-RG-2018.0001
            number = "{prefixo}-{nome}-{anoCompleto}.{serialAno}".format(**data)

        instance.number = number


@receiver(post_save, sender=AdministrativeInformation)
def update_measurement_bulletins(sender, instance, created, **kwargs):
    if created:
        try:
            MeasurementBulletin.objects.filter(
                firm=instance.firm,
                contract__service_orders=instance.service_order,
            ).select_related("administrative_information_bulletins").update(
                administrative_information=instance
            )
        except Exception as e:
            print(e)
            pass


def generate_measurement_bulletins_todos(instance):
    try:
        if (
            MeasurementBulletin.objects.filter(uuid=instance.uuid).exists()
            and not ToDo.objects.filter(
                resource_obj_id=instance.uuid, is_done=False
            ).exists()
        ):
            approval_step = instance.approval_step
            contract = instance.contract
            company = None
            if contract.firm:
                company = contract.firm.company
            elif contract.subcompany:
                company = contract.subcompany.company
            action_step = ToDoActionStep.objects.filter(
                approval_step=approval_step,
                todo_action__company_group=company.company_group,
            )
            if len(action_step):
                action_step = action_step.first()
                action = ToDoAction.objects.filter(
                    action_steps=action_step,
                    company_group=company.company_group,
                ).first()

                # If action destinatary are responsibles, we generate todo for hirers aprove
                send_to = []
                if action_step.destinatary == "responsible":
                    if contract.responsibles_hirer.exists():
                        for user in contract.responsibles_hirer.all():
                            send_to.append(user)
                    independent_todos = False
                # Else destinatary hired firm will only be notified.
                elif action_step.destinatary == "notified":
                    if contract.responsibles_hired.exists():
                        for user in contract.responsibles_hired.all():
                            send_to.append(user)
                    # Get firms that receive notification by e-mail when the approval_step changes
                    old_instance = MeasurementBulletin.objects.get(uuid=instance.uuid)
                    if ApprovalTransition.objects.filter(
                        origin=old_instance.approval_step,
                        destination=instance.approval_step,
                    ).exists():
                        transition = ApprovalTransition.objects.get(
                            origin=old_instance.approval_step,
                            destination=instance.approval_step,
                        )
                        notification_firms = transition.callback.get(
                            "measurement_bulletin_notification_firms", []
                        )
                        notification_firms = Firm.objects.filter(
                            uuid__in=notification_firms
                        )
                        for firm in notification_firms.all():
                            send_to.append(firm.manager)
                            for user in firm.users.all():
                                send_to.append(user)

                    independent_todos = True

                # Set the description
                description = {}
                if contract.name:
                    description["description"] = contract.name
                if contract.extra_info["r_c_number"]:
                    description["contract"] = contract.extra_info["r_c_number"]
                description["measurement_bulletin"] = instance.number
                description["approval_step_status"] = str(instance.approval_step.uuid)

                url = "{}/#/SharedLink/MeasurementBulletin/{}/show?company={}".format(
                    settings.FRONTEND_URL, str(instance.uuid), str(company.uuid)
                )
                send_to = set(send_to)
                # If there is someone to send, generate todos
                if len(send_to):
                    generate_todo(
                        company=company,
                        responsibles=send_to,
                        action=action,
                        is_done=False,
                        description=description,
                        url=url,
                        created_by=get_current_user(),
                        independent_todos=independent_todos,
                        resource=instance,
                    )
    except Exception as e:
        print(e)
        pass


@receiver(post_delete, sender=MeasurementBulletin)
def update_added_to_measurement_bulletin_by(sender, instance, **kwargs):
    for fs in instance.bulletin_surveys.all():
        fs.refresh_from_db()
        fs.save()


@receiver(post_save, sender=ServiceOrder)
def generate_so_conclusion_todo(sender, instance, created, **kwargs):
    try:
        if created:
            pass
        else:
            if instance.is_closed:
                send_to = []
                # Add managers
                for user in instance.managers.all():
                    send_to.append(user)
                # Add responsibles
                for user in instance.responsibles.all():
                    send_to.append(user)
                # Add watchers
                for watcher in instance.serviceorder_watchers.all():
                    if watcher.user:
                        send_to.append(watcher.user)
                    if watcher.firm:
                        send_to.append(watcher.firm.manager)
                        for user in watcher.firm.users.all():
                            send_to.append(user)

                # Get view to do action
                action = ToDoAction.objects.get(
                    default_options="see",
                    company_group=instance.company.company_group,
                )

                # Get description
                description = {}
                description["service"] = instance.number
                description["description"] = instance.description
                description["closed_description"] = instance.closed_description

                url = "{}/#/SharedLink/ServiceOrder/{}/show?company={}".format(
                    settings.FRONTEND_URL,
                    str(instance.uuid),
                    str(instance.company.uuid),
                )

                send_to = set(send_to)
                # If there is someone to send, generate todos
                if len(send_to):
                    generate_todo(
                        company=instance.company,
                        responsibles=send_to,
                        action=action,
                        is_done=False,
                        description=description,
                        url=url,
                        created_by=get_current_user(),
                        independent_todos=True,
                        resource=instance,
                    )
    except Exception as e:
        print(e)
        pass


@receiver(pre_save, sender=ServiceOrder)
def fill_service_order_fields(sender, instance, **kwargs):
    """
    Fill OS Number and OS opened_at date
    """

    company = instance.company

    if instance.number in [None, ""]:
        instance_type = "OS"
        key_name = "{}_name_format".format(instance_type)
        # Get datetime and serial arrays
        data = get_autonumber_array(company.uuid, instance_type)
        # Get company prefix
        data["prefixo"] = company.metadata.get(
            "company_prefix", "[{}]".format(company.name)
        )
        # Make number
        number = company.metadata.get(
            key_name, "{prefixo}-{nome}-{anoCompleto}.{serialAno}"
        ).format(**data)
        instance.number = number

    if not instance.opened_at:
        instance.opened_at = datetime.now()


@receiver(pre_delete, sender=AdministrativeInformation)
def delete_only_if_resources_have_not_been_consumed(sender, instance, **kwargs):
    """
    Don't allow deleting AdministrativeInformation when resources have already been consumed

    If there are any ProcedureResource in any Procedure of any ServiceOrderAction from ServiceOrder,
    where ServiceOrderResource is linked to the AdministrativeInformation Contract in question,
    this means that it was already consumed, and could not be deleted.
    """
    try:
        service_order_resources = instance.contract.resources.all()
        procedure_resources = ProcedureResource.objects.filter(
            service_order=instance.service_order,
            service_order_resource__in=service_order_resources,
        )
        if procedure_resources.exists():
            raise Exception()
    except Exception:
        raise ValidationError(
            "Não pode ser deletado se os recursos já foram consumidos."
        )


@receiver(post_save_changed, sender=MeasurementBulletin)
def check_mb_unread_todos(sender, instance, changed_fields, created, **kwargs):
    """
    Check if we have any ToDo that hasn't been marked as done,
    and if so, mark them as done
    Then, generate new ToDos according to new instance fields
    """
    if field_has_changed(changed_fields, "approval_step"):
        mark_to_dos_as_read(instance)

    generate_measurement_bulletins_todos(instance)


@receiver(post_save_changed, sender=ProcedureResource)
def check_pr_unread_todos(sender, instance, changed_fields, created, **kwargs):
    """
    Check if we have any ToDo that hasn't been marked as done,
    and if so, mark them as done
    """
    if field_has_changed(changed_fields, "approval_status"):
        mark_to_dos_as_read(instance)


@receiver(post_save_changed, sender=Procedure)
def check_procedure_unread_todos(sender, instance, changed_fields, created, **kwargs):
    """
    Check if we have any ToDo that hasn't been marked as done,
    and if so, mark them as done
    """
    if instance.procedure_previous:
        mark_to_dos_as_read(instance.procedure_previous)


@receiver(post_save_changed, sender=ServiceOrderResource)
def update_contract_values(sender, instance, changed_fields, created, **kwargs):
    if not instance._state.adding:
        change_flag = False
        for field, (old, new) in changed_fields.items():
            if field in ["unit_price", "amount"]:
                change_flag = True

        if change_flag:
            contract = instance.contract
            contract.total_price = get_total_price(contract)
            contract.spent_price = get_spent_price(contract)

            with DisableSignals():
                contract.save()
