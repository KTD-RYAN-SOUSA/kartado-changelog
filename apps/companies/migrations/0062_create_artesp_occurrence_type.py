from django.db import migrations
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def create_occ_type_and_add_configs_to_metadata(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    OccurrenceType = apps.get_model("occurrence_records", "OccurrenceType")
    OccurrenceTypeSpecs = apps.get_model("occurrence_records", "OccurrenceTypeSpecs")
    Firm = apps.get_model("companies", "Firm")
    company_qs = Company.objects.using(db_alias).filter(
        company_group__mobile_app="road"
    )

    updated_items = []

    for company in tqdm(company_qs):
        firms = Firm.objects.using(db_alias).filter(company=company)
        name = "Classe ARTESP"
        form_fields = {
            "id": "9999",
            "name": name,
            "fields": [],
            "groups": [],
            "displayName": name,
        }
        occ_type_data = {
            "form_fields": form_fields,
            "name": name,
            "occurrence_kind": "",
        }
        occ_type = OccurrenceType.objects.create(**occ_type_data)
        occ_type.firms.add(*firms)
        OccurrenceTypeSpecs.objects.create(company=company, occurrence_type=occ_type)
        company.metadata["artesp_default_occurrence_type"] = str(occ_type.uuid)
        company.metadata["artesp_canceled_status"] = [4]
        updated_items.append(company)

    bulk_update(updated_items, batch_size=100, update_fields=["metadata"])


def reverse_create_occ_type_and_add_configs_to_metadata(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    OccurrenceType = apps.get_model("occurrence_records", "OccurrenceType")
    company_qs = Company.objects.using(db_alias).all()

    updated_items = []

    for company in tqdm(company_qs):
        OccurrenceType.objects.using(db_alias).filter(
            company=company, name="Classe ARTESP"
        ).delete()
        if "artesp_default_occurrence_type" in company.metadata:
            del company.metadata["artesp_default_occurrence_type"]
        if "artesp_canceled_status" in company.metadata:
            del company.metadata["artesp_canceled_status"]
        updated_items.append(company)

    bulk_update(updated_items, batch_size=100, update_fields=["metadata"])


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0061_fill_artesp_config_v2"),
        ("occurrence_records", "0084_create_panel_menus"),
    ]
    operations = [
        migrations.RunPython(
            create_occ_type_and_add_configs_to_metadata,
            reverse_code=reverse_create_occ_type_and_add_configs_to_metadata,
        )
    ]
