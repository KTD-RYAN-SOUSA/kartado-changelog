from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "resources",
            "0023_contractitemadministration_historicalcontractitemadministration",
        )
    ]

    operations = [
        migrations.AddField(
            model_name="contractservice",
            name="contract_item_administration",
            field=models.ManyToManyField(
                blank=True,
                related_name="contract_item_administration_services",
                to="resources.ContractItemAdministration",
            ),
        )
    ]
