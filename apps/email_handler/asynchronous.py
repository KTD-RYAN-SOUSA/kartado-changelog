import datetime
import locale
import logging
import time
from typing import Dict, Iterable, List

import psycopg2
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from apps.companies.models import Company
from apps.monitorings.models import MonitoringCycle
from apps.monitorings.notifications import monitoring_cycle_email
from apps.occurrence_records.models import OccurrenceRecord
from apps.resources.models import Contract
from apps.service_orders.models import (
    Procedure,
    ServiceOrder,
    ServiceOrderAction,
    ServiceOrderActionStatus,
    ServiceOrderWatcher,
)
from apps.users.const.notification_areas import VALID_NOTIFICATIONS
from apps.users.models import User, UserNotification
from helpers.apps.users import time_interval_to_label
from helpers.dates import is_first_work_day_month
from helpers.histories import bulk_update_with_history
from helpers.notifications import create_notifications
from helpers.strings import get_obj_from_path

from .models import EmailBlacklist, QueuedEmail, QueuedEmailEvent


def send_queued_emails():
    """
    Send queued emails


    This function is called on a 1 minute rate by AWS SQS
    """
    # Maximum number of emails to be processed on this call
    MAX_EMAILS = 10

    qs = QueuedEmail.objects.filter(
        sent=False, in_progress=False, cleared=True, error=False
    ).order_by("created_at")[:MAX_EMAILS]
    queue = list(qs)

    emails_blacklist = EmailBlacklist.objects.all().values_list("email", flat=True)

    # Set all of the selected emails for this call as in progress
    for email in qs:
        email.in_progress = True

    bulk_update_with_history(objs=qs, model=QueuedEmail, use_django_bulk=True)

    # Start trying to send the emails
    for email in queue:
        send_to_emails = []
        sender = "Notificacoes Kartado <notificacoes@kartado.com.br>"

        if email.send_anyway:
            for user in email.send_to_users.all():
                # If he has e-mail, add to send list
                if user.email and user.email not in emails_blacklist:
                    send_to_emails.append(user.email)
        else:
            for user in email.send_to_users.all():
                # Check if user wants to receive e-mail:
                if user.configuration:
                    if not user.configuration.get("send_email_notifications", False):
                        continue
                # If he has e-mail, add to send list
                if user.email and user.email not in emails_blacklist:
                    send_to_emails.append(user.email)

        if send_to_emails:
            try:
                msg = EmailMultiAlternatives(
                    email.title,
                    # message:
                    email.content_plain_text,
                    # from:
                    sender,
                    # to:
                    send_to_emails,
                    headers={
                        "X-SES-CONFIGURATION-SET": "SES-events",
                        "X-KARTADO-ID": email.uuid,
                        **email.custom_headers,
                    },
                )
                msg.encoding = "utf-8"
                if email.content_html:
                    msg.attach_alternative(email.content_html, "text/html")
                sent = msg.send()
            except Exception:
                email.error = True
            else:
                if sent:
                    email.sent = True
                else:
                    email.error = True
                    for address_email in send_to_emails:
                        try:
                            EmailBlacklist.objects.create(
                                email=address_email, reason=""
                            )
                        except Exception:
                            pass
        else:
            # no users have email
            email.sent = True

        # Email has finished being processed
        email.sent_at = datetime.datetime.now()
        email.in_progress = False

        # Update QueuedEmail
        email.save()


def manager_report_email():
    """
    An email notification with monthly metrics to send it to managers.
    Call it every day 1 of the month at 07:00.

    Does not group results of multiple Company instances.

    Does not follow the regular notification flow.
    """

    NOTIFICATION_AREA = "servicos.relatorio_gerencial"

    for company in Company.objects.all():
        if "report_email_firms" in company.metadata:
            # Selecting users which the email will be sent
            firms_ids = company.metadata["report_email_firms"]
            send_to = User.objects.filter(
                Q(user_notifications__notification=NOTIFICATION_AREA)
                & (Q(user_firms__in=firms_ids) | Q(user_firms_manager__in=firms_ids))
            ).distinct()

            # Find first day of last month (since this function will be called every day 1)
            today = datetime.date.today()
            last_day = today - datetime.timedelta(days=1)
            first_day_last_month = last_day.replace(day=1)
            # First day of the current year
            first_day_year = today.replace(month=1, day=1)

            # 1 - Records (Registros Movimentados em month/year):

            em_andamento = [
                "Registro em Elaboração",
                "Necessita Revisão",
                "Aguardando Homologação",
            ]
            homologados = ["Registro Deferido"]
            indeferidos = ["Registro Indeferido"]
            records_types = em_andamento + homologados + indeferidos

            possible_path = (
                "occurrenceType__fields__occurrenceKind__selectoptions__options"
            )
            options = get_obj_from_path(company.custom_options, possible_path)
            display_names = {item["value"]: item["name"] for item in options}

            records = OccurrenceRecord.objects.filter(
                company=company,
                created_at__gte=first_day_last_month,
                occurrence_type__isnull=False,
            ).select_related("occurrence_type", "status")

            records_in_year = OccurrenceRecord.objects.filter(
                company=company,
                created_at__gte=first_day_year,
                occurrence_type__isnull=False,
            ).select_related("occurrence_type")

            kinds = records.values_list(
                "occurrence_type__occurrence_kind", flat=True
            ).distinct()

            kinds_and_records = {
                kind: {
                    item["status__name"]: item["count"]
                    for item in records.filter(occurrence_type__occurrence_kind=kind)
                    .values("status__name")
                    .annotate(count=Count("status"))
                }
                for kind in kinds
            }

            records_dict = {}
            for key, value in kinds_and_records.items():
                records_dict[key] = {}
                for name in records_types:
                    records_dict[key][name] = value.get(name, 0)
                count = sum([b for a, b in value.items()])
                records_dict[key] = {
                    k: v for k, v in records_dict[key].items() if k in records_types
                }

                # Get total month
                records_dict[key]["total_month"] = count

                # Get most frequent type
                count_types = (
                    records.filter(occurrence_type__occurrence_kind=key)
                    .values("occurrence_type__name")
                    .annotate(count=Count("occurrence_type"))
                )
                max_value_type = count_types.aggregate(Max("count"))["count__max"]
                records_dict[key]["most_frequent"] = count_types.filter(
                    count=max_value_type
                )[0]["occurrence_type__name"]

                # Get total year
                records_dict[key]["total_year"] = records_in_year.filter(
                    occurrence_type__occurrence_kind=key
                ).count()

            records_final = []
            for key, value in records_dict.items():
                b = {}
                if key in display_names.keys():
                    b["natureza"] = display_names[key]
                    b["recorrente"] = value["most_frequent"]
                    b["total_month"] = value["total_month"]
                    b["total_anual"] = value["total_year"]
                    b["andamento"] = sum(
                        [d for c, d in value.items() if c in em_andamento]
                    )
                    b["homologados"] = sum(
                        [d for c, d in value.items() if c in homologados]
                    )
                    b["indeferidos"] = sum(
                        [d for c, d in value.items() if c in indeferidos]
                    )
                    records_final.append(b)

            # 2 - Services (Serviços Movimentados em month/year):

            services = (
                ServiceOrder.objects.filter(
                    Q(company=company)
                    & (
                        Q(updated_at__gte=first_day_last_month)
                        | Q(actions__procedures__created_at__gte=first_day_last_month)
                    )
                )
                .distinct()
                .prefetch_related("actions", "actions__procedures")
            )

            services_final = [
                {
                    "description": service.description,
                    "actions": ServiceOrderAction.objects.filter(
                        service_order=service,
                        opened_at__gte=first_day_last_month,
                    ).count(),
                    "creation_date": service.opened_at.strftime("%d/%m/%Y")
                    if service.opened_at
                    else "",
                    "late_procedures": Procedure.objects.filter(
                        action__service_order=service,
                        procedure_next__isnull=True,
                        deadline__lte=today,
                        service_order_action_status__is_final=False,
                    ).count(),
                    "concluded_actions": str(
                        round(
                            100
                            * ServiceOrderAction.objects.filter(
                                service_order=service,
                                service_order_action_status__is_final=True,
                            ).count()
                            / ServiceOrderAction.objects.filter(
                                service_order=service
                            ).count()
                        )
                    )
                    + " %"
                    if ServiceOrderAction.objects.filter(service_order=service).count()
                    else 0.0,
                    "concluded_procedures": Procedure.objects.filter(
                        action__service_order=service,
                        procedure_previous__isnull=False,
                        done_at__gte=first_day_last_month,
                    ).count(),
                }
                for service in services
                if service.description
            ]

            # 3 - Contracts (Recursos Vigentes em month/year):

            contracts = (
                Contract.objects.annotate(
                    total_remaining_amount=Sum("resources__remaining_amount")
                )
                .filter(
                    Q(firm__company=company)
                    & Q(contract_end__gte=first_day_last_month)
                    & (
                        Q(firm__is_company_team=False)
                        | Q(subcompany__subcompany_type="HIRED")
                    )
                )
                .exclude(total_remaining_amount=0)
                .prefetch_related(
                    "bulletins",
                    "resources",
                    "resources__serviceorderresource_procedures",
                )
            )

            contracts_final = [
                {
                    "description": contract.name,
                    "start_date": contract.contract_start.strftime("%d/%m/%Y"),
                    "end_date": contract.contract_end.strftime("%d/%m/%Y"),
                    "bulletins": contract.bulletins.count(),
                    "provisioned": contract.total_price,
                    "used": contract.spent_price,
                }
                for contract in contracts
            ]

            for item in contracts_final:
                locale.setlocale(locale.LC_MONETARY, "pt_BR.UTF-8")
                item["balance"] = "R$ " + locale.currency(
                    item["provisioned"] - item["used"],
                    grouping=True,
                    symbol=False,
                )
                item["provisioned"] = "R$ " + locale.currency(
                    item["provisioned"], grouping=True, symbol=False
                )
                item["used"] = "R$ " + locale.currency(
                    item["used"], grouping=True, symbol=False
                )

            # Get context
            title = "{}/{} do Kartado Energia - {}".format(
                first_day_last_month.month,
                first_day_last_month.year,
                company.name,
            )

            context = {
                "title": "Relatório Gerencial de " + title,
                "month": first_day_last_month.month,
                "year": first_day_last_month.year,
                "records": records_final,
                "services": services_final,
                "contracts": contracts_final,
                "company": company.name,
            }

            # Get templates path
            template_path = "email_handler/email/report_manager"

            # Create a email for each user
            if records_final or services_final or contracts_final:
                create_notifications(
                    send_to,
                    company,
                    context,
                    template_path,
                    push=False,
                    user_notification=NOTIFICATION_AREA,
                )


def get_service_report(
    status_concluded: ServiceOrderActionStatus,
    services: Iterable[ServiceOrder],
    first_day: datetime.datetime,
    today: datetime.datetime,
    company: Company,
) -> List[Dict[str, any]]:
    """
    Serialize the info needed for the services report regarding the provided
    services if that particular service has a description.

    Args:
        status_concluded (ServiceOrderActionStatus): The concluded status for that Company
        services (Iterable[ServiceOrder]): List of the services to be serialized
        first_day (datetime.datetime): First day to be considered on the query
        today (datetime.datetime): Current day reference for the query
        company (Company): Company needed for the url generation

    Returns:
        List[Dict[str, any]]: Serialized fields for the notification
    """

    services_final = [
        {
            "description": service.description,
            "actions": ServiceOrderAction.objects.filter(
                service_order=service, opened_at__date__gte=first_day
            ).count(),
            "creation_date": service.opened_at.strftime("%d/%m/%Y")
            if service.opened_at
            else "",
            "late_procedures": Procedure.objects.filter(
                action__service_order=service,
                procedure_next__isnull=True,
                deadline__lte=today,
                service_order_action_status__is_final=False,
            ).count(),
            "concluded_actions": (
                round(
                    100
                    * (
                        ServiceOrderAction.objects.filter(
                            service_order=service,
                            service_order_action_status_id__in=status_concluded,
                        ).count()
                        / ServiceOrderAction.objects.filter(
                            service_order=service
                        ).count()
                    ),
                    2,
                )
            )
            if ServiceOrderAction.objects.filter(service_order=service).exists()
            else 0.0,
            "concluded_procedures": Procedure.objects.filter(
                action__service_order=service,
                procedure_previous__isnull=False,
                done_at__date__gte=first_day,
            ).count(),
            "url": "{}/#/SharedLink/ServiceOrder/{}/show?company={}".format(
                settings.FRONTEND_URL,
                str(service.uuid),
                str(company.uuid),
            ),
        }
        for service in services
        if service.description
    ]

    return services_final


def service_order_report_email():
    """
    An email notification with service_order metrics to send it to managers.
    Call it every workday at 07:00.

    Does not group results of multiple Company instances.

    Does not follow the regular notification flow.
    """

    NOTIFICATION_AREA = "servicos.relatorio_de_periodo"
    TIME_INTERVALS = get_obj_from_path(
        VALID_NOTIFICATIONS, "servicos__relatorio_de_periodo__time_intervals"
    )

    # Determine which users can receive the notification
    user_notifs = UserNotification.objects.filter(
        notification=NOTIFICATION_AREA
    ).values_list("uuid", "user", "time_interval")

    # Reference data required for the main logic loop
    user_to_frequency = {}
    usr_notif_ids = []
    for usr_notif_id, user_uuid, time_interval in user_notifs:
        user_to_frequency[str(user_uuid)] = time_interval_to_label(time_interval)
        usr_notif_ids.append(usr_notif_id)
    users_pool = list(user_to_frequency.keys())

    # Common notification data
    template_path = "email_handler/email/report_services"
    title_template = "Kartado - Relatório de serviços de {} a {} - {}"

    # Only consider Company instances that are related to the UserNotification instances
    # NOTE: distinct() to avoid duplicate notifications for the same Company instance
    companies = Company.objects.filter(user_notifications__in=usr_notif_ids).distinct()

    for company in companies:
        status_concluded = ServiceOrderActionStatus.objects.filter(
            kind="ACTION_STATUS", is_final=True, companies=company
        )
        watchers = ServiceOrderWatcher.objects.filter(
            service_order__company=company
        ).only("user", "firm", "service_order")

        # Structure: {"<interval>": {"<user_uuid>": {"user": <user_instance>, "service_orders": [<service_order_instance>]}}}
        watcher_users = {interval: {} for interval in TIME_INTERVALS}

        def add_service_order(user: User, service_order: ServiceOrder):
            """
            Helper to insert items to the watcher_users dict according to the
            structure documented above.

            Args:
                user (User): User that's going to be notified
                service_order (ServiceOrder): ServiceOrder related to the notification
            """
            user_uuid = str(user.uuid)
            user_frequency = user_to_frequency[user_uuid]

            if user_uuid not in watcher_users[user_frequency]:
                watcher_users[user_frequency][user_uuid] = {
                    "user": user,
                    "service_orders": [],
                }

            watcher_users[user_frequency][user_uuid]["service_orders"].append(
                service_order
            )

        # Go through all the watchers and, if the user is part of the pool, add him
        # to the watcher_users using the helper
        for watcher in watchers:
            if watcher.user and str(watcher.user.uuid) in users_pool:
                add_service_order(watcher.user, watcher.service_order)
            elif watcher.firm:
                for user in watcher.firm.users.all():
                    if str(user.uuid) in users_pool:
                        add_service_order(user, watcher.service_order)

        # Divide users per frequency
        send_to_week = []
        send_to_month = []

        today = timezone.now()
        first_work_day_month = is_first_work_day_month(today)
        monday = today.weekday() == 0

        # NOTE: If new intervals are going to be supported, you'll only need to edit the
        # code under this comment for specific logic. The code above already accounts for
        # TIME_INTERVALS changes.
        if first_work_day_month:
            send_to_month = list(watcher_users["MONTH"].values())
        if monday:
            send_to_week = list(watcher_users["WEEK"].values())

        if send_to_week:
            for watcher in send_to_week:
                start_day = today - datetime.timedelta(days=7)

                services_final = get_service_report(
                    status_concluded,
                    watcher["service_orders"],
                    start_day,
                    today,
                    company,
                )

                title = title_template.format(
                    start_day.strftime("%d/%m/%Y"),
                    today.strftime("%d/%m/%Y"),
                    company.name,
                )
                context = {
                    "title": title,
                    "period_text": "a última semana",
                    "date": "de {} a {}".format(
                        start_day.strftime("%d/%m/%Y"),
                        today.strftime("%d/%m/%Y"),
                    ),
                    "services": services_final,
                    "company": company.name,
                }

                create_notifications(
                    [watcher["user"]],
                    company,
                    context,
                    template_path,
                    push=False,
                    user_notification=NOTIFICATION_AREA,
                )

        if send_to_month:
            for watcher in send_to_month:
                last_week = today - datetime.timedelta(days=7)
                start_day = last_week.replace(day=1)

                services_final = get_service_report(
                    status_concluded,
                    watcher["service_orders"],
                    start_day,
                    today,
                    company,
                )

                title = title_template.format(
                    start_day.strftime("%d/%m/%Y"),
                    today.strftime("%d/%m/%Y"),
                    company.name,
                )
                context = {
                    "title": title,
                    "period_text": "o último mês",
                    "date": "em {}".format(start_day.strftime("%m/%Y")),
                    "services": services_final,
                    "company": company.name,
                }

                create_notifications(
                    [watcher["user"]],
                    company,
                    context,
                    template_path,
                    push=False,
                    user_notification=NOTIFICATION_AREA,
                )


def monitoring_cycles_emails():
    now = timezone.now()
    cycles = MonitoringCycle.objects.filter(
        start_date__date__lte=now.date(),
        end_date__date__gte=now.date(),
        email_created=False,
    )
    for item in cycles:
        monitoring_cycle_email(item)
        item.email_created = True
        item.save()


def delete_old_queued_emails():
    start_time = time.perf_counter()
    OBJECT_LIMIT = 20000

    email_qs_len = 0
    event_qs_len = 0
    now = timezone.now()
    six_months_ago = now - relativedelta(months=6)
    db = settings.DATABASES["default"]
    conn = psycopg2.connect(
        user=db["USER"],
        password=db["PASSWORD"],
        database=db["NAME"],
        host=db["HOST"],
        port=db["PORT"],
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    event_qs = QueuedEmailEvent.objects.filter(created_at__lt=six_months_ago).order_by(
        "created_at"
    )[:OBJECT_LIMIT]
    if event_qs.exists():
        new_qs = tuple(
            QueuedEmailEvent.objects.filter(pk__in=event_qs).values_list(
                "uuid", flat=True
            )
        )
        email_qs_len = len(new_qs)
        s_list = ""
        for item in range(email_qs_len):
            s_list += "%s, "
        cur.execute(
            f"DELETE FROM email_handler_queuedemailevent WHERE email_handler_queuedemailevent.uuid IN ({s_list[:-2]}) ;",
            [*new_qs],
        )
    qs = QueuedEmail.objects.filter(
        in_progress=False, sent=True, created_at__lt=six_months_ago
    ).order_by("created_at")[:OBJECT_LIMIT]
    if qs.exists():
        new_qs = tuple(
            QueuedEmail.objects.filter(pk__in=qs).values_list("uuid", flat=True)
        )

        event_qs_len = len(new_qs)
        s_list = ""
        for item in range(event_qs_len):
            s_list += "%s, "

        cur.execute(
            f"DELETE FROM email_handler_queuedemail_send_to_users WHERE email_handler_queuedemail_send_to_users.queuedemail_id IN ({s_list[:-2]}) ;",
            [*new_qs],
        )

        cur.execute(
            f"DELETE FROM email_handler_queuedemail WHERE email_handler_queuedemail.uuid IN ({s_list[:-2]}) ;",
            [*new_qs],
        )
    end_time = time.perf_counter()
    logging.info(
        f"{str(round(end_time - start_time, 3))} seconds elapsed and {str(email_qs_len + event_qs_len)} objects deleted"
    )

    conn.close()
