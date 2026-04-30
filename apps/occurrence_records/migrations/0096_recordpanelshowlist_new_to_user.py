from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("occurrence_records", "0095_merge_20240724_1005"),
    ]

    operations = [
        migrations.AddField(
            model_name="recordpanelshowlist",
            name="new_to_user",
            field=models.BooleanField(default=False),
        ),
    ]
