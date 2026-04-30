from django.db import migrations
from tqdm import tqdm


def create_reporting_relation_recuperation(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    ReportingRelation = apps.get_model("reportings", "ReportingRelation")
    company_qs = Company.objects.using(db_alias).all()

    kwargs = {
        "name": "Recuperação",
        "outward": "Tem recuperação na",
        "inward": "É recuperação para",
    }

    for company in tqdm(company_qs):
        reporting_relation = ReportingRelation.objects.using(db_alias).create(
            company=company, **kwargs
        )
        company.metadata["recuperation_reporting_relation"] = str(
            reporting_relation.uuid
        )
        company.save()


def reverse_create_reporting_relation_recuperation(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    ReportingRelation = apps.get_model("reportings", "ReportingRelation")
    company_qs = Company.objects.using(db_alias).all()
    kwargs = {
        "name": "Recuperação",
        "outward": "tem recuperação na",
        "inward": "é recuperação para",
    }
    for company in company_qs:
        reporting_relation = ReportingRelation.objects.using(db_alias).filter(
            company=company, **kwargs
        )
        reporting_relation.delete()
        if "recuperation_reporting_relation" in company.metadata:
            del company.metadata["recuperation_reporting_relation"]
            company.save()


class Migration(migrations.Migration):
    dependencies = [("reportings", "0050_auto_20230901_1441")]
    operations = [
        migrations.RunPython(
            create_reporting_relation_recuperation,
            reverse_code=reverse_create_reporting_relation_recuperation,
        )
    ]
