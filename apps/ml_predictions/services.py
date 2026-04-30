import logging

from zappa.asynchronous import task

from apps.daily_reports.models import MultipleDailyReport
from helpers.apps.databricks import DatabricksClient

from .models import MLPrediction, MLPredictionConfig

logger = logging.getLogger(__name__)


@task
def fetch_predictions():
    client = DatabricksClient()
    total = 0

    for config in MLPredictionConfig.objects.prefetch_related("company"):
        company = config.company
        try:
            results = client.predict_by_company(str(company.uuid))
            if not results:
                continue
            for item in results:
                rdo_id = item.get("id_rdo") or item.get("idRdo")
                if not rdo_id:
                    continue
                if MLPrediction.objects.filter(
                    company=company, output_data__contains={"id_rdo": rdo_id}
                ).exists():
                    continue
                rdo = MultipleDailyReport.objects.filter(uuid=rdo_id).first()
                MLPrediction.objects.create(
                    company=company, output_data=item, multiple_daily_report=rdo
                )
                total += 1
        except Exception as e:
            logger.error("Erro ML %s: %s", company.name, e)

    return total
