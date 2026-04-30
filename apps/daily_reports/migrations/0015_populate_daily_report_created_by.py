from django.db import migrations
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def determine_daily_report_creator_field(apps, schema_editor):
    """
    Search inside the DailyReport's history to determine the user who created it
    and set the created_by field for existing DailyReports
    """

    db_alias = schema_editor.connection.alias
    DailyReport = apps.get_model("daily_reports", "DailyReport")
    HistoricalDailyReport = apps.get_model("daily_reports", "HistoricalDailyReport")
    reports = DailyReport.objects.using(db_alias).filter(created_by__isnull=True)

    # List of updated reports
    updated_reports = []

    for report in tqdm(reports):
        creator = HistoricalDailyReport.objects.get(
            uuid=report.uuid, history_type="+"
        ).history_user

        if creator is not None:
            report.created_by = creator

            # Add to updated reports
            updated_reports.append(report)

    # Bulk update the reports in updated_reports
    bulk_update(updated_reports, batch_size=2000, update_fields=["created_by"])


def reset_daily_report_creator_field(apps, schema_editor):
    """
    Undoes all the changes made in determine_daily_report_creator_field
    """

    db_alias = schema_editor.connection.alias
    DailyReport = apps.get_model("daily_reports", "DailyReport")
    reports = DailyReport.objects.using(db_alias).filter(created_by__isnull=False)

    # List of updated reports
    updated_reports = []

    for report in tqdm(reports):
        report.created_by = None
        updated_reports.append(report)

    # Bulk update the reports in updated_reports
    bulk_update(updated_reports, batch_size=2000, update_fields=["created_by"])


class Migration(migrations.Migration):

    dependencies = [("daily_reports", "0014_auto_20210525_0849")]

    operations = [
        migrations.RunPython(
            determine_daily_report_creator_field,
            reverse_code=reset_daily_report_creator_field,
        )
    ]
