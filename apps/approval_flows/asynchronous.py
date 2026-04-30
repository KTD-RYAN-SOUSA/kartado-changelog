from collections import defaultdict

from django.conf import settings

from apps.companies.models import Company, SubCompany
from apps.daily_reports.models import MultipleDailyReport
from apps.reportings.models import Reporting
from helpers.notifications import create_single_notification
from helpers.strings import get_obj_from_path

FREQUENCY_TRANSLATION = {"daily": "diária", "weekly": "semanal"}


def reporting_approval_daily():
    send_reporting_approval_notifications("daily")


def reporting_approval_weekly():
    send_reporting_approval_notifications("weekly")


def daily_report_approval_daily():
    send_mdr_notifications("daily")


def daily_report_approval_weekly():
    send_mdr_notifications("weekly")


def send_reporting_approval_notifications(frequency):

    TEMPLATE_PATH = "reportings/email/reporting_approval_notifications"

    frequency_text = FREQUENCY_TRANSLATION.get(frequency, "")
    companies = Company.objects.filter(
        custom_options__has_key="approvalNotificationsRules"
    ).filter(custom_options__approvalNotificationsRules__reporting__frequency=frequency)

    for company in companies:
        flows = get_obj_from_path(
            company.custom_options, "approvalnotificationsrules__reporting__web__flows"
        )
        reportings = (
            Reporting.objects.filter(
                company=company,
                created_at__year__gte=2025,
                approval_step__uuid__in=flows,
            )
            .order_by("created_at")
            .prefetch_related(
                "firm",
                "firm__subcompany",
                "occurrence_type",
                "created_by",
                "approval_step",
                "approval_step__responsible_firms",
                "approval_step__responsible_firms__users",
                "approval_step__responsible_firms__manager",
                "approval_step__responsible_users",
            )
            .only(
                "uuid",
                "company",
                "number",
                "firm",
                "firm__subcompany",
                "occurrence_type",
                "created_by",
                "approval_step",
                "approval_step__responsible_firms",
                "approval_step__responsible_firms__users",
                "approval_step__responsible_firms__manager",
                "approval_step__responsible_users",
            )
        )

        show_subcompany = SubCompany.objects.filter(company=company).exists()
        approval_users = defaultdict(lambda: defaultdict(list))
        for reporting in reportings:
            reporting_data = {}
            approval_step = reporting.approval_step
            reporting_data.update(
                {
                    "number": reporting.number,
                    "firm": reporting.firm.name if reporting.firm else "",
                    "occurrence_type": reporting.occurrence_type.name
                    if reporting.occurrence_type
                    else "",
                    "approval_step": approval_step.name,
                    "url": "{}/#/SharedLink/Reporting/{}/?company={}".format(
                        settings.FRONTEND_URL,
                        str(reporting.uuid),
                        str(reporting.company.pk),
                    ),
                }
            )
            if reporting.firm and reporting.firm.subcompany:
                reporting_data.update({"subcompany": reporting.firm.subcompany.name})

            approval_step_uuid = str(approval_step.uuid)
            for user in approval_step.responsible_users.all():
                approval_users[user][approval_step_uuid].append(reporting_data)

            for firm in approval_step.responsible_firms.all():
                if (
                    firm.manager
                    and reporting_data
                    not in approval_users[firm.manager][approval_step_uuid]
                ):
                    approval_users[firm.manager][approval_step_uuid].append(
                        reporting_data
                    )
                for user in firm.users.all():
                    if reporting_data not in approval_users[user][approval_step_uuid]:
                        approval_users[user][approval_step_uuid].append(reporting_data)
            if (
                approval_step.responsible_created_by
                and reporting.created_by
                and reporting_data
                not in approval_users[reporting.created_by][approval_step_uuid]
            ):
                approval_users[reporting.created_by][approval_step_uuid].append(
                    reporting_data
                )

        context = {
            "title": "Kartado - Informações sobre apontamentos",
            "message": "Segue atualização {} de aprovação dos apontamentos".format(
                frequency_text
            ),
            "show_subcompany": show_subcompany,
        }

        for user, approval_data in approval_users.items():
            context.update({"reporting_approval_data": dict(approval_data)})
            create_single_notification(
                user=user,
                company=company,
                context=context,
                template_path=TEMPLATE_PATH,
                push=False,
            )


def send_mdr_notifications(frequency):
    TEMPLATE_PATH = "email/mdr_approval_notifications"

    frequency_text = FREQUENCY_TRANSLATION.get(frequency, "")
    companies = Company.objects.filter(
        custom_options__has_key="approvalNotificationsRules"
    ).filter(
        custom_options__approvalNotificationsRules__multipleDailyReport__frequency=frequency
    )

    for company in companies:
        flows = get_obj_from_path(
            company.custom_options,
            "approvalnotificationsrules__multipledailyreport__web__flows",
        )
        mdrs = (
            MultipleDailyReport.objects.filter(
                company=company,
                created_at__year__gte=2025,
                approval_step__uuid__in=flows,
            )
            .order_by("date")
            .prefetch_related(
                "firm",
                "firm__subcompany",
                "created_by",
                "approval_step",
                "approval_step__responsible_firms",
                "approval_step__responsible_firms__users",
                "approval_step__responsible_firms__manager",
                "approval_step__responsible_users",
            )
            .only(
                "uuid",
                "company",
                "number",
                "firm",
                "firm__subcompany",
                "created_by",
                "approval_step",
                "approval_step__responsible_firms",
                "approval_step__responsible_firms__users",
                "approval_step__responsible_firms__manager",
                "approval_step__responsible_users",
            )
        )
        approval_users = defaultdict(lambda: defaultdict(list))
        for mdr in mdrs:
            approval_step = mdr.approval_step
            mdr_data = {}
            mdr_data.update(
                {
                    "number": mdr.number,
                    "firm": mdr.firm.name if mdr.firm else "",
                    "subcompany": mdr.firm.subcompany.name
                    if mdr.firm.subcompany
                    else "",
                    "approval_step": approval_step.name,
                    "date": mdr.date.strftime("%d-%m-%Y") if mdr.date else "",
                    "url": "{}/#/SharedLink/MultipleDailyReport/{}/?company={}".format(
                        settings.FRONTEND_URL,
                        str(mdr.uuid),
                        str(mdr.company.pk),
                    ),
                }
            )

            approval_step_uuid = str(approval_step.uuid)

            for user in approval_step.responsible_users.all():
                approval_users[user][approval_step_uuid].append(mdr_data)

            for firm in approval_step.responsible_firms.all():
                if (
                    firm.manager
                    and mdr_data not in approval_users[firm.manager][approval_step_uuid]
                ):
                    approval_users[firm.manager][approval_step_uuid].append(mdr_data)
                for user in firm.users.all():
                    if mdr_data not in approval_users[user][approval_step_uuid]:
                        approval_users[user][approval_step_uuid].append(mdr_data)
            if (
                approval_step.responsible_created_by
                and mdr.created_by
                and mdr_data not in approval_users[mdr.created_by][approval_step_uuid]
            ):
                approval_users[mdr.created_by][approval_step_uuid].append(mdr_data)

        context = {
            "title": "Kartado - Informações sobre RDOs",
            "message": "Segue atualização {} de aprovação dos RDOs".format(
                frequency_text
            ),
        }

        for user, approval_data in approval_users.items():
            context.update({"mdr_approval_data": dict(approval_data)})
            create_single_notification(
                user=user,
                company=company,
                context=context,
                template_path=TEMPLATE_PATH,
                push=False,
            )
