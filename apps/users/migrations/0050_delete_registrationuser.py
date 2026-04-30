from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0049_merge_0048_auto_20250923_1934_0048_usersignature"),
    ]

    operations = [
        migrations.DeleteModel(
            name="HistoricalRegistrationUser",
        ),
        migrations.DeleteModel(
            name="RegistrationUser",
        ),
    ]
