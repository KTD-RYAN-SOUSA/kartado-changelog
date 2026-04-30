from django.db import migrations
from django_bulk_update.helper import bulk_update
from tqdm import tqdm

from helpers.apps.contract_utils import get_spent_price, get_total_price


def set_contract_price_values(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Contract = apps.get_model("resources", "Contract")

    contracts = (
        Contract.objects.using(db_alias)
        .all()
        .prefetch_related(
            "resources",
            "resources__serviceorderresource_procedures",
            "resources__serviceorderresource_procedures__measurement_bulletin",
            "bulletins",
            "performance_services",
        )
    )

    updated_contracts = []

    for contract in tqdm(contracts):
        total_price = get_total_price(contract)
        spent_price = get_spent_price(contract)

        contract.total_price = total_price
        contract.spent_price = spent_price
        updated_contracts.append(contract)

    bulk_update(
        updated_contracts, batch_size=1000, update_fields=["total_price", "spent_price"]
    )


def reset_set_contract_price_values(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Contract = apps.get_model("Contract")

    contracts = Contract.objects.using(db_alias).all()

    updated_contracts = []

    for contract in contracts:
        contract.total_price = 0
        contract.spent_price = 0
        updated_contracts.append(contract)

    bulk_update(
        updated_contracts, batch_size=1000, update_fields=["total_price", "spent_price"]
    )


class Migration(migrations.Migration):
    dependencies = [
        ("resources", "0055_auto_20231220_0951"),
    ]

    operations = [
        migrations.RunPython(
            set_contract_price_values,
            reverse_code=reset_set_contract_price_values,
        )
    ]
