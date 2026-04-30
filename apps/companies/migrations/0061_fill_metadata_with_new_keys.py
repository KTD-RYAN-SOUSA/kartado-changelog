from django.db import migrations
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def populate_metadata_with_new_keys(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    company_qs = Company.objects.using(db_alias).all()

    updated_items = []

    for company in tqdm(company_qs):
        if company.company_group and company.company_group.mobile_app == "road":
            company.metadata["use_reporting_inventory_dashboard_shape_list"] = False
            company.metadata["toggle_dashboard_new_shape_update"] = False
            updated_items.append(company)

    if updated_items:
        bulk_update(updated_items, batch_size=100, update_fields=["metadata"])


def reverse_populate_metadata_with_new_keys(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    company_qs = Company.objects.using(db_alias).all()

    updated_items = []

    for company in company_qs:
        if company.company_group and company.company_group.mobile_app == "road":
            company.metadata.pop("use_reporting_inventory_dashboard_shape_list", None)
            company.metadata.pop("toggle_dashboard_new_shape_update", None)
            updated_items.append(company)

    if updated_items:
        bulk_update(updated_items, batch_size=100, update_fields=["metadata"])


class Migration(migrations.Migration):
    dependencies = [("companies", "0060_create_show_coordinate_input")]
    operations = [
        migrations.RunPython(
            populate_metadata_with_new_keys,
            reverse_code=reverse_populate_metadata_with_new_keys,
        )
    ]
