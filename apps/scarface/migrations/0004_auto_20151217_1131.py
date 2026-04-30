# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scarface", "0003_auto_20151217_1101"),
    ]

    operations = [
        migrations.AlterField(
            model_name="device",
            name="push_token",
            field=models.CharField(max_length=512),
        ),
    ]
