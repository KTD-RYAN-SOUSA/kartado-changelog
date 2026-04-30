from django.db import migrations
from django_bulk_update.helper import bulk_update
from tqdm import tqdm

PARAMETER_KEY = "max_reportings_by_job"
PARAMETER_VALUE = 250


def add_max_reportings_by_job(apps, schema_editor):
    """
    Add max_reportings_by_job parameter to all Company instances.
    """

    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    companies = Company.objects.using(db_alias).all().only("uuid", "metadata")
    updated_companies = []

    for company in tqdm(companies):
        company.metadata[PARAMETER_KEY] = PARAMETER_VALUE
        updated_companies.append(company)

    bulk_update(updated_companies, batch_size=2000, update_fields=["metadata"])


def revert_add_max_reportings_by_job(apps, schema_editor):
    """
    Undo the changes made in add_max_reportings_by_job.
    """

    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    companies = Company.objects.using(db_alias).all().only("uuid", "metadata")
    updated_companies = []

    for company in tqdm(companies):
        del company.metadata[PARAMETER_KEY]
        updated_companies.append(company)

    bulk_update(updated_companies, batch_size=2000, update_fields=["metadata"])


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0059_merge_20230918_1024"),
    ]

    operations = [
        migrations.RunPython(
            add_max_reportings_by_job, reverse_code=revert_add_max_reportings_by_job
        )
    ]
