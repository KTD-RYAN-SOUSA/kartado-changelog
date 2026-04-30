from django.db import migrations
from tqdm import tqdm


def migrate_quality_sample_reporting_fk_to_m2m(apps, schema_editor):
    """
    Copy the contents of the QualitySample `reporting` field and adds it to the
    new `reportings` M2M field
    """
    db_alias = schema_editor.connection.alias
    QualitySample = apps.get_model("quality_control", "QualitySample")
    samples = QualitySample.objects.using(db_alias).filter(reporting__isnull=False)

    for sample in tqdm(samples):
        sample.reportings.add(sample.reporting)


class Migration(migrations.Migration):

    dependencies = [("quality_control", "0011_qualitysample_reportings")]

    operations = [migrations.RunPython(migrate_quality_sample_reporting_fk_to_m2m)]
