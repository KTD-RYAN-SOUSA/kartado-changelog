from django.db import migrations
from django.db.models import Prefetch
from django_bulk_update.helper import bulk_update
from tqdm import tqdm

from helpers.apps.job import calculate_fields as cal_fields


def calculate_fields(apps, schema_editor):
    """
    Does the same as the update_calculated_fields signal
    but needed since migrations don't trigger signals
    """

    db_alias = schema_editor.connection.alias

    # Models
    Job = apps.get_model("work_plans", "Job")
    ServiceOrderActionStatus = apps.get_model(
        "service_orders", "ServiceOrderActionStatus"
    )
    ServiceOrderActionStatusSpecs = apps.get_model(
        "service_orders", "ServiceOrderActionStatusSpecs"
    )

    # Get all jobs
    jobs = Job.objects.using(db_alias).all().prefetch_related("company")

    # List of updated jobs
    updated_jobs = []

    for job in tqdm(jobs):
        # Prepare the data

        # Get all the reportings and prefetch the related data
        reportings = job.reportings.all().prefetch_related(
            Prefetch(
                "status",
                queryset=ServiceOrderActionStatus.objects.all().only("uuid"),
            ),
            Prefetch(
                "status__status_specs",
                queryset=ServiceOrderActionStatusSpecs.objects.all().only(
                    "uuid", "order", "status"
                ),
            ),
        )

        # Get the job company
        company = job.company

        # Calculate the fields
        progress, executed_reportings, reporting_count = cal_fields(reportings, company)

        # Set the new values
        job.progress = progress
        job.executed_reportings = executed_reportings
        job.reporting_count = reporting_count

        # Add to updated jobs
        updated_jobs.append(job)

    # Bulk update the jobs in updated_jobs
    bulk_update(
        updated_jobs,
        batch_size=2000,
        update_fields=["progress", "executed_reportings", "reporting_count"],
    )


def uncalculate_fields(apps, schema_editor):
    """
    Undoes all the changes made in calculate_fields
    """

    db_alias = schema_editor.connection.alias
    Job = apps.get_model("work_plans", "Job")
    jobs = Job.objects.using(db_alias).all()

    # List of updated jobs
    updated_jobs = []

    for job in tqdm(jobs):
        job.progress = 0
        job.executed_reportings = 0
        job.reporting_count = 0

        updated_jobs.append(job)

    # Bulk update the jobs in updated_jobs
    bulk_update(
        updated_jobs,
        batch_size=2000,
        update_fields=["progress", "executed_reportings", "reporting_count"],
    )


class Migration(migrations.Migration):

    dependencies = [
        ("work_plans", "0011_auto_20210330_0826"),
    ]

    operations = [
        migrations.RunPython(calculate_fields, reverse_code=uncalculate_fields)
    ]
