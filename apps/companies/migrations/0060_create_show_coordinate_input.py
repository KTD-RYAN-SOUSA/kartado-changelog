from django.db import migrations
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def populate_metadata_with_show_coordinate_input(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    company_qs = Company.objects.using(db_alias).all()

    updated_items = []

    for company in tqdm(company_qs):
        company.metadata["show_coordinate_input"] = False
        updated_items.append(company)

    bulk_update(updated_items, batch_size=100, update_fields=["metadata"])


def reverse_populate_metadata_with_show_coordinate_input(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    company_qs = Company.objects.using(db_alias).all()

    updated_items = []

    for company in company_qs:
        if "show_coordinate_input" in company.metadata:
            del company.metadata["show_coordinate_input"]
            updated_items.append(company)

    bulk_update(updated_items, batch_size=100, update_fields=["metadata"])


class Migration(migrations.Migration):
    dependencies = [("companies", "0059_merge_20230918_1024")]
    operations = [
        migrations.RunPython(
            populate_metadata_with_show_coordinate_input,
            reverse_code=reverse_populate_metadata_with_show_coordinate_input,
        )
    ]
