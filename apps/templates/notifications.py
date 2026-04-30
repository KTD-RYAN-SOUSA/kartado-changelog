from datetime import timedelta
from urllib import parse

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver
from django.utils import timezone

from apps.reportings.models import Reporting
from helpers.notifications import create_notifications
from helpers.signals import disable_signal_for_loaddata

from .models import MobileSync


def send_email_reporting_export(instance):
    try:
        """Envia email com link de download do arquivo Excel gerado no Fargate."""
        if not instance.created_by:
            return

        params = {}
        params["Bucket"] = instance.exported_file.storage.bucket.name
        params["Key"] = "media/private/{}".format(instance.exported_file.name)
        download_url = (
            instance.exported_file.storage.bucket.meta.client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=604800
            )
        )  # seven days

        label = "Inventário" if instance.is_inventory else "Apontamentos"
        context = {
            "title": "Exportação de {} pronta para download.".format(label),
            "url": download_url,
            "link": True,
            "message": "Sua exportação de {} foi concluída. Clique abaixo para realizar o download:".format(
                label.lower()
            ),
            "url_front": "{}/#/SharedLink/ReportingExport/{}/show/?company={}".format(
                settings.FRONTEND_URL,
                str(instance.uuid),
                str(instance.company.uuid),
            ),
            "disclaimer_approval_title": "",
            "disclaimer_approval": "",
        }

        create_notifications(
            [instance.created_by],
            instance.company,
            context,
            "templates/email/zip_email",
            push=False,
            instance=instance,
        )
    except Exception as e:
        print("Export Teste Error - send_email_reporting_export", e)


def send_email_export_request(instance):
    # Get context
    if instance.done:
        tarefa = "Arquivo zip pronto para download."
        message = "Por favor, clique abaixo para realizar o download:"
        link = True
    else:
        tarefa = "Erro no arquivo zip."
        message = "Ocorreu um erro no arquivo zip. Por favor, contate a nossa equipe."
        link = False
    params = {}
    params["Bucket"] = instance.file.storage.bucket.name
    params["Key"] = "media/private/{}".format(instance.file.name)
    download_url = instance.file.storage.bucket.meta.client.generate_presigned_url(
        "get_object", Params=params, ExpiresIn=604800
    )  # seven days, but the url will expire in 6 hours
    context = {
        "title": tarefa,
        "url": download_url,
        "link": link,
        "message": message,
        "url_front": "{}/#/SharedLink/ExportRequest/{}/show/?company={}".format(
            settings.FRONTEND_URL,
            str(instance.uuid),
            str(instance.company.uuid),
        ),
    }

    # Get templates path
    template_path = "templates/email/zip_email"

    # Create a email
    create_notifications(
        [instance.created_by],
        instance.company,
        context,
        template_path,
        push=False,
        instance=instance,
    )


def email_mobile_sync(instance):
    """
    When a MobileSync is marked as done, send out a notification to any
    users specified as key_users of that Company, letting them know that
    a sync has been completed.
    """
    # Get Company
    company = instance.company

    # Send to
    send_to = company.key_users.all().distinct()

    # Reportings
    reportings = Reporting.objects.filter(
        company=company, historicalreporting__mobile_sync_id=instance.pk
    ).distinct()

    if reportings and send_to:
        # Build query filter
        query = parse.quote("{" + '"mobile_sync":["' + str(instance.pk) + '"]' + "}")

        # Create url
        url = "{}/#/SharedLink/Reporting/?filter={}&company={}".format(
            settings.FRONTEND_URL, query, str(company.uuid)
        )

        # Get context
        user_name = instance.created_by.get_full_name()
        nb_reportings = reportings.count()

        if instance.done:
            title = "Nova sincronização de {}.".format(user_name)
            message = "O usuário {} sincronizou {} apontamentos.".format(
                user_name, nb_reportings
            )
        else:
            title = "Nova sincronização incompleta de {}".format(user_name)
            message = "O usuário {} sincronizou {} apontamentos, porém a sincronização não foi concluída com sucesso.".format(
                user_name, nb_reportings
            )

        context = {"title": title, "message": message, "url": url}

        # Get templates path
        template_path = "templates/email/mobile_sync_done"

        # Create a email for each user
        create_notifications(
            send_to, company, context, template_path, instance=instance, url=url
        )

    # Update email_sent
    instance.email_sent = True
    instance.save()


@receiver(post_save, sender=MobileSync)
@disable_signal_for_loaddata
def call_email_mobile_sync(sender, instance, created, **kwargs):
    if instance.done and not instance.email_sent:
        email_mobile_sync(instance)


def call_email_mobile_sync_not_done():
    """
    A function called every 30 minutes to check if any MobileSync
    was created and the field done remains False for over one hour
    to send a notification
    """
    diff_hours = 1
    timecheck = timezone.now() - timedelta(hours=diff_hours)
    mobile_syncs = MobileSync.objects.filter(
        done=False, created_at__lte=timecheck, email_sent=False
    ).distinct()
    for instance in mobile_syncs:
        email_mobile_sync(instance)
