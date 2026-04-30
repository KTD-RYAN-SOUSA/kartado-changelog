from django.db import migrations
from django.db.models import BooleanField, Case, Q, Value, When
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def fill_custom_map_table_field(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    OccurrenceType = apps.get_model("occurrence_records", "OccurrenceType")

    occ_types = (
        OccurrenceType.objects.using(db_alias)
        .filter(custom_map_table=[])
        .annotate(
            has_general_identification=Case(
                When(
                    Q(
                        form_fields__fields__contains=[
                            {"apiName": "generalIdentification"}
                        ]
                    )
                    | Q(
                        form_fields__fields__contains=[
                            {"api_name": "generalIdentification"}
                        ]
                    ),
                    then=Value(True),
                ),
                default=Value(False),
                output_field=BooleanField(),
            ),
            hides_rep_location=Case(
                When(
                    Q(company__metadata__hide_reporting_location=True)
                    | Q(company__metadata__hideReportingLocation=True),
                    then=Value(True),
                ),
                default=Value(False),
                output_field=BooleanField(),
            ),
        )
        .distinct()
    )

    updated_occ_types = []
    for occ_type in tqdm(occ_types):
        occ_type.custom_map_table.extend(["foundAt", "number"])

        if occ_type.has_general_identification:
            occ_type.custom_map_table.append("generalIdentification")

        if not occ_type.hides_rep_location:
            occ_type.custom_map_table.extend(["direction", "km"])

        updated_occ_types.append(occ_type)

    bulk_update(updated_occ_types, batch_size=2000, update_fields=["custom_map_table"])


class Migration(migrations.Migration):

    dependencies = [
        ("occurrence_records", "0092_auto_20240604_1522"),
    ]

    operations = [
        migrations.RunPython(
            fill_custom_map_table_field, reverse_code=migrations.RunPython.noop
        ),
    ]
