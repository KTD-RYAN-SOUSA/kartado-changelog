from django.db import migrations
from tqdm import tqdm


def create_reporting_relation(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    ReportingRelation = apps.get_model("reportings", "ReportingRelation")
    company_qs = Company.objects.using(db_alias).all()

    kwargs = {
        "name": "Relação",
        "outward": "é relacionada à",
        "inward": "é relacionada à",
    }

    for company in tqdm(company_qs):
        ReportingRelation.objects.using(db_alias).create(company=company, **kwargs)


def reverse_create_reporting_relation(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    ReportingRelation = apps.get_model("reportings", "ReportingRelation")
    company_qs = Company.objects.using(db_alias).all()
    kwargs = {
        "name": "Relação",
        "outward": "é relacionada à",
        "inward": "é relacionada à",
    }
    reporting_relation = ReportingRelation.objects.using(db_alias).filter(
        company__in=company_qs, **kwargs
    )
    reporting_relation.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("reportings", "0048_historicalreportingrelation_reportingrelation")
    ]
    operations = [
        migrations.RunPython(
            create_reporting_relation, reverse_code=reverse_create_reporting_relation
        )
    ]
