from django.db import migrations
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def populate_custom_options_with_artesp_config_v2(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    company_qs = Company.objects.using(db_alias).all()

    updated_items = []

    for company in tqdm(company_qs):
        if "artespIntegration" in company.custom_options:
            company.custom_options["artespIntegration"][
                "artespDefaultFieldsConfig"
            ] = {}
        else:
            company.custom_options["artespIntegration"] = {
                "artespOccurrenceTypeConfig": [],
                "artespFieldsConfig": [],
                "artespDefaultFieldsConfig": {},
            }
        updated_items.append(company)

    bulk_update(updated_items, batch_size=100, update_fields=["custom_options"])


def reverse_populate_custom_options_with_artesp_config_v2(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    company_qs = Company.objects.using(db_alias).all()

    updated_items = []

    for company in tqdm(company_qs):
        if "artespIntegration" in company.custom_options:
            del company.custom_options["artespIntegration"]
            updated_items.append(company)

    bulk_update(updated_items, batch_size=100, update_fields=["custom_options"])


class Migration(migrations.Migration):
    dependencies = [("companies", "0060_fill_artesp_config")]
    operations = [
        migrations.RunPython(
            populate_custom_options_with_artesp_config_v2,
            reverse_code=reverse_populate_custom_options_with_artesp_config_v2,
        )
    ]
