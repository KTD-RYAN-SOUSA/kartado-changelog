from django.db import migrations
from django.db.models import Prefetch, Q
from tqdm import tqdm


def migrate_old_contract_items(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Contract = apps.get_model("resources", "Contract")
    ContractService = apps.get_model("resources", "ContractService")
    ContractItemUnitPrice = apps.get_model("resources", "ContractItemUnitPrice")
    ServiceOrderResource = apps.get_model("service_orders", "ServiceOrderResource")

    # The filters make sure we're not trying to migrate Contracts that use the new models
    contracts = (
        Contract.objects.using(db_alias)
        .filter(
            # Get only contracts with items
            Q(resources__isnull=False)
            # But ignore contracts who use the new models
            & Q(unit_price_services__isnull=True)
            & Q(administration_services__isnull=True)
            & Q(performance_services__isnull=True)
            & Q(resources__resource_contract_unit_price_items__isnull=True)
            & Q(resources__resource_contract_administration_items__isnull=True)
        )
        .distinct()
        .prefetch_related(
            "firm",
            "subcompany",
            "subcompany__subcompany_firms",
            Prefetch(
                "resources",
                queryset=ServiceOrderResource.objects.all().order_by("resource__name"),
            ),
        )
    )

    for contract in tqdm(contracts):
        # Define which firms are going to be added to the new ContractService
        if contract.firm:
            contract_firms = [contract.firm]
        elif contract.subcompany:
            contract_firms = list(contract.subcompany.subcompany_firms.all())
        else:
            contract_firms = []

        new_contract_service = ContractService.objects.using(db_alias).create(
            description="Seção 1"
        )
        new_contract_service.firms.add(*contract_firms)

        contract_service_order_resources = contract.resources.all().order_by(
            "resource__name"
        )
        for (i, service_order_resource) in enumerate(contract_service_order_resources):
            kwargs = {
                "sort_string": str(i + 1),
                "entity": service_order_resource.entity,
                "resource": service_order_resource,
            }

            new_item = ContractItemUnitPrice.objects.using(db_alias).create(**kwargs)
            new_contract_service.contract_item_unit_prices.add(new_item)

        contract.unit_price_services.add(new_contract_service)


class Migration(migrations.Migration):

    dependencies = [("resources", "0025_auto_20220303_1621")]

    operations = [
        migrations.RunPython(
            migrate_old_contract_items, reverse_code=migrations.RunPython.noop
        )
    ]
