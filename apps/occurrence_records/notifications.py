from django.conf import settings
from django.db.models import Q
from zappa.asynchronous import task

from apps.users.models import User
from helpers.apps.approval_flow import get_user_notif_of_approval_responsibles
from helpers.apps.todo import generate_todo
from helpers.apps.users import add_debounce_data
from helpers.notifications import create_notifications

from .models import OccurrenceRecord


@task
def occurrence_record_approval(uuid: str):
    """
    Notify OccurrenceRecord approval change

    Does not group results of multiple Company instances.
    """

    NOTIFICATION_AREA = "registros.alteracao_de_status"

    # Check is_not_notified flag
    instance = OccurrenceRecord.objects.get(uuid=uuid)
    if (
        instance.occurrence_type
        and instance.occurrence_type.occurrencetype_specs.filter(
            company=instance.company, is_not_notified=True
        ).exists()
    ) or (instance.monitoring_plan and instance.monitoring_plan.is_not_notified):
        return

    user_notifs = get_user_notif_of_approval_responsibles(instance, NOTIFICATION_AREA)

    if user_notifs:
        # Create url
        url = "{}/#/SharedLink/OccurrenceRecord/{}/show?company={}".format(
            settings.FRONTEND_URL,
            str(instance.uuid),
            str(instance.company.uuid),
        )

        debounce_data = {
            "number": instance.number,
            "status": instance.status.name,
            "company_id": str(instance.company.pk),
            "url": url,
        }

        # NOTE: user_notifs was already deduped with .distinct() on get_user_notif_of_approval_responsibles
        add_debounce_data(user_notifs, debounce_data)


def average_flow(instance, water_meter, water_meter_uuid):
    # Check is_not_notified flag
    if (
        instance.occurrence_type
        and instance.occurrence_type.occurrencetype_specs.filter(
            company=instance.company, is_not_notified=True
        ).exists()
    ) or (instance.monitoring_plan and instance.monitoring_plan.is_not_notified):
        return

    water_meter_form_data = water_meter.form_data

    # Get meter basic info
    water_meter_name = water_meter_form_data.get("hydrometer_namer", "Sem Nome")

    # Get warning flags
    warn_average_flow = water_meter_form_data.get("warn_average_flow", False)
    warn_maximum_flow = water_meter_form_data.get("warn_maximum_flow", False)

    # Get limits
    daily_average_flow = water_meter_form_data.get("daily_average_flow_water", None)
    monthly_average_flow = water_meter_form_data.get("monthly_average_flow_water", None)
    daily_max_flow = water_meter_form_data.get("daily_max_flow_water", None)
    monthly_max_flow = water_meter_form_data.get("monthly_max_flow_water", None)

    # Any flag set?
    if warn_average_flow or warn_maximum_flow:
        # Get consumption records for that meter
        month_records = OccurrenceRecord.objects.filter(
            form_data__records=water_meter_uuid,
            datetime__date__month=instance.datetime.month,
            datetime__date__year=instance.datetime.year,
        )
        day_records = month_records.filter(datetime__date__day=instance.datetime.day)

        # Get daily and monthly quantities
        month_sum = sum(
            [record.form_data.get("quantity", 0) for record in month_records]
        )
        day_sum = sum([record.form_data.get("quantity", 0) for record in day_records])
        month_sum_minus_record = month_sum - instance.form_data.get("quantity", 0)
        day_sum_minus_record = day_sum - instance.form_data.get("quantity", 0)

        # Possible scenarios
        monthly_average_exceeded = (
            month_sum > monthly_average_flow if monthly_average_flow else False
        )
        monthly_max_exceeded = day_sum > monthly_max_flow if monthly_max_flow else False
        daily_average_exceeded = (
            day_sum > daily_average_flow if daily_average_flow else False
        )
        daily_max_exceeded = day_sum > daily_max_flow if daily_max_flow else False

        # Scenarios where limit was exceeded without the current instance
        monthly_average_already_exceeded = (
            month_sum_minus_record > monthly_average_flow
            if monthly_average_flow
            else False
        )
        monthly_max_already_exceeded = (
            month_sum_minus_record > monthly_max_flow if monthly_max_flow else False
        )
        daily_average_already_exceeded = (
            day_sum_minus_record > daily_average_flow if daily_average_flow else False
        )
        daily_max_already_exceeded = (
            day_sum_minus_record > daily_max_flow if daily_max_flow else False
        )

        # Determine recipients
        average_flow_users_uuids = water_meter_form_data.get(
            "warn_average_flow_users", []
        )
        average_flow_firms_uuids = water_meter_form_data.get(
            "warn_average_flow_firms", []
        )
        maximum_flow_users_uuids = water_meter_form_data.get(
            "warn_maximum_flow_users", []
        )
        maximum_flow_firms_uuids = water_meter_form_data.get(
            "warn_maximum_flow_firms", []
        )

        # Filter Users
        if warn_average_flow:
            average_flow_users = User.objects.filter(
                Q(uuid__in=average_flow_users_uuids)
                | Q(user_firms__in=average_flow_firms_uuids)
            ).distinct()
        if warn_maximum_flow:
            maximum_flow_users = User.objects.filter(
                Q(uuid__in=maximum_flow_users_uuids)
                | Q(user_firms__in=maximum_flow_firms_uuids)
            ).distinct()

        # Notification basic info
        url = "{}/#/SharedLink/OccurrenceRecord/{}/show?company={}".format(
            settings.FRONTEND_URL,
            str(instance.uuid),
            str(instance.company.uuid),
        )
        notification_args = {
            "company": instance.company,
            "template_path": "occurrence_records/email/flow_warning_email",
            "instance": instance,
            "url": url,
            "context": {"number": instance.number, "url": url},
        }
        title_template = water_meter_name + " antingiu nível {}"
        message_template = (
            "Seu limite {} de {} litros foi excedido na última leitura."
            " Para mais informações consultar '{}' no Controle Operacional de Hidrômetros"
        )

        # Notify in order of importance
        if (
            warn_maximum_flow
            and monthly_max_exceeded
            and not monthly_max_already_exceeded
        ):
            notification_args["send_to"] = maximum_flow_users
            warning_kind = "máximo mensal"
            title = title_template.format(warning_kind)
            message = message_template.format(
                warning_kind, monthly_max_flow, water_meter_name
            )
        elif (
            warn_maximum_flow and daily_max_exceeded and not daily_max_already_exceeded
        ):
            notification_args["send_to"] = maximum_flow_users
            warning_kind = "máximo diário"
            title = title_template.format(warning_kind)
            message = message_template.format(
                warning_kind, daily_max_flow, water_meter_name
            )
        elif (
            warn_average_flow
            and monthly_average_exceeded
            and not monthly_average_already_exceeded
        ):
            notification_args["send_to"] = average_flow_users
            warning_kind = "médio mensal"
            title = title_template.format(warning_kind)
            message = message_template.format(
                warning_kind, monthly_average_flow, water_meter_name
            )
        elif (
            warn_average_flow
            and daily_average_exceeded
            and not daily_average_already_exceeded
        ):
            notification_args["send_to"] = average_flow_users
            warning_kind = "médio diário"
            title = title_template.format(warning_kind)
            message = message_template.format(
                warning_kind, daily_average_flow, water_meter_name
            )
        else:
            return  # Nothing else to do

        notification_args["context"]["title"] = title
        notification_args["context"]["message"] = message

        create_notifications(**notification_args)


def get_description(instance):
    description = {}
    description["record"] = instance.number + ", "

    # Get search tags
    # Record
    description["record"] += instance.search_tags.get(level=1).name
    # Type
    if instance.search_tags.filter(level=2).exists():
        description["record"] += ", " + instance.search_tags.get(level=2).name
    # Nature
    if instance.search_tags.filter(level=3).exists():
        description["record"] += ", " + instance.search_tags.get(level=3).name
    # Subject
    if instance.search_tags.filter(level=4).exists():
        description["subject"] = instance.search_tags.get(level=4).name

    # Get location
    description["city"] = ""
    if instance.city:
        description["city"] += instance.city.name
    if instance.location:
        description["city"] += ", " + instance.location.name

    # Title
    description["additionalInformation"] = instance.search_tag_description

    # Status
    description["record_status"] = str(instance.status.uuid)

    return description


def occurrence_record_approval_todo(instance, request_user):
    try:
        # Get company
        company = instance.company

        # Get action, if has no action, return
        if instance.approval_step.action.exists():
            actions = instance.approval_step.action_steps.all()
        else:
            return

        responsibles = []
        notifieds = []
        creators = []
        send_to = {
            "responsible": responsibles,
            "notified": notifieds,
            "creator": creators,
        }

        # Get responsibles
        for user in instance.approval_step.responsible_users.all():
            responsibles.append(user)
        for firm in instance.approval_step.responsible_firms.all():
            responsibles.append(firm.manager)
            for user in firm.users.all():
                responsibles.append(user)
        if instance.approval_step.responsible_created_by:
            responsibles.append(instance.created_by)
        if instance.approval_step.responsible_firm_manager:
            responsibles.append(instance.firm.manager)
        if (
            instance.approval_step.responsible_firm_entity
            and instance.firm.entity
            and instance.firm.entity.approver_firm
        ):
            for user in instance.firm.entity.approver_firm.users.all():
                responsibles.append(user)

        # Get notifieds
        for watcher in instance.occurrencerecord_watchers.all():
            if watcher.user:
                notifieds.append(watcher.user)
            if watcher.firm:
                notifieds.append(firm.manager)
                for user in firm.users.all():
                    notifieds.append(user)

        # Get creators
        creators.append(instance.created_by)
        creators.append(instance.firm.manager)
        for user in instance.firm.users.all():
            creators.append(user)

        # Set is_done
        is_done = False

        # Get description
        description = get_description(instance)

        # Get url
        url = "{}/#/SharedLink/OccurrenceRecord/{}/show?company={}".format(
            settings.FRONTEND_URL,
            str(instance.uuid),
            str(instance.company.uuid),
        )

        # Set due_at
        due_at = None

        # Set creaeted_by
        created_by = request_user

        # Set independent_todos
        independent_todos = False

        # Set resource
        resource = instance

        for action in actions:
            if len(send_to[action.destinatary]):
                generate_todo(
                    company=company,
                    responsibles=send_to[action.destinatary],
                    action=action.todo_action,
                    is_done=is_done,
                    description=description,
                    url=url,
                    due_at=due_at,
                    created_by=created_by,
                    independent_todos=independent_todos,
                    resource=resource,
                )
    except Exception as e:
        print(e)
        pass
