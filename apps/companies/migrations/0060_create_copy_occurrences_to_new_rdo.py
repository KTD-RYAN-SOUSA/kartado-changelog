from django.db import migrations
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def populate_metadata_with_copy_occurrences_to_new_rdo(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    company_qs = Company.objects.using(db_alias).all()
    updated_items = []
    for company in tqdm(company_qs):
        company.metadata["copy_occurrences_to_new_rdo"] = True
        updated_items.append(company)
    bulk_update(updated_items, batch_size=100, update_fields=["metadata"])


def reverse_populate_metadata_with_copy_occurrences_to_new_rdo(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    company_qs = Company.objects.using(db_alias).all()
    updated_items = []
    for company in company_qs:
        if "copy_occurrences_to_new_rdo" in company.metadata:
            del company.metadata["copy_occurrences_to_new_rdo"]
            updated_items.append(company)
    bulk_update(updated_items, batch_size=100, update_fields=["metadata"])


class Migration(migrations.Migration):
    dependencies = [("companies", "0059_merge_20230918_1024")]
    operations = [
        migrations.RunPython(
            populate_metadata_with_copy_occurrences_to_new_rdo,
            reverse_code=reverse_populate_metadata_with_copy_occurrences_to_new_rdo,
        )
    ]
