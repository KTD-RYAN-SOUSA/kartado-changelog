from django.db import migrations
from tqdm import tqdm


def change_company_to_companies(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    AccessRequest = apps.get_model("companies", "AccessRequest")
    requests = AccessRequest.objects.using(db_alias).all().prefetch_related("company")
    for request in tqdm(requests):
        request.companies.set([request.company])


class Migration(migrations.Migration):
    dependencies = [("companies", "0054_accessrequest_companies")]
    operations = [
        migrations.RunPython(
            change_company_to_companies, reverse_code=migrations.RunPython.noop
        )
    ]
