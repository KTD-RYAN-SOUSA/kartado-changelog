from django.conf import settings
from zappa.asynchronous import task

from apps.companies.models import Firm
from apps.daily_reports.models import (
    DailyReportOccurrence,
    DailyReportWorker,
    MultipleDailyReport,
)
from apps.monitorings.models import OperationalControl
from apps.quality_control.models import QualityProject
from apps.users.models import User
from helpers.notifications import create_push_notifications


@task
def verify_firm_deletion(instance_uuid, user_uuid):
    firm = Firm.objects.get(uuid=instance_uuid)
    user = User.objects.get(uuid=user_uuid)

    firm_company = firm.company

    mdr_exists = MultipleDailyReport.objects.filter(firm=firm).exists()
    worker_exists = DailyReportWorker.objects.filter(firm=firm).exists()
    occurrence_exists = DailyReportOccurrence.objects.filter(firm=firm).exists()
    project_exists = QualityProject.objects.filter(firm=firm).exists()
    operational_exists = OperationalControl.objects.filter(firm=firm).exists()

    url = "{}/#/SharedLink/Firm?company={}".format(
        settings.FRONTEND_URL, str(firm_company.pk)
    )

    if any(
        [
            mdr_exists,
            worker_exists,
            occurrence_exists,
            project_exists,
            operational_exists,
        ]
    ):
        firm.delete_in_progress = False
        firm.active = False
        firm.save()
        create_push_notifications(
            [user],
            f'Não foi possível excluir a equipe "{firm.name}"',
            firm_company,
            firm,
            url,
        )
    else:
        create_push_notifications(
            [user],
            f'Exclusão da equipe "{firm.name}" foi realizada',
            firm_company,
            firm,
            url,
        )
        firm.delete()
