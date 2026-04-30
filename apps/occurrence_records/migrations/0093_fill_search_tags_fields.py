from django.db import migrations
from django.db.models import Case, F, OuterRef, Subquery, TextField, When
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def fill_search_tags_helper_fields(apps, schema_editor):
    """
    Fill the new SearchTag helper fields for OccurrenceRecord instances created
    before the signal implementation.
    """

    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    OccurrenceRecord = apps.get_model("occurrence_records", "OccurrenceRecord")
    SearchTag = apps.get_model("templates", "SearchTag")

    updated_records = []
    companies = Company.objects.using(db_alias).all()
    for company in tqdm(companies):
        search_tag_record_sub = SearchTag.objects.using(db_alias).filter(
            level=1, occurrence_records=OuterRef("pk")
        )
        search_tag_type_sub = SearchTag.objects.using(db_alias).filter(
            level=2, occurrence_records=OuterRef("pk")
        )
        search_tag_kind_sub = SearchTag.objects.using(db_alias).filter(
            level=3, occurrence_records=OuterRef("pk")
        )
        search_tag_subject_sub = SearchTag.objects.using(db_alias).filter(
            level=4, occurrence_records=OuterRef("pk")
        )

        records = (
            OccurrenceRecord.objects.using(db_alias)
            .filter(company=company, search_tags__isnull=False)
            .annotate(
                # Record
                tmp_record_tag_id=Subquery(
                    search_tag_record_sub.values("uuid")[:1], output_field=TextField()
                ),
                tmp_record_tag=Subquery(
                    search_tag_record_sub.values("name")[:1], output_field=TextField()
                ),
                tmp_record=Case(
                    When(record_tag__isnull=False, then=F("record_tag")),
                    default=F("occurrence_type__occurrence_kind"),
                    output_field=TextField(),
                ),
                # Type
                tmp_type_tag_id=Subquery(
                    search_tag_type_sub.values("uuid")[:1], output_field=TextField()
                ),
                tmp_type_tag=Subquery(
                    search_tag_type_sub.values("name")[:1], output_field=TextField()
                ),
                tmp_type=Case(
                    When(type_tag__isnull=False, then=F("type_tag")),
                    default=F("occurrence_type__name"),
                    output_field=TextField(),
                ),
                # Kind
                tmp_kind_tag_id=Subquery(
                    search_tag_kind_sub.values("uuid")[:1], output_field=TextField()
                ),
                tmp_kind=Subquery(
                    search_tag_kind_sub.values("name")[:1], output_field=TextField()
                ),
                # Subject
                tmp_subject_tag_id=Subquery(
                    search_tag_subject_sub.values("uuid")[:1], output_field=TextField()
                ),
                tmp_subject=Subquery(
                    search_tag_subject_sub.values("name")[:1], output_field=TextField()
                ),
            )
        )

        for record in records:
            # Make the annotations permanent
            record.record_tag_id = record.tmp_record_tag_id
            record.record_tag = record.tmp_record_tag
            record.record = record.tmp_record

            record.type_tag_id = record.tmp_type_tag_id
            record.type_tag = record.tmp_type_tag
            record.type = record.tmp_type

            record.kind_tag_id = record.tmp_kind_tag_id
            record.kind = record.tmp_kind

            record.subject_tag_id = record.subject_tag_id
            record.subject = record.tmp_subject

            updated_records.append(record)

    bulk_update(
        updated_records,
        batch_size=2000,
        update_fields=[
            "record_tag_id",
            "record_tag",
            "record",
            "type_tag_id",
            "type_tag",
            "type",
            "kind_tag_id",
            "kind",
            "subject_tag_id",
            "subject",
        ],
    )


class Migration(migrations.Migration):

    dependencies = [
        ("occurrence_records", "0092_auto_20240531_0840"),
    ]

    operations = [
        migrations.RunPython(
            fill_search_tags_helper_fields, reverse_code=migrations.RunPython.noop
        )
    ]
