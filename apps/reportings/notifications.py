from collections import defaultdict
from datetime import datetime, timedelta
from urllib import parse

import pytz
from django.conf import settings
from django.db.models import Q

from apps.companies.models import Company, Firm
from apps.reportings.models import HistoricalReporting, Reporting
from apps.users.models import User
from helpers.filters import filter_history
from helpers.notifications import (
    create_notifications,
    create_single_notification,
    get_disclaimer,
)


def reporting_message_created(instance):
    # Get Company
    company = instance.reporting.company

    # Get send_to
    send_to = []

    # Use `list` to force qs evaluation and avoid subqueries in the big send_to query
    # This approach looks ugly but runs very fast
    reporting_messages = list(
        instance.reporting.reporting_messages.values_list("uuid", flat=True)
    )

    send_to_firms = list(
        Firm.objects.filter(
            mentioned_firm_in_messages__in=reporting_messages
        ).values_list("uuid", flat=True)
    )

    send_to = list(
        User.objects.filter(
            Q(reporting_messages__in=reporting_messages)
            | Q(mentioned_in_messages__in=reporting_messages)
            | Q(user_firms__in=send_to_firms)
        )
        .distinct()
        .only("uuid")
    )

    # Create url
    url = "{}/#/SharedLink/Reporting/{}/messages?company={}".format(
        settings.FRONTEND_URL, str(instance.reporting.uuid), str(company.pk)
    )

    # Get context
    tarefa = "Nova mensagem no apontamento {}".format(instance.reporting.number)

    context = {"title": tarefa, "number": instance.reporting.number, "url": url}

    # Get templates path
    template_path = "reportings/email/reporting_message_created"

    # Create a email for each user
    create_notifications(
        send_to, company, context, template_path, instance=instance, url=url
    )


def reporting_approval_step_report_email():
    """
    A periodic notification signalling updates in approval_step
    Call it every Monday at 07:30.
    """
    # import here to prevent recursion error
    from apps.reportings.views import ReportingFilter

    for company in Company.objects.all():
        # Get disclaimer message and mobile_app type
        disclaimer_msg, mobile_app = get_disclaimer(company.company_group)

        # Get reportings by company
        reportings = (
            Reporting.objects.filter(company=company)
            .select_related("status")
            .prefetch_related("historicalreporting__history_user")
        )

        # Reporting objects that had a change in its approval_step in the last week
        today = datetime.now().astimezone(pytz.timezone(settings.TIME_ZONE))
        last_date = today - timedelta(days=7)

        reportings = filter_history(
            last_date,
            today,
            "approval_step_id",
            HistoricalReporting,
            reportings,
        )

        # For every reporting, get the created_by and all the
        # users that have changed the reporting in the past

        created_bys = list(
            User.objects.filter(reportings__in=reportings).values_list(
                "uuid", flat=True
            )
        )
        users_in_histories = list(
            HistoricalReporting.objects.filter(uuid__in=reportings).values_list(
                "history_user_id", flat=True
            )
        )

        users_list = User.objects.filter(
            uuid__in=created_bys + users_in_histories
        ).distinct()

        reporting_filter = ReportingFilter()

        title = "Relatório do Fluxo de Aprovação."
        message = "Apontamentos que tiveram alteração no status de aprovação entre os dias {} e {}:".format(
            last_date.strftime("%d/%m/%Y"), today.strftime("%d/%m/%Y")
        )

        context = {
            "title": title,
            "message": message,
            "disclaimer": disclaimer_msg,
            "html_table": True,
            "mobile_app": mobile_app,
        }

        template_path = "reportings/email/reporting_approval_step"

        # Send email for every user
        for user in users_list:
            user_id = str(user.pk)
            reportings_list = reporting_filter.get_only_related_to(
                reportings, name="", value=user_id
            )

            reportings_final = [
                {
                    "number": reporting.number,
                    "status": reporting.status.name if reporting.status else "",
                    "step": reporting.approval_step.name
                    if reporting.approval_step
                    else "",
                    "notes": reporting.form_data["notes"]
                    if "notes" in reporting.form_data
                    else "",
                }
                for reporting in reportings_list
            ]

            if reportings_final:
                # Create url
                query = (
                    "{"
                    + '"approval_step_changed_date":"'
                    + today.strftime("%Y-%m-%d")
                    + '",'
                    + '"only_related_to":["'
                    + user_id
                    + '"]'
                    + "}"
                )
                url = "{}/#/SharedLink/Reporting/?filter={}&company={}".format(
                    settings.FRONTEND_URL, parse.quote(query), str(company.uuid)
                )

                context = {
                    **context,
                    "reportings": reportings_final,
                    "url": url,
                }

                create_single_notification(
                    user, company, context, template_path, push=False
                )


def reporting_job_email():
    """
    A periodic notification for every Job that had their related
    Reporting objects updated since the last notification.
    Call it every Monday at 7h30m.
    """
    now = datetime.now().astimezone(pytz.timezone(settings.TIME_ZONE))
    last_date = now - timedelta(days=7)

    title = "Relatório de programações - {} a {}.".format(
        last_date.strftime("%d/%m"), now.strftime("%d/%m")
    )
    message = "Entre os dias {} a {}, as seguintes programações às quais você está relacionado tiveram atualizações em seus apontamentos:".format(
        last_date.strftime("%d/%m"), now.strftime("%d/%m")
    )

    template_path = "reportings/email/reporting_job_email"

    for company in Company.objects.all():
        # Get disclaimer message and mobile_app type
        disclaimer_msg, mobile_app = get_disclaimer(company.company_group)

        # Get reportings
        reportings = (
            Reporting.objects.filter(
                company=company,
                updated_at__lte=now,
                updated_at__gt=last_date,
                job__isnull=False,
            )
        ).prefetch_related(
            "historicalreporting__history_user",
            "status",
            "job",
            "job__created_by",
            "job__watcher_users",
            "job__worker",
            "job__watcher_firms__users",
            "job__firm__users",
            "job__watcher_subcompanies",
        )

        if reportings.exists():
            # Get reportings by job
            jobs_and_reportings = defaultdict(list)
            for item in reportings:
                jobs_and_reportings[item.job].append(item)

            # Get jobs by user
            users_and_jobs = defaultdict(list)
            all_jobs = jobs_and_reportings.keys()
            for job in all_jobs:
                all_users = []
                all_users.append(job.created_by)
                all_users.append(job.worker)
                all_users += list(job.firm.users.all())
                all_users += list(job.watcher_users.all())
                for firm in job.watcher_firms.all():
                    all_users += list(firm.users.all())
                for subcompany in job.watcher_subcompanies.all():
                    for firm in subcompany.subcompany_firms.all():
                        all_users += list(firm.users.all())
                for user in list(set(all_users)):
                    users_and_jobs[user].append(job)

            context = {
                "title": title,
                "message": message,
                "disclaimer": disclaimer_msg,
                "html_table": True,
                "mobile_app": mobile_app,
            }

            # Send email for every user
            for user, jobs_list in users_and_jobs.items():

                jobs_final = [
                    {
                        "url": "{}/#/SharedLink/Job/{}/show?company={}".format(
                            settings.FRONTEND_URL,
                            str(job.uuid),
                            str(company.uuid),
                        ),
                        "title": job.title,
                        "reportings": [
                            {
                                "number": reporting.number,
                                "status": reporting.status.name
                                if reporting.status
                                else "",
                                "notes": reporting.form_data["notes"]
                                if "notes" in reporting.form_data
                                else "",
                            }
                            for reporting in jobs_and_reportings[job]
                        ],
                    }
                    for job in jobs_list
                    if jobs_and_reportings[job]
                ]

                if jobs_final:
                    context = {**context, "jobs": jobs_final}

                    create_single_notification(
                        user, company, context, template_path, push=False
                    )


# Zappa alias: function path must be ≤63 chars (0.61.x validation)
def approval_step_report_email():
    return reporting_approval_step_report_email()
