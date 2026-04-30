from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("scarface", "0005_auto_20250227_1243"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="platform",
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name="platform",
            name="application",
        ),
        migrations.AlterUniqueTogether(
            name="subscription",
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name="subscription",
            name="device",
        ),
        migrations.RemoveField(
            model_name="subscription",
            name="topic",
        ),
        migrations.AlterUniqueTogether(
            name="topic",
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name="topic",
            name="application",
        ),
        migrations.RemoveField(
            model_name="topic",
            name="devices",
        ),
        migrations.AlterUniqueTogether(
            name="device",
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name="device",
            name="arn",
        ),
        migrations.RemoveField(
            model_name="device",
            name="platform",
        ),
        migrations.RemoveField(
            model_name="device",
            name="topics",
        ),
    ]
