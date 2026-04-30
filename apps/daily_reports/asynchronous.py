import logging

from zappa.asynchronous import task

from apps.daily_reports.models import (
    DailyReport,
    DailyReportRelation,
    MultipleDailyReport,
)
from helpers.apps.daily_reports import create_and_update_contract_usage

logger = logging.getLogger(__name__)


@task
def process_contract_usage_for_report(report_uuid, report_type="multiple"):
    """
    Async task to process DailyReportContractUsage creation for all board items
    related to a specific report (DailyReport or MultipleDailyReport).

    This task is triggered after DailyReportRelation objects are created in
    handle_deferred_serializers.

    Args:
        report_uuid: UUID of the DailyReport or MultipleDailyReport
        report_type: "multiple" for MultipleDailyReport, "single" for DailyReport
    """

    try:
        # Get the report instance
        if report_type == "multiple":
            report = MultipleDailyReport.objects.get(uuid=report_uuid)
            relations = DailyReportRelation.objects.filter(
                multiple_daily_report=report
            ).prefetch_related("worker", "equipment", "vehicle")
        else:  # single
            report = DailyReport.objects.get(uuid=report_uuid)
            relations = DailyReportRelation.objects.filter(
                daily_report=report
            ).prefetch_related("worker", "equipment", "vehicle")

        # Process each relation
        for relation in relations:
            # Process worker
            if relation.worker:
                create_and_update_contract_usage(relation.worker)

            # Process equipment
            if relation.equipment:
                create_and_update_contract_usage(relation.equipment)

            # Process vehicle
            if relation.vehicle:
                create_and_update_contract_usage(relation.vehicle)

    except (DailyReport.DoesNotExist, MultipleDailyReport.DoesNotExist) as e:
        logger.error(
            f"[CONTRACT_USAGE_TASK] Report not found: {report_uuid} - {str(e)}"
        )
    except Exception as e:
        logger.error(
            f"[CONTRACT_USAGE_TASK] Error processing report {report_uuid}: {str(e)}",
            exc_info=True,
        )
