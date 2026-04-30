from django.db import migrations
from django_bulk_update.helper import bulk_update

from helpers.apps.companies import is_energy_company


def fill_is_clustered_access_request(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")

    company_qs = Company.objects.using(db_alias).all()

    updated_items = []

    for company in company_qs:
        is_energy = is_energy_company(company)
        if is_energy:
            company.metadata["is_clustered_access_request"] = True
            updated_items.append(company)

    bulk_update(updated_items, batch_size=100, update_fields=["metadata"])


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0065_merge_20240912_1801"),
    ]

    operations = [migrations.RunPython(fill_is_clustered_access_request)]
