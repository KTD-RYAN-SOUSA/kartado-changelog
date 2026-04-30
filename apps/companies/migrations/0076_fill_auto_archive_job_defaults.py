from django.db import migrations
from django_bulk_update.helper import bulk_update

EXCLUDED_UUIDS = [
    "b8450161-14d1-4de8-b254-7d1ddc4a9c20",
    "96e24ad5-3b23-461f-9300-85c542576894",
    "433c0cd2-80e2-46c9-b8c5-030fc61070e5",
    "4e3abcde-b827-469c-ab60-4e6a3030ee60",
    "d8ad38eb-91bf-4482-b5c8-7f3c6341c65e",
    "69e110b0-e7ee-4379-b6b2-c4c9d88e91b4",
    "bec1fdb9-85a7-40ad-b1ac-6f1c215859a8",
    "8174e68f-3a8f-4013-98dd-062954e4c0da",
    "368b6a99-502e-4f1c-8f10-4de6f445a160",
    "52106de8-24d8-46ef-bc6d-aaa546855707",
    "b8c91aac-3cbb-48d7-a5f2-064c0f0702a2",
    "7c7b39ac-7711-420a-9402-0859df283634",
]


def fill_auto_archive_job_defaults(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")

    company_qs = Company.objects.using(db_alias).all()

    updated_items = []

    for company in company_qs:
        if str(company.uuid) in EXCLUDED_UUIDS:
            continue

        company_mapping = company.metadata.get("company_mapping", [])
        is_implantacao = any(
            item.get("displayName") == "Etapa da jornada" and item.get("value") == "22"
            for item in company_mapping
        )
        if is_implantacao:
            continue

        company.metadata["auto_archive_completed_jobs"] = True

        if company.metadata.get("approved_approval_steps"):
            company.metadata["consider_approval_for_job_progress"] = True

        updated_items.append(company)

    bulk_update(updated_items, batch_size=100, update_fields=["metadata"])


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0075_merge_0074_auto_20250604_1735_0074_auto_20250909_1951"),
    ]

    operations = [migrations.RunPython(fill_auto_archive_job_defaults)]
