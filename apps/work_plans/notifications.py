from datetime import datetime

import pytz
from django.conf import settings
from django.db.models import prefetch_related_objects
from django.utils.timezone import make_aware

from helpers.notifications import create_single_notification, get_disclaimer


def create_job_email(instance):
    # Default
    worker_name = ""
    firm_name = ""
    watcher_users = []
    watcher_firms = []
    prefetch_related_objects(
        [instance],
        "watcher_firms",
        "watcher_users",
        "worker",
        "firm",
        "firm__manager",
        "company",
        "company__company_group",
    )

    # Get send_to
    send_to = []

    if instance.firm and instance.firm.manager:
        firm_name = instance.firm.name
        send_to.append(instance.firm.manager)
    if instance.worker:
        worker_name = instance.worker.get_full_name()
        send_to.append(instance.worker)

    for watcher_user in instance.watcher_users.all():
        watcher_users.append(watcher_user.get_full_name())
        send_to.append(watcher_user)
    for watcher_firm in instance.watcher_firms.all():
        watcher_firms.append(watcher_firm.name)
        send_to += list(watcher_firm.users.all())

    send_to = list(set([user for user in send_to if user]))

    # Get disclaimer message and mobile_app type
    disclaimer_msg, mobile_app = get_disclaimer(instance.company.company_group)

    # Create url
    url = "{}/#/SharedLink/Job/{}/show?company={}".format(
        settings.FRONTEND_URL, str(instance.uuid), str(instance.company.uuid)
    )

    # Get context
    nb_reportings = instance.reportings.count()
    str_item = "item" if nb_reportings == 1 else "itens"
    nb_reportings_str = "{} {}".format(nb_reportings, str_item)

    push_message = "Nova Programação - {} ({} {})".format(
        instance.title, nb_reportings, str_item
    )
    message_text = "a programação {}, com descrição '{}' e {} {} foi criada e está relacionada a você.".format(
        instance.number, instance.title, str(nb_reportings), str_item
    )
    message_text = (
        message_text + " Para acessá-la, clique no link ou sincronize o aplicativo."
    )

    context = {
        "title": push_message,
        "number": instance.number,
        "description": instance.title,
        "nb_reportings": nb_reportings_str,
        "responsible": worker_name,
        "firm": firm_name,
        "watcher_users": ", ".join(watcher_users),
        "watcher_firms": ", ".join(watcher_firms),
        "url": url,
        "disclaimer": disclaimer_msg,
        "mobile_app": mobile_app,
    }

    template_path = "work_plans/email/job_create"

    for user in send_to:
        complete_message = user.first_name + ", " + message_text
        context = {**context, "message": complete_message}

        create_single_notification(
            user, instance.company, context, template_path, instance=instance, url=url
        )


def update_job_email_func(instance):
    prefetch_related_objects(
        [instance],
        "watcher_firms",
        "watcher_users",
        "worker",
        "firm",
        "firm__manager",
        "company",
        "company__company_group",
    )

    # Get disclaimer message and mobile_app type
    disclaimer_msg, mobile_app = get_disclaimer(instance.company.company_group)

    # Get send_to
    send_to = []
    if instance.firm and instance.firm.manager:
        send_to.append(instance.firm.manager)
    if instance.worker:
        send_to.append(instance.worker)

    send_to += list(instance.watcher_users.all())
    for watcher_firm in instance.watcher_firms.all():
        send_to += list(watcher_firm.users.all())

    send_to = list(set([user for user in send_to if user]))

    # Create url
    url = "{}/#/SharedLink/Job/{}/show?company={}".format(
        settings.FRONTEND_URL, str(instance.uuid), str(instance.company.uuid)
    )

    # Get context
    instance.last_notification_sent_at = make_aware(datetime.now(), timezone=pytz.UTC)

    # Get current progress of the job
    nb_perc_reportings = instance.progress * 100

    push_message = "Programação atualizada - {} ({}%)".format(
        instance.title, nb_perc_reportings
    )

    message_text = (
        "a programação {} - {}, que está relacionada a você, foi atualizada.".format(
            instance.number, instance.title
        )
    )
    message_text = (
        message_text
        + " Para verificar as alterações, clique no link ou sincronize o aplicativo."
    )

    context = {
        "title": push_message,
        "url": url,
        "disclaimer": disclaimer_msg,
        "mobile_app": mobile_app,
    }

    template_path = "work_plans/email/job_update"

    for user in send_to:
        complete_message = user.first_name + ", " + message_text
        context = {**context, "message": complete_message}

        create_single_notification(
            user, instance.company, context, template_path, instance=instance, url=url
        )

    # save last_sent_at
    # this will call update_job_email again, but the diff_hours
    # will avoid creating more emails
    instance.save()


def update_job_email(instance):
    """
    Send it when add a Reporting to a Job.
    Don't send more than one e-mail per Job every hour
    """
    diff_hours = 1
    if not instance.last_notification_sent_at:
        update_job_email_func(instance)
    else:
        timenow = make_aware(datetime.now(), timezone=pytz.UTC)
        try:
            last_sent_at = make_aware(
                instance.last_notification_sent_at, timezone=pytz.UTC
            )
        except ValueError:
            last_sent_at = instance.last_notification_sent_at
        diff = timenow - last_sent_at
        if diff.seconds >= (diff_hours * 3600):
            update_job_email_func(instance)
