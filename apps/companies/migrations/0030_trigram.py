from django.contrib.postgres import operations
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0029_auto_20200127_2040"),
    ]

    operations = [
        operations.TrigramExtension(),
    ]
