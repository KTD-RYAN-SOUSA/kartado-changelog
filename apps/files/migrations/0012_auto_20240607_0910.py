from django.db import migrations
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def fill_company_field(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    File = apps.get_model("files", "File")
    ContentType = apps.get_model("contenttypes", "ContentType")
    MonitoringRecord = apps.get_model("monitorings", "MonitoringRecord")
    OperationalControl = apps.get_model("monitorings", "OperationalControl")
    OccurrenceRecord = apps.get_model("occurrence_records", "OccurrenceRecord")
    Construction = apps.get_model("constructions", "Construction")
    ConstructionProgress = apps.get_model("constructions", "ConstructionProgress")

    # Get the relevant content types
    monitoring_record_ctype = ContentType.objects.using(db_alias).get(
        model="monitoringrecord"
    )
    operational_control_ctype = ContentType.objects.using(db_alias).get(
        model="operationalcontrol"
    )
    occurrence_record_ctype = ContentType.objects.using(db_alias).get(
        model="occurrencerecord"
    )
    construction_ctype = ContentType.objects.using(db_alias).get(model="construction")
    construction_progress_ctype = ContentType.objects.using(db_alias).get(
        model="constructionprogress"
    )

    ctypes = [
        (monitoring_record_ctype, MonitoringRecord),
        (operational_control_ctype, OperationalControl),  # firm.company_id
        (occurrence_record_ctype, OccurrenceRecord),
        (construction_ctype, Construction),
        (construction_progress_ctype, ConstructionProgress),  # construction.company_id
    ]

    updated_files = []
    for ctype, model in ctypes:
        ctype_files = File.objects.using(db_alias).filter(content_type=ctype)
        ctype_object_ids = ctype_files.values_list("object_id", flat=True)

        if model == OperationalControl:
            relevant_fields = ["uuid", "firm__company"]
        elif model == ConstructionProgress:
            relevant_fields = ["uuid", "construction__company"]
        else:
            relevant_fields = ["uuid", "company"]

        raw_ids_list = (
            model.objects.using(db_alias)
            .filter(uuid__in=ctype_object_ids)
            .values_list(*relevant_fields)
        )
        instance_id_to_company_id = {
            instance_id: company_id for instance_id, company_id in raw_ids_list
        }

        for file in tqdm(ctype_files):
            company_id = instance_id_to_company_id.get(file.object_id, None)
            if company_id:
                file.company_id = company_id
                updated_files.append(file)

    bulk_update(updated_files, batch_size=2000, update_fields=["company_id"])


def reverse_fill_company_field(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    File = apps.get_model("files", "File")
    files = File.objects.using(db_alias).all()

    updated_files = []
    for file in tqdm(files):
        file.company = None
        updated_files.append(file)

    bulk_update(updated_files, batch_size=2000, update_fields=["company"])


class Migration(migrations.Migration):

    dependencies = [
        ("files", "0011_auto_20240528_0842"),
    ]

    operations = [
        migrations.RunPython(
            fill_company_field, reverse_code=reverse_fill_company_field
        ),
    ]
