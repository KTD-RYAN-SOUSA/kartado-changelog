from django.db import migrations
from django_bulk_update.helper import bulk_update

from helpers.strings import get_obj_from_path


def fill_reporting_spreadsheet(apps, schema_editor):

    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")

    company_qs = Company.objects.using(db_alias).all()

    updated_items = []

    for company in company_qs:

        possible_path = "reporting__exporter__extracolumns"
        extra_columns = get_obj_from_path(company.custom_options, possible_path)

        if extra_columns:
            company.custom_options["reportingSpreadsheet"] = {}
            company.custom_options["reportingSpreadsheet"][
                "extra_columns"
            ] = extra_columns
            updated_items.append(company)

    bulk_update(updated_items, batch_size=1000, update_fields=["custom_options"])


class Migration(migrations.Migration):

    dependencies = [("companies", "0055_auto_20230315_0030")]

    operations = [
        migrations.RunPython(
            fill_reporting_spreadsheet, reverse_code=migrations.RunPython.noop
        )
    ]
