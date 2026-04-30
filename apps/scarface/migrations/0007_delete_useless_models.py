from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("scarface", "0006_remove_useless_fields"),
    ]

    operations = [
        migrations.DeleteModel(name="Application"),
        migrations.DeleteModel(name="Subscription"),
        migrations.DeleteModel(name="Platform"),
        migrations.DeleteModel(name="Topic"),
    ]
