from django.conf import settings

from helpers.notifications import create_notifications


def monitoring_cycle_email(instance):
    # Get company
    company = instance.monitoring_plan.company

    # Check is_not_notified flag
    if instance.monitoring_plan.is_not_notified:
        return

    # Get send_to
    send_to = []
    for user in instance.responsibles.all():
        send_to.append(user)

    # Create url
    url = "{}/#/SharedLink/MonitoringPlan/{}/show?company={}".format(
        settings.FRONTEND_URL,
        str(instance.monitoring_plan.uuid),
        str(company.uuid),
    )

    # Get context
    tarefa = "Plano de Monitoramento {} atualizado.".format(
        instance.monitoring_plan.number
    )

    context = {
        "title": tarefa,
        "number": instance.monitoring_plan.number,
        "url": url,
    }

    # Get templates path
    template_path = "monitorings/email/monitoring_cycle_email"

    # Create a email for each user
    create_notifications(
        send_to, company, context, template_path, instance=instance, url=url
    )
