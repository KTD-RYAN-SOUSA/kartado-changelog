import logging
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List
from uuid import UUID

import sentry_sdk
from django.db.models import Q
from django.utils import timezone
from django_bulk_update.helper import bulk_update
from zappa.asynchronous import task

from apps.companies.models import Company, UserInFirm
from apps.occurrence_records.models import RecordPanel, RecordPanelShowList
from apps.users.const.notification_areas import VALID_NOTIFICATIONS
from apps.users.const.notification_types import NOTIFICATION_TYPES, PUSH_NOTIFICATION
from apps.users.const.time_intervals import (
    DEFAULT_INTERVAL,
    DEFAULT_LABEL,
    NOTIFICATION_INTERVALS,
)
from apps.users.models import User, UserNotification
from helpers.notifications import create_single_notification, get_disclaimer
from helpers.permissions import PermissionManager, join_queryset


def get_possible_notifications(
    user: User, companies: Iterable[Company] = [], companies_ids: Iterable[UUID] = []
) -> List[str]:
    """
    Return all available notifications for that particular User depending
    on their permissions.

    Args:
        user (User): The User we'll be checking for available notifications.
        companies (Iterable[Company]): List of Company instances to use when checking permissions.
        companies_ids (Iterable[UUID]): Alternative to using Company instances by providing the IDs.
        Should not be used alongside the companies argument.

    Returns:
        List[str]: List with the identifiers for the available notifications.
    """

    possible_notifications = []

    # Ensure only one company argument was used
    if companies and companies_ids:
        raise ValueError(
            "The argument companies and companies_ids should not be used together"
        )
    # Check if using IDs input or instance input
    elif companies_ids:
        companies_list = Company.objects.filter(uuid__in=companies_ids)
    else:
        companies_list = companies

    # If no companies were provided, there's no way to get the possible notifications
    if companies_list and len(companies_list) >= 1:
        company_ids = [company.uuid for company in companies_list]
        model_to_perm_manager: Dict[str, PermissionManager] = {}

        # For each notification area
        for notif_area, area_notifs in VALID_NOTIFICATIONS.items():
            # For each notification in that area
            for notif, notif_info in area_notifs.items():
                notif_req_model_perms = notif_info.get("required_permissions", {})

                # For each model permissions requirements
                perm_checker = []
                for model_name, req_model_perms in notif_req_model_perms.items():
                    # Since the companies_ids list does not change, we can cache
                    # the manager for other iterations instead of instanciating every time
                    if model_name not in model_to_perm_manager:
                        perm_manager = PermissionManager(company_ids, user, model_name)
                        model_to_perm_manager[model_name] = perm_manager
                    else:
                        perm_manager = model_to_perm_manager[model_name]

                    perm_checker.append(
                        perm_manager.has_all_required_permissions(req_model_perms)
                    )

                if all(perm_checker):
                    possible_notifications.append(f"{notif_area}.{notif}")

    return possible_notifications


def get_notification_accepts(notification: str) -> dict:
    """
    Returns a dict with all the possibilities of configuration for the provided
    notification

    Args:
        notification (str): Notification in the <area>.<notification> format

    Returns:
        dict: Dict with all possibilities of configuration for that notification
        returns an empty dict if the notification doesn't exist.
    """

    area, notif = notification.split(".")
    accepts = {}

    try:
        accepts = VALID_NOTIFICATIONS[area][notif]
    except Exception as e:
        sentry_sdk.capture_exception(e)

    return accepts


def get_notification_types():
    """Lists the possible notification types for the UserNotification endpoints"""
    options = []
    for option, _ in NOTIFICATION_TYPES:
        options.append(option)

    return options


def time_interval_to_label(time_interval: timedelta) -> str:
    """
    Get the corresponding label for the provided timedelta.
    Defaults to DEFAULT_LABEL.

    Use this when returning a time_interval to the user.
    """

    return next(
        (
            label
            for (value, label) in NOTIFICATION_INTERVALS
            if isinstance(time_interval, timedelta) and time_interval == value
        ),
        DEFAULT_LABEL,
    )


def label_to_time_interval(interval_label: str) -> timedelta:
    """
    Get the corresponding timedelta for the provided label.
    Defaults to DEFAULT_INTERVAL.

    Use this when receiving a time_interval from the user.
    """

    return next(
        (
            value
            for (value, label) in NOTIFICATION_INTERVALS
            if isinstance(interval_label, str) and label == interval_label
        ),
        DEFAULT_INTERVAL,
    )


def get_notification_summary(company, user):
    """
    Retrieves the current summary of notifications

    Example:
    ```python
    {
        "auscultacao.boletim_mensal": {
            "accepts": {
                "time_intervals": ["IMMEDIATE", "HOUR"],
                "notification_types": ["EMAIL"],
            },
            "EMAIL": [
                {"time_interval": "IMMEDIATE", "preferred_time": None}
            ]
        }
    }
    ```
    """

    # Build initial summary
    summary = {}
    for notif in get_possible_notifications(user, companies=[company]):
        summary[notif] = {
            notif_type.lower(): [] for notif_type in get_notification_types()
        }
        summary[notif]["accepts"] = get_notification_accepts(notif)

    user_notifs = UserNotification.objects.filter(
        companies=company, user=user
    ).values_list(
        "notification", "notification_type", "time_interval", "preferred_time"
    )

    for notif, notif_type, datetime_interval, preferred_time in user_notifs:
        if notif in summary:
            time_interval = time_interval_to_label(datetime_interval)
            summary[notif][notif_type.lower()].append(
                {
                    "time_interval": time_interval,
                    "preferred_time": preferred_time,
                }
            )

    return summary


def add_debounce_data(
    usr_notifs: Iterable[UserNotification],
    data: Any,
    many=False,
    dedup_key: str = None,
):
    """
    Inititialize the field and add `debounce_data` item.

    Args:
        usr_notif (UserNotification): Recipient of the new item
        data (Any): Item to be added
        many (bool): If the data contains more than one item
        dedup_key (str): Key to be used to differentiate the data and remove duplicates
    """

    upd_usr_notifs = []
    for usr_notif in usr_notifs:
        if not usr_notif.debounce_data:
            usr_notif.debounce_data = []

        if many:
            # Create new list without the duped items if dedup_key is provided
            deduped_data = []
            if dedup_key:
                for new_item in data:
                    dedup_data = new_item[dedup_key]

                    if not any(
                        debounce_item[dedup_key] == dedup_data
                        for debounce_item in usr_notif.debounce_data
                    ):
                        deduped_data.append(new_item)

            usr_notif.debounce_data.extend(deduped_data if dedup_key else data)
        else:
            # If the data is already in the debounce_data field, skip this usr_notif
            if dedup_key:
                dedup_data = data[dedup_key]
                if any(
                    debounce_item[dedup_key] == dedup_data
                    for debounce_item in usr_notif.debounce_data
                ):
                    continue

            usr_notif.debounce_data.append(data)

        upd_usr_notifs.append(usr_notif)

    bulk_update(upd_usr_notifs, update_fields=["debounce_data"])


def add_unique_debounce_data(
    user_notifs: Iterable[UserNotification],
    company_to_seri_item: Dict[str, Iterable[dict]],
    dedup_key: str,
    validator: Callable[[dict, UserNotification], bool] = None,
):
    """
    Helper to add debounce data to UserNotification according to a reference dict provided as an
    argument.

    This is useful when the data being added differs for each UserNotification instance. Common for
    Company dependant data.

    In summary: if your data being added is the same for all instances, use add_debounce_data(),
    otherwise, create a reference dict and use add_unique_debounce_data().

    Args:
        user_notifs (Iterable[UserNotification]): List of UserNotification instances that are going to receive
        the new data.
        company_to_seri_item (Dict[str, Iterable[dict]]): The reference dict with the list of data that's going to be
        added attached to a Company ID.
        dedup_key (str): The key used to access the list of data and to identify duplicates of already debounced items.
        validator (Callable[[dict, UserNotification], bool]): Allows the caller to provide a function for custom validation.
    """

    updated_usr_notif_instances: List[UserNotification] = []

    for user_notif in user_notifs:
        notif_companies_ids = user_notif.companies.values_list("uuid", flat=True)

        # Find which items are already debounced
        if not user_notif.debounce_data:
            user_notif.debounce_data = []
        deb_item_ids = [deb_item[dedup_key] for deb_item in user_notif.debounce_data]

        # Separate only the new items (not debounced) from the reference dict company_to_seri_item
        new_debounce_data = [
            serialized_item
            # For each Company ID
            for company_uuid in notif_companies_ids
            # Only if the Company ID is present in the reference dict
            if str(company_uuid) in company_to_seri_item
            # Fetch all items for the Company
            for serialized_item in company_to_seri_item[str(company_uuid)]
            # Add to list only if it wasn't already debounced
            if serialized_item[dedup_key] not in deb_item_ids
            # Apply the provided validator if present
            if validator is None or validator(serialized_item, user_notif)
        ]

        # Extend the debounce_data only with new items (if any) and
        # add it to the bulk update waiting list.
        if new_debounce_data:
            user_notif.debounce_data.extend(new_debounce_data)
            updated_usr_notif_instances.append(user_notif)

    # Bulk update the UserNotification instances that have new debounce data items
    if updated_usr_notif_instances:
        bulk_update(updated_usr_notif_instances, update_fields=["debounce_data"])


def send_debounced_readings(
    usr_notif: UserNotification,
    title_template: str,
    template_path: str,
):
    """
    Common reading debounce logic to create a new notification.
    Assumes all constraints were already met.

    Does not group results of multiple Company instances.

    Args:
        usr_notif (UserNotification): The instance to be debounced
        title_template (str): Template for the email title
        template_path (str): Path to the notification template (requires exactly one `{}`)
    """

    debounce_data = usr_notif.debounce_data

    # Group reading items by Company
    company_id_to_reading_items = defaultdict(list)
    for reading_item in debounce_data:
        company_id = reading_item["company_id"]
        company_id_to_reading_items[company_id].append(reading_item)

    # Send notification for each Company
    companies = usr_notif.companies.all()
    for company in companies:
        company_id = str(company.pk)
        disclaimer_msg, _ = get_disclaimer(company.company_group)

        # Build initial context with data for that Company
        reading_items = company_id_to_reading_items[company_id]
        context = {
            "reading_items": reading_items,
            "conditions": {},
            "disclaimer": disclaimer_msg,
        }

        # Build conditions counters
        for reading_item in reading_items:
            condition = reading_item["condition"]

            # Initialize the counter for that condition if not present
            if condition not in context["conditions"]:
                context["conditions"][condition] = 0

            context["conditions"][condition] += 1

        # Use conditions counters to build the notification title
        conditions_text = ", ".join(
            f"{key} ({value})" for (key, value) in context["conditions"].items()
        )
        context["title"] = title_template.format(conditions_text)

        create_single_notification(
            user=usr_notif.user,
            company=company,
            context=context,
            template_path=template_path,
            user_notification=usr_notif.notification,
            push=usr_notif.notification_type == PUSH_NOTIFICATION,
        )


def send_notif_for_each_related_company(
    usr_notif: UserNotification, notification_title: str, template_path: str
):
    """
    Create the notifications for the provided UserNotification assuming it is NOT grouped
    for all Company instances of the UserNotification.

    Args:
        usr_notif (UserNotification): Instance of the UserNotification to be sent
        notification_title (str): The subject of the notification
        template_path (str): Path to the templates to be rendered (without extension)
    """

    # Initial data
    debounce_data = usr_notif.debounce_data
    notif_user = usr_notif.user
    notification = usr_notif.notification
    is_push = usr_notif.notification_type == PUSH_NOTIFICATION

    # Needed to separate notifications for each Company
    id_to_notif_company = {
        str(company.pk): company for company in usr_notif.companies.all()
    }

    # Determine one representative Company and get disclaimer for that group
    rep_comp: Company = next(iter(id_to_notif_company.values()))
    disclaimer_msg, _ = get_disclaimer(rep_comp.company_group)

    # Create a notification for each debounce_item
    for debounce_item in debounce_data:
        # Since the debounce data structure was changed this may happen for instances created before the change,
        # so we need to handle it here and log the error properly before continuing.
        # NOTE: Once this happens for all previously created instances it SHOULD NOT continue to happen. If
        # it does, consider that a bug.
        if "company_id" not in debounce_item:
            logging.error(
                "send_notif_for_each_related_company: debounce_item does not have the required company_id key"
            )
            continue

        company_id = debounce_item.get("company_id")
        company = id_to_notif_company[company_id]

        # Keep original dict structure but add two new necessary keys/values
        context = deepcopy(debounce_item)
        context.update(
            {
                "title": notification_title,
                "disclaimer": disclaimer_msg,
            }
        )

        create_single_notification(
            user=notif_user,
            company=company,
            context=context,
            template_path=template_path,
            user_notification=notification,
            push=is_push,
        )


def handle_novas_leituras_debounce(usr_notif: UserNotification):
    """
    Handle `auscultacao.novas_leituras` debouncing

    Does not group results of multiple Company instances.

    Args:
        usr_notif (UserNotification): The instance to be debounced
    """

    TEMPLATE_PATH = "users/email/usr_notif_new_readings"
    TITLE_TEMPLATE = "Segurança de barragens - Leituras para validação em {}"

    send_debounced_readings(usr_notif, TITLE_TEMPLATE, TEMPLATE_PATH)


def handle_novas_leituras_validadas_debounce(
    usr_notif: UserNotification,
):
    """
    Handle `auscultacao.novas_leituras_validadas` debouncing

    Does not group results of multiple Company instances.

    Args:
        usr_notif (UserNotification): The instance to be debounced
    """

    TEMPLATE_PATH = "users/email/usr_notif_new_readings"
    TITLE_TEMPLATE = "Segurança de barragens - Leituras validadas em {}"

    send_debounced_readings(usr_notif, TITLE_TEMPLATE, TEMPLATE_PATH)


def handle_leitura_precisa_ser_refeita_debounce(usr_notif: UserNotification):
    """
    Handle `auscultacao.leitura_precisa_ser_refeita` debouncing

    Does not group results of multiple Company instances.

    Args:
        usr_notif (UserNotification): The instance to be debounced
    """

    TEMPLATE_PATH = "users/email/usr_notif_remake_reading"
    TITLE_TEMPLATE = "Segurança de barragens - Refazer leituras em {}"

    user = usr_notif.user

    # Group reading items by Company
    company_id_to_reading_items = defaultdict(list)
    for reading_item in usr_notif.debounce_data:
        company_id = reading_item["company_id"]
        company_id_to_reading_items[company_id].append(reading_item)

    companies = usr_notif.companies.all()
    for company in companies:
        title = TITLE_TEMPLATE.format(company.name)
        disclaimer_msg, _ = get_disclaimer(company.company_group)

        company_id = str(company.pk)
        reading_items = company_id_to_reading_items[company_id]
        context = {
            "title": title,
            "reading_items": reading_items,
            "disclaimer": disclaimer_msg,
        }

        create_single_notification(
            user=user,
            company=company,
            context=context,
            template_path=TEMPLATE_PATH,
            user_notification=usr_notif.notification,
            push=usr_notif.notification_type == PUSH_NOTIFICATION,
        )


def handle_leituras_ultrapassaram_prazo_de_validacao(
    usr_notif: UserNotification,
):
    """
    Handle `auscultacao.leituras_ultrapassaram_prazo_de_validacao` debouncing

    Does not group results of multiple Company instances.

    Args:
        usr_notif (UserNotification): The instance to be debounced
    """

    TEMPLATE_PATH = "users/email/usr_notif_overdue_validation"
    TITLE_TEMPLATE = "Segurança de barragens - {} {} com validação atrasada"

    user = usr_notif.user

    # Group reading items by Company
    company_id_to_reading_items = defaultdict(list)
    for reading_item in usr_notif.debounce_data:
        company_id = reading_item["company_id"]
        company_id_to_reading_items[company_id].append(reading_item)

    companies = usr_notif.companies.all()
    for company in companies:
        company_id = str(company.pk)
        reading_items = company_id_to_reading_items[company_id]

        readings_amount = len(reading_items) if isinstance(reading_items, list) else 0
        title = TITLE_TEMPLATE.format(
            readings_amount, "leituras" if readings_amount != 1 else "leitura"
        )
        disclaimer_msg, _ = get_disclaimer(company.company_group)

        context = {
            "title": title,
            "reading_items": reading_items,
            "disclaimer": disclaimer_msg,
            "readings_amount": readings_amount,
        }

        create_single_notification(
            user=user,
            company=company,
            context=context,
            template_path=TEMPLATE_PATH,
            user_notification=usr_notif.notification,
            push=usr_notif.notification_type == PUSH_NOTIFICATION,
        )


def handle_informacoes_sobre_registros(usr_notif: UserNotification):
    """
    Handle `registros.informacoes_sobre_registros` debouncing

    Groups results of multiple Company instances.

    Args:
        usr_notif (UserNotification): The instance to be debounced
    """

    from apps.occurrence_records.views import get_occurrence_record_queryset
    from apps.service_orders.views import get_service_order_queryset

    TEMPLATE_PATH = "users/email/usr_notif_occurrence_record_update"

    debounce_data = usr_notif.debounce_data
    rep_company = usr_notif.companies.first()
    notif_companies = usr_notif.companies.all().values_list("uuid", flat=True)
    disclaimer_msg, _ = get_disclaimer(rep_company.company_group)
    user = usr_notif.user

    occ_records_qs = None
    service_orders_qs = None
    for company_id in notif_companies:
        occ_records_qs = join_queryset(
            occ_records_qs,
            get_occurrence_record_queryset("list", user_company=company_id, user=user),
        )
        service_orders_qs = join_queryset(
            service_orders_qs,
            get_service_order_queryset("list", user_company=company_id, user=user),
        )

    available_occ_records = set(occ_records_qs.values_list("uuid", flat=True))
    available_service_orders = set(service_orders_qs.values_list("uuid", flat=True))

    # Separate each item
    created_ors = []
    updated_ors = []
    services = []
    for occ_record_id, occ_record_data in debounce_data.items():
        # Skip unavailable OccurrenceRecord instances
        if UUID(occ_record_id) in available_occ_records:
            if occ_record_data["created"]:
                created_ors.append(occ_record_data)

            if occ_record_data["updated"]:
                updated_ors.append(occ_record_data)

            if occ_record_data["services"]:
                services.extend(
                    service_data
                    for service_id, service_data in occ_record_data["services"].items()
                    # Skip unavailable ServiceOrder instances
                    if UUID(service_id) in available_service_orders
                )

    # Dates
    report_start_date = (
        usr_notif.last_notified.strftime("%d/%m/%Y")
        if usr_notif.last_notified
        else usr_notif.created_at.strftime("%d/%m/%Y")
    )
    report_end_date = timezone.now().strftime("%d/%m/%Y")

    context = {
        "title": "Kartado - Informações sobre registros",
        "created": created_ors,
        "updated": updated_ors,
        "services": services,
        "report_start_date": report_start_date,
        "report_end_date": report_end_date,
        "disclaimer": disclaimer_msg,
    }

    if created_ors or updated_ors or services:
        create_single_notification(
            user=user,
            company=rep_company,
            context=context,
            template_path=TEMPLATE_PATH,
            user_notification=usr_notif.notification,
            push=usr_notif.notification_type == PUSH_NOTIFICATION,
        )


def handle_alteracao_de_status(usr_notif: UserNotification):
    """
    Handle `registros.alteracao_de_status` debouncing.

    Does not group results of multiple Company instances.

    Args:
        usr_notif (UserNotification): The instance to be debounced
    """

    TITLE = "Kartado - Alteração de status de registro"
    TEMPLATE_PATH = "users/email/usr_notif_status_change"

    send_notif_for_each_related_company(usr_notif, TITLE, TEMPLATE_PATH)


def handle_registros_adicao_aos_notificados(usr_notif: UserNotification):
    """
    Handle `registros.adicao_aos_notificados` debouncing

    Does not group results of multiple Company instances.

    Args:
        usr_notif (UserNotification): The instance to be debounced
    """

    TITLE = "Kartado - Adição aos notificados de um registro"
    TEMPLATE_PATH = "occurrence_records/email/occurrence_record_watcher"

    send_notif_for_each_related_company(usr_notif, TITLE, TEMPLATE_PATH)


def handle_servicos_adicao_aos_notificados(usr_notif: UserNotification):
    """
    Handle `servicos.adicao_aos_notificados` debouncing

    Does not group results of multiple Company instances.

    Args:
        usr_notif (UserNotification): The instance to be debounced
    """

    TITLE = "Kartado - Adição aos notificados de um serviço"
    TEMPLATE_PATH = "service_orders/email/service_order_watcher"

    send_notif_for_each_related_company(usr_notif, TITLE, TEMPLATE_PATH)


def handle_tarefas_novas_tarefas(usr_notif: UserNotification):
    """
    Handle `tarefas.novas_tarefas` debouncing.

    Does not group results of multiple Company instances.

    Args:
        usr_notif (UserNotification): The instance to be debounced
    """

    TITLE = "Kartado — Nova tarefa"
    TEMPLATE_PATH = "service_orders/email/procedure_created"

    send_notif_for_each_related_company(usr_notif, TITLE, TEMPLATE_PATH)


def handle_tarefas_pendentes(usr_notif: UserNotification):
    """
    Handle `tarefas.tarefas_pendentes` debouncing

    Groups results of multiple Company instances.

    Args:
        usr_notif (UserNotification): The instance to be debounced
    """

    # When we start caring about the Procedure
    CARE_FROM = -3

    # When we no longer care about the Procedure (inclusive: if 7, stops at 8)
    CARE_UNTIL = 7

    TEMPLATE_PATH = "service_orders/email/pending_procedures"
    SECONDS_IN_A_DAY = 86400

    debounce_data = usr_notif.debounce_data
    rep_company = usr_notif.companies.first()
    disclaimer_msg, _ = get_disclaimer(rep_company.company_group)

    # Group delayed, reaching deadline and deadline today
    deadline_overdue = []
    deadline_close = []
    deadline_soon = []
    for serialized_procedure in debounce_data:
        # Convert serialized deadline to datetime obj
        deadline_iso = serialized_procedure["deadline_iso"]
        deadline = datetime.fromisoformat(deadline_iso)

        # Get how many days until/past deadline
        # NOTE: We consider non complete days (less than 24 hours) as a normal complete day
        # See https://kartado.atlassian.net/browse/KTD-3633?focusedCommentId=29593
        seconds_delta = (timezone.localtime() - deadline).total_seconds()
        days_balance = round(seconds_delta / SECONDS_IN_A_DAY)

        serialized_procedure["delay"] = days_balance

        # If delayed and still in the CARE_UNTIL margin, add to delayed list
        if days_balance > 0 and days_balance <= CARE_UNTIL:
            deadline_overdue.append(serialized_procedure)
        # If the deadline is either today or tomorrow add to deadline_close
        elif days_balance == -1 or days_balance == 0:
            deadline_close.append(serialized_procedure)
        # If the deadline is close and within the CARE_FROM margin, add to deadline_soon
        elif days_balance < 0 and days_balance >= CARE_FROM:
            deadline_soon.append(serialized_procedure)
        # Could happen that the procedure has surpassed our "care" margins between being added
        # and actually triggering the notification. In this care, ignore.
        else:
            continue

    # Sort the lists
    deadline_overdue = sorted(deadline_overdue, key=lambda x: x["delay"], reverse=True)
    deadline_close = sorted(deadline_close, key=lambda x: x["delay"], reverse=True)
    deadline_soon = sorted(deadline_soon, key=lambda x: x["delay"], reverse=True)

    # How many procedures are actually going to be included
    # Could be different from len(debounce_data) since it accounts for
    # the "care" window.
    procedure_count = len(deadline_overdue) + len(deadline_close) + len(deadline_soon)

    # Send only if there's something to be sent according to the care window
    if procedure_count > 0:
        context = {
            "title": "Kartado — Relatório de Tarefas",
            "delayed": deadline_overdue,
            "deadline_close": deadline_close,
            "deadline_soon": deadline_soon,
            "procedure_count": procedure_count,
            "disclaimer": disclaimer_msg,
        }

        create_single_notification(
            user=usr_notif.user,
            company=rep_company,
            context=context,
            template_path=TEMPLATE_PATH,
            user_notification=usr_notif.notification,
            push=usr_notif.notification_type == PUSH_NOTIFICATION,
        )


def handle_aprovacao_de_boletim(usr_notif: UserNotification):
    """
    Handle `recursos.aprovacao_de_boletim` debouncing

    Does not group results of multiple Company instances.

    Args:
        usr_notif (UserNotification): The instance to be debounced
    """

    TITLE = "Kartado - Aprovação de boletins de medição"
    TEMPLATE_PATH = "service_orders/email/bulletin_approval"

    send_notif_for_each_related_company(usr_notif, TITLE, TEMPLATE_PATH)


def queue_debounced_user_notification(
    usr_notif: UserNotification,
) -> UserNotification:
    """
    Direct the debounced user notification to the proper handler
    using the `UserNotification` data.

    Args:
        usr_notif (UserNotification): Instance to be directed

    Returns:
        UserNotification: Updated instance
    """

    SUPPORTED_NOTIFICATIONS = {
        "auscultacao.novas_leituras": handle_novas_leituras_debounce,
        "auscultacao.novas_leituras_validadas": handle_novas_leituras_validadas_debounce,
        "auscultacao.leitura_precisa_ser_refeita": handle_leitura_precisa_ser_refeita_debounce,
        "aduscultacao.leituras_ultrapassaram_prazo_de_validacao": handle_leituras_ultrapassaram_prazo_de_validacao,
        "registros.informacoes_sobre_registros": handle_informacoes_sobre_registros,
        "registros.alteracao_de_status": handle_alteracao_de_status,
        "registros.adicao_aos_notificados": handle_registros_adicao_aos_notificados,
        "servicos.adicao_aos_notificados": handle_servicos_adicao_aos_notificados,
        "tarefas.novas_tarefas": handle_tarefas_novas_tarefas,
        "tarefas.tarefas_pendentes": handle_tarefas_pendentes,
        "recursos.aprovacao_de_boletim": handle_aprovacao_de_boletim,
    }

    try:
        notif_handler = SUPPORTED_NOTIFICATIONS[usr_notif.notification]
    except KeyError as e:
        sentry_sdk.capture_exception(e)
        logging.error("Unsupported debounced user notification was provided")
        return usr_notif
    else:
        # Default to created_at if it was never notified
        reference_point = (
            usr_notif.last_notified if usr_notif.last_notified else usr_notif.created_at
        )
        current_interval = timezone.now() - reference_point
        debounce_data = usr_notif.debounce_data
        should_notify = current_interval > usr_notif.time_interval and debounce_data

        # Respect the preferred time
        if usr_notif.preferred_time:
            should_notify = (
                should_notify and timezone.now().time() >= usr_notif.preferred_time
            )

        # If for some reason the debounce_data is empty but not None fix that
        if not debounce_data and debounce_data is not None:
            logging.warning(
                f"queue_debounced_user_notification: debounce_data empty but not None for {usr_notif.notification}"
            )
            usr_notif.debounce_data = None

        if should_notify:
            notif_handler(usr_notif)
            usr_notif.debounce_data = None
            usr_notif.last_notified = timezone.now()

        usr_notif.last_checked = timezone.now()
        usr_notif.in_progress = False

        return usr_notif


@task
def create_panels(user_in_firm_uuids):
    # Circular import
    from helpers.apps.occurrence_records import handle_record_panel_show

    user_in_firm = UserInFirm.objects.filter(uuid__in=user_in_firm_uuids)

    for instance in user_in_firm:

        firm = instance.firm
        user = instance.user
        subcompany = firm.subcompany

        query = Q(viewer_firms=firm) | Q(editor_firms=firm)

        if subcompany:
            query |= Q(viewer_subcompanies=subcompany) | Q(
                editor_subcompanies=subcompany
            )
        panels = RecordPanel.objects.filter(query).distinct()

        for panel in panels:
            handle_record_panel_show(RecordPanelShowList, panel, True, user, True)
