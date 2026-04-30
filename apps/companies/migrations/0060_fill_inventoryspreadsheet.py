from django.db import migrations
from django_bulk_update.helper import bulk_update

from helpers.strings import get_obj_from_path


def fill_inventory_spreadsheet(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")

    company_qs = Company.objects.using(db_alias).all()

    updated_items = []

    for company in company_qs:
        possible_path = "inventory__exporter__extracolumns"
        extra_columns = get_obj_from_path(company.custom_options, possible_path)

        if extra_columns:
            company.custom_options["inventorySpreadsheet"] = {}
            company.custom_options["inventorySpreadsheet"][
                "extra_columns"
            ] = extra_columns
            updated_items.append(company)

    bulk_update(updated_items, batch_size=1000, update_fields=["custom_options"])


class Migration(migrations.Migration):
    dependencies = [("companies", "0059_merge_20230918_1024")]

    operations = [
        migrations.RunPython(
            fill_inventory_spreadsheet, reverse_code=migrations.RunPython.noop
        )
    ]
