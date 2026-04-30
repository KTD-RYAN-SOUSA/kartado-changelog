import locale
import logging
from collections import defaultdict
from typing import Any, Dict

from django.conf import settings
from django.db.models import F, Q
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver

from apps.companies.models import UserInFirm
from apps.service_orders.const import resource_approval_status
from apps.service_orders.models import (
    MeasurementBulletin,
    Procedure,
    ProcedureResource,
    ServiceOrderWatcher,
)
from apps.users.const.notification_types import PUSH_NOTIFICATION
from apps.users.models import User, UserNotification
from helpers.apps.approval_flow import get_user_notif_of_approval_responsibles
from helpers.apps.users import add_debounce_data
from helpers.notifications import (
    create_notifications,
    create_single_notification,
    get_disclaimer,
)
from helpers.permissions import PermissionManager
from helpers.signals import disable_signal_for_loaddata, watcher_email_notification
from helpers.strings import clean_string


@receiver(post_save, sender=Procedure)
@disable_signal_for_loaddata
def email_procedure_info(sender, instance: Procedure, created: bool, **kwargs):
    """
    Notify Procedure creation

    Does not group results of multiple Company instances.
    """

    NOTIFICATION_AREA = "tarefas.novas_tarefas"

    if created and instance.action:
        service_order = instance.action.service_order
        company = service_order.company
        company_id = str(company.pk)

        # For the special judiciary forward email
        # judiciary_firms = Firm.objects.filter(company=company, is_judiciary=True)
        judiciary_users = User.objects.filter(
            user_firms__company=company, user_firms__is_judiciary=True
        )

        # For the regular notification
        # NOTE: judiciary_users are ignored to avoid duplicate emails (a normal one and a judiciary one)
        user_notifs = (
            UserNotification.objects.filter(
                notification=NOTIFICATION_AREA,
                companies=company,
                user=instance.responsible,
            ).exclude(user__in=judiciary_users)
            if instance.responsible
            else None
        )

        # Only process the data if there's someone to receive the email
        if user_notifs:
            # Process the common data for both emails
            to_do_snake = clean_string(instance.to_do) if instance.to_do.split() else ""

            url = "{}/#/SharedLink/Procedure/{}/show?company={}".format(
                settings.FRONTEND_URL, str(instance.uuid), str(company.uuid)
            )

            debounce_data = {
                "to_do": to_do_snake,
                "action": instance.action.name,
                "deadline": instance.deadline.strftime("%d/%m/%Y às %H:%M"),
                "os_number": service_order.number,
                "os_description": service_order.description,
                "responsible": (
                    instance.responsible.get_full_name() if instance.responsible else ""
                ),
                "created_by": (
                    instance.created_by.get_full_name() if instance.created_by else ""
                ),
                "created_at": instance.created_at.strftime("%d/%m/%Y"),
                "url": url,
                "company_id": company_id,
            }

            # Debounce the normal notification
            if user_notifs is not None:
                add_debounce_data(user_notifs, debounce_data)
        else:
            logging.info(
                f"No UserNotification configured for the responsibles of Procedure ({instance.uuid})"
            )


@receiver(post_save, sender=ServiceOrderWatcher)
@disable_signal_for_loaddata
def watcher_email_service_order(
    sender, instance: ServiceOrderWatcher, created: bool, **kwargs
):
    """
    Notify ServiceOrderWatcher related to a user

    Does not group results of multiple Company instances.
    """

    NOTIFICATION_AREA = "servicos.adicao_aos_notificados"

    watcher_email_notification(NOTIFICATION_AREA, instance, created)


def approved_measurement_bulletin(obj, notification_firms, subject, description):
    if obj.contract:
        # Get company
        company = (
            obj.contract.firm.company
            if obj.contract.firm
            else obj.contract.subcompany.company
        )

        # Get send_to
        history_users = list(
            obj.history.values_list("history_user_id", flat=True).distinct()
        )
        history_users += list(
            obj.contract.responsibles_hirer.values_list("uuid", flat=True)
        )
        history_users += list(
            obj.contract.responsibles_hired.values_list("uuid", flat=True)
        )

        send_to = User.objects.filter(
            Q(uuid__in=history_users)
            | Q(user_firms__uuid__in=notification_firms)
            | Q(user_firms_manager__uuid__in=notification_firms)
        ).distinct()

        # Create url
        url = "{}/#/SharedLink/MeasurementBulletin/{}/show?company={}".format(
            settings.FRONTEND_URL, str(obj.uuid), str(company.pk)
        )

        # Get context
        title = subject or "Um boletim de medição foi aprovado."
        message = (
            description
            or "Um novo boletim de medição foi aprovado no objeto {}.".format(
                obj.contract.name
            )
        )

        context = {"title": title, "message": message, "url": url}

        # Get templates path
        template_path = "service_orders/email/bulletin_email"

        # Create a email for each user
        create_notifications(
            send_to, company, context, template_path, instance=obj, url=url
        )


def measurement_bulletin_approval_change(instance: MeasurementBulletin):
    """
    Notify MeasurementBulletin approval change

    Does not group results of multiple Company instances.
    """

    NOTIFICATION_AREA = "recursos.aprovacao_de_boletim"

    user_notifs = get_user_notif_of_approval_responsibles(instance, NOTIFICATION_AREA)

    if user_notifs:
        company_id = (
            instance.contract.firm.company_id
            if instance.contract.firm
            else instance.contract.subcompany.company_id
        )
        url = "{}/#/SharedLink/MeasurementBulletin/{}/show?company={}".format(
            settings.FRONTEND_URL,
            str(instance.uuid),
            str(company_id),
        )

        # Convert the period datetimes
        period_start = (
            instance.period_starts_at.strftime("%d/%m/%Y")
            if instance.period_starts_at
            else ""
        )
        period_end = (
            instance.period_ends_at.strftime("%d/%m/%Y")
            if instance.period_ends_at
            else ""
        )
        period = f"{period_start} - {period_end}" if period_start or period_end else ""

        description = instance.contract.name if instance.contract else ""

        hired = (
            instance.contract.firm.name
            if instance.contract.firm
            else instance.contract.subcompany.name
        )

        locale.setlocale(locale.LC_MONETARY, "pt_BR.UTF-8")
        debounce_data = {
            "hired": hired,
            "total_price": locale.currency(instance.total_price, grouping=True),
            "creation_date": instance.creation_date.strftime("%d/%m/%Y"),
            "measurement_date": instance.measurement_date.strftime("%d/%m/%Y"),
            "status": instance.approval_step.name,
            "description": description,
            "period": period,
            "accounting_classification": instance.extra_info.get(
                "accounting_classification", ""
            ),
            "comments": instance.description,
            "url": url,
            "company_id": str(company_id),
        }

        add_debounce_data(user_notifs, debounce_data)


def notify_resources_pending_approval():
    """
    Gather all Resources pending approval and notify the users.

    Called every Monday 07:30 by AWS SQS.

    Groups results of multiple Company instances.

    Does not follow the regular notification flow.

    WARNING: If ProcedureResourceView.get_queryset() method changes, it will be necessary to update the logic in this function
    """

    NOTIFICATION_AREA = "recursos.aprovacao_de_recursos"
    TEMPLATE_PATH = "service_orders/email/resource_approval"

    user_notifs = UserNotification.objects.filter(notification=NOTIFICATION_AREA)

    if user_notifs:
        # Only query ProcedureResource from relevant Company instances (and remove duplicates)
        relevant_companies_ids = list(
            set(user_notifs.values_list("companies", flat=True))
        )

        pending_proc_resources = ProcedureResource.objects.filter(
            # Not approved yet
            approval_status=resource_approval_status.WAITING_APPROVAL,
            # And part of the UserNotification Company list
            service_order_resource__resource__company__in=relevant_companies_ids,
        )

        # Batch raw data serialization
        # NOTE: Use this as reference of the structure
        serialized_proc_res = pending_proc_resources.values(
            # ProcedureResource
            proc_res_uuid=F("uuid"),
            proc_res_amount=F("amount"),
            # ServiceOrderResource
            sor_unit_price=F("service_order_resource__unit_price"),
            # Resource
            resource_name=F("service_order_resource__resource__name"),
            resource_unit=F("service_order_resource__resource__unit"),
            resource_company_uuid=F("service_order_resource__resource__company"),
            resource_company_name=F("service_order_resource__resource__company__name"),
            # Contract
            contract_uuid=F("service_order_resource__contract"),
            contract_name=F("service_order_resource__contract__name"),
            contract_firm_name=F("service_order_resource__contract__firm__name"),
            contract_subcompany_name=F(
                "service_order_resource__contract__subcompany__name"
            ),
            contract_r_c_number=F(
                "service_order_resource__contract__extra_info__r_c_number"
            ),
            created_by_user=F("created_by_id"),
        )

        # Group serialized data
        locale.setlocale(locale.LC_MONETARY, "pt_BR.UTF-8")
        contract_to_proc_res: Dict[str, Dict[str, Any]] = defaultdict(dict)
        for proc_res in serialized_proc_res:
            company_id = str(proc_res["resource_company_uuid"])
            contract_id = str(proc_res["contract_uuid"])

            # Determine the provider name
            firm_name = proc_res["contract_firm_name"] or ""
            subcompany_name = proc_res["contract_subcompany_name"] or ""
            provider_name = subcompany_name or firm_name

            # Build Contract data
            if contract_id not in contract_to_proc_res:
                r_c_number = (
                    proc_res["contract_r_c_number"].get("r_c_number", "")
                    if proc_res["contract_r_c_number"] is not None
                    else ""
                )
                contract_title = (
                    "{} - Objeto Nº {} - Descrição: {} - Fornecedor: {}".format(
                        proc_res["resource_company_name"] or "",
                        r_c_number,
                        proc_res["contract_name"] or "",
                        provider_name,
                    )
                )
                contract_url = "{}/#/SharedLink/Contract/{}/show?company={}".format(
                    settings.FRONTEND_URL, contract_id, company_id
                )

                contract_to_proc_res[contract_id] = {
                    "title": contract_title,
                    "url": contract_url,
                    "company_id": company_id,
                    "procedure_resources": {},
                }

            # Build ProcedureResource data (contract_id -> procedure_resources[proc_res_id])
            proc_res_id = str(proc_res["proc_res_uuid"])
            if (
                proc_res_id
                not in contract_to_proc_res[contract_id]["procedure_resources"]
            ):
                item = proc_res["resource_name"] or ""
                amount = proc_res["proc_res_amount"] or 0
                unit = proc_res["resource_unit"] or ""
                unit_price = proc_res["sor_unit_price"] or 0
                total_price = amount * unit_price

                contract_to_proc_res[contract_id]["procedure_resources"][
                    proc_res_id
                ] = {
                    "item": item,
                    "amount": f"{amount} {unit}",
                    "unit_price": locale.currency(unit_price, grouping=True),
                    "total_price": locale.currency(total_price, grouping=True),
                    "created_by": str(proc_res["created_by_user"]),
                }

        # Send the notifications for the active UserNotification instances
        for user_notif in user_notifs:
            user = user_notif.user
            rep_company = user_notif.companies.first()
            companies_ids = [
                str(company_id)
                for company_id in user_notif.companies.values_list("uuid", flat=True)
            ]

            # Get a Contract only if the Company is related to the UserNotification
            user_contracts = {
                contract_id: contract_data
                for contract_id, contract_data in contract_to_proc_res.items()
                if contract_data["company_id"] in companies_ids
            }

            if user_contracts:
                queryset = PermissionManager(
                    user=user,
                    company_ids=rep_company,
                    model="ProcedureResource",
                ).get_allowed_queryset()
                if "self" in queryset:
                    user_contracts = {
                        contract_id: contract_data
                        for contract_id, contract_data in user_contracts.items()
                        for proc_id, proc_data in contract_data[
                            "procedure_resources"
                        ].items()
                        if proc_data["created_by"] == str(user.pk)
                    }
                elif "firm" in queryset:
                    user_firms = user.user_firms.filter(company__uuid__in=companies_ids)
                    users_firms_pks = [
                        str(a)
                        for a in set(
                            UserInFirm.objects.filter(firm__in=user_firms).values_list(
                                "user_id", flat=True
                            )
                        )
                    ]
                    user_contracts = {
                        contract_id: contract_data
                        for contract_id, contract_data in user_contracts.items()
                        for proc_id, proc_data in contract_data[
                            "procedure_resources"
                        ].items()
                        if proc_data["created_by"] == str(user.pk)
                        or proc_data["created_by"] in users_firms_pks
                    }
                elif "none" in queryset:
                    continue
                if user_contracts:
                    disclaimer_msg, _ = get_disclaimer(rep_company.company_group)
                    context = {
                        "title": "Kartado - Aprovação de recursos",
                        "contracts": user_contracts,
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


# Zappa alias: function path must be ≤63 chars (0.61.x validation)
def notify_resources_approval():
    return notify_resources_pending_approval()
