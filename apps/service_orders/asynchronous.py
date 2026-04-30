import logging
from collections import defaultdict
from copy import deepcopy
from datetime import timedelta
from typing import DefaultDict

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.companies.models import Company
from apps.service_orders.const import status_types
from apps.service_orders.models import Procedure
from apps.users.const.notification_types import PUSH_NOTIFICATION
from apps.users.models import UserNotification
from helpers.apps.users import add_unique_debounce_data
from helpers.notifications import create_single_notification, get_disclaimer


def notify_pending_procedures():
    """
    Inject pending procedures notification for users with the proper
    UserNotification configuration.

    This function is called on a 1 minute rate by AWS SQS

    Groups results of multiple Company instances.
    """

    # When we no longer care about the Procedure (inclusive: if 7, stops at 8)
    CARE_UNTIL = 7

    NOTIFICATION_AREA = "tarefas.tarefas_pendentes"

    user_notifs = UserNotification.objects.filter(
        notification=NOTIFICATION_AREA,
    )

    if user_notifs:
        # Only query Procedure from relevant Company instances (and remove duplicates)
        relevant_user_ids = list(set(user_notifs.values_list("user", flat=True)))

        # Get only Procedures who are not past the "caring" space
        # NOTE: This is not done for the CARE_FROM limit because the value
        # of timezone.localtime() is going to be different when the handler takes over
        days_ago_delta = timezone.now() - timedelta(days=CARE_UNTIL)
        pending_procedures = (
            Procedure.objects.filter(
                # Determine is the Procedure is pending
                service_order_action_status__kind=status_types.ACTION_STATUS,
                service_order_action_status__is_final=False,
                procedure_next__isnull=True,
                deadline__date__gte=days_ago_delta.date(),
                # Determine if the Procedure is from a relevant User
                responsible__in=relevant_user_ids,
            )
            .prefetch_related("responsible", "action", "action__service_order")
            .distinct()
        )

        # Create a reference dict to point a Company ID to the serialized Procedure list
        company_to_procedures: DefaultDict[str, list] = defaultdict(list)
        for procedure in pending_procedures:
            company_uuid = str(procedure.get_company_id)
            deadline_with_tz = procedure.deadline.astimezone()

            serialized_procedure = {
                "uuid": str(procedure.pk),
                "company_id": str(company_uuid),
                "responsible_id": str(procedure.responsible.pk),
                "to_do": procedure.to_do,
                "action": procedure.action.name,
                "deadline": deadline_with_tz.strftime("%d/%m/%Y às %H:%M"),
                "deadline_iso": deadline_with_tz.isoformat(),
                "os_number": procedure.action.service_order.number,
                "url": "{}/#/SharedLink/Procedure/{}/show?company={}".format(
                    settings.FRONTEND_URL,
                    str(procedure.pk),
                    str(company_uuid),
                ),
            }
            company_to_procedures[company_uuid].append(serialized_procedure)

        def responsible_validator(item, usr_notif) -> bool:
            """Validate the user is the responsible for the Procedure"""
            return item["responsible_id"] == str(usr_notif.user.pk)

        add_unique_debounce_data(
            user_notifs,
            company_to_seri_item=company_to_procedures,
            dedup_key="uuid",
            validator=responsible_validator,
        )
    else:
        logging.info("No UserNotification configured to receive pending procedures")


def notify_pending_procedures_for_report():
    """
    Inject pending procedures report notification for users with the proper
    UserNotification configuration.

    This function is called every day 1 of the month at 07:00 by AWS SQS.

    Groups results of multiple Company instances.
    """

    NOTIFICATION_AREA = "tarefas.boletim_de_pendencias"
    TEMPLATE_PATH = "service_orders/email/pending_procedures_report"

    user_notifs = UserNotification.objects.filter(
        notification=NOTIFICATION_AREA,
    )

    if user_notifs:
        # Get a date from last month to extract month and year (never day)
        last_month = (timezone.now() - relativedelta(months=1)).date()
        last_month_str = last_month.strftime("%m/%Y")

        # Get raw data using one DB call
        raw_serialized_procedures = Procedure.objects.filter(
            Q(service_order_action_status__kind=status_types.ACTION_STATUS)
            & Q(service_order_action_status__is_final=False)
            & Q(procedure_next__isnull=True)
            # Either the procedure is not done, or it was finished last month
            & (
                Q(done_at__isnull=True)
                | (
                    Q(done_at__date__month=last_month.month)
                    & Q(done_at__date__year=last_month.year)
                )
            )
        ).values_list(
            "firm__name",
            "firm__company",
            "firm__company__name",
            "deadline",
            "done_at",
        )

        # Count each Procedure status by Company then by Firm
        # Structure: company_name -> <done_on_time, done_after_deadline, pending, firms> -> firm_name -> <done_on_time, done_after_deadline, pending> -> count
        company_name_to_proc = {}
        init_count = {
            "done_on_time": 0,
            "done_after_deadline": 0,
            "pending": 0,
        }
        for (
            firm_name,
            company_id,
            company_name,
            deadline,
            done_at,
        ) in raw_serialized_procedures:
            # Initialize the grouping
            if company_name not in company_name_to_proc:
                company_init = deepcopy(init_count)

                # Add key unique to Company level keys
                company_init["firms"] = {}

                # Add Company specific URL
                company_url = f"{settings.FRONTEND_URL}/#/SharedLink/ServiceOrder?company={str(company_id)}"
                company_init["company_url"] = company_url

                company_name_to_proc[company_name] = company_init
            if firm_name not in company_name_to_proc[company_name]["firms"]:
                firm_init = deepcopy(init_count)
                company_name_to_proc[company_name]["firms"][firm_name] = firm_init

            # Determine the status
            if done_at:
                procedure_status = (
                    "done_on_time" if done_at <= deadline else "done_after_deadline"
                )
            else:
                procedure_status = "pending"

            # Update firm count
            company_name_to_proc[company_name]["firms"][firm_name][
                procedure_status
            ] += 1
            # Update company count
            company_name_to_proc[company_name][procedure_status] += 1

        for user_notif in user_notifs:
            user = user_notif.user
            company_names = user_notif.companies.values_list("name", flat=True)
            rep_company: Company = user_notif.companies.first()
            disclaimer_msg, _ = get_disclaimer(rep_company.company_group)

            grouped_data = {
                company_name: company_name_to_proc[company_name]
                for company_name in company_names
                if company_name in company_name_to_proc
            }

            context = {
                "title": f"Kartado — Boletim mensal de pendências ({last_month_str})",
                "grouped_data": grouped_data,
                "last_month": last_month_str,
                "disclaimer": disclaimer_msg,
            }

            create_single_notification(
                user=user,
                company=rep_company,
                context=context,
                template_path=TEMPLATE_PATH,
                user_notification=NOTIFICATION_AREA,
                push=user_notif.notification_type == PUSH_NOTIFICATION,
            )

    else:
        logging.info(
            "No UserNotification configured to receive pending procedures report"
        )


# Zappa alias: function path must be ≤63 chars (0.61.x validation)
def notify_pending_for_report():
    return notify_pending_procedures_for_report()
