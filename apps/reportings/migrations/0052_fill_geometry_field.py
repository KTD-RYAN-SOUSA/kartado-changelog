from django.contrib.gis.db.models.fields import GeometryCollectionField
from django.contrib.gis.geos import GeometryCollection
from django.db import migrations
from django.db.models import Func, TextField, Value
from django.db.models.functions import Cast, Concat
from django_bulk_update.helper import bulk_update
from tqdm import tqdm

migration_strategy = None
# This migration has been purposefully disabled by default
# Still, there is code to do it two different ways
# If you need it to run, change the variable above


def fill_geometry_field(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Reporting = apps.get_model("reportings", "Reporting")
    HistoricalReporting = apps.get_model("reportings", "HistoricalReporting")
    Company = apps.get_model("companies", "Company")
    company_qs = Company.objects.using(db_alias).all()

    if migration_strategy == "django_update":
        for company in tqdm(company_qs):
            # objs = []
            reportings = (
                Reporting.objects.using(db_alias)
                .filter(company=company, point__isnull=False)
                .annotate(
                    wkt=Func("point", function="ST_AsText", output_field=TextField()),
                )
                .filter(
                    wkt__isnull=False,
                )
                .exclude(wkt="")
                .order_by("uuid")
            )
            hist_reportings = (
                HistoricalReporting.objects.using(db_alias)
                .filter(company=company, point__isnull=False)
                .annotate(
                    wkt=Func("point", function="ST_AsText", output_field=TextField()),
                )
                .filter(
                    wkt__isnull=False,
                )
                .exclude(wkt="")
                .order_by("uuid")
            )

            reportings.update(
                geometry=Cast(
                    Concat(
                        Value("SRID=4326;GEOMETRYCOLLECTION ("),
                        Func("point", function="ST_AsText", output_field=TextField()),
                        Value(")"),
                    ),
                    output_field=GeometryCollectionField(srid=4326),
                ),
                properties=[{}],
            )

            hist_reportings.update(
                geometry=Cast(
                    Concat(
                        Value("SRID=4326;GEOMETRYCOLLECTION ("),
                        Func("point", function="ST_AsText", output_field=TextField()),
                        Value(")"),
                    ),
                    output_field=GeometryCollectionField(srid=4326),
                ),
                properties=[{}],
            )

    elif migration_strategy == "bulk_update":
        for company in company_qs:
            objs = []
            reportings = (
                Reporting.objects.using(db_alias)
                .filter(
                    company=company,
                )
                .only("uuid", "point", "geometry", "properties")
            )
            for rep in reportings:
                if rep.point:
                    rep.geometry = GeometryCollection(rep.point)
                    rep.properties = [{}]
                    objs.append(rep)
            bulk_update(
                objs,
                batch_size=1000,
                update_fields=["geometry", "properties"],
            )


def reverse_fill_geometry_field(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Reporting = apps.get_model("reportings", "Reporting")
    Company = apps.get_model("companies", "Company")
    company_qs = Company.objects.using(db_alias).all()

    if migration_strategy == "bulk_update":

        for company in company_qs:
            objs = []
            reportings = (
                Reporting.objects.using(db_alias)
                .filter(
                    company=company,
                )
                .only("uuid", "point", "geometry")
            )
            for rep in reportings:
                if rep.geometry:
                    rep.geometry = None
                    objs.append(rep)
            bulk_update(objs, batch_size=1000, update_fields=["geometry"])


class Migration(migrations.Migration):
    dependencies = [("reportings", "0051_auto_20240105_0955")]
    operations = [
        migrations.RunPython(
            fill_geometry_field, reverse_code=reverse_fill_geometry_field
        )
    ]
