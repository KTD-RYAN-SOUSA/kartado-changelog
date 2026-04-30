from apps.resources.models import (
    ContractItemPerformanceBulletin,
    ContractServiceBulletin,
)

CONTRACT_SERVICE_FIELDS = ["weight", "price", "description"]
CONTRACT_ITEM_PERFORMANCE_FIELDS = ["weight", "sort_string"]


def create_contract_bulletin_items(
    contract_service, contract, measurement_bulletins=None
):
    if measurement_bulletins is None:
        measurement_bulletins = []
    for bulletin in measurement_bulletins:
        data_dict = {"parent_uuid": contract_service.uuid, "contract_id": contract.uuid}
        for field in contract_service._meta.fields:
            if field.name not in CONTRACT_SERVICE_FIELDS:
                continue
            data_dict.update({field.name: getattr(contract_service, field.name)})
        new_service_object = ContractServiceBulletin.objects.create(**data_dict)
        new_service_object.measurement_bulletins.set([bulletin])

        new_performance_objects = []
        for (
            contract_item_performance
        ) in contract_service.contract_item_performance.all().prefetch_related(
            "resource"
        ):
            data_dict = {"parent_uuid": contract_item_performance.uuid}
            if contract_item_performance.resource:
                data_dict.update({"resource_id": contract_item_performance.resource_id})
            for field in contract_item_performance._meta.fields:
                if field.name not in CONTRACT_ITEM_PERFORMANCE_FIELDS:
                    continue
                data_dict.update(
                    {field.name: getattr(contract_item_performance, field.name)}
                )
            new_performance_object = ContractItemPerformanceBulletin.objects.create(
                **data_dict
            )
            new_performance_object.measurement_bulletins.set([bulletin])
            new_performance_objects.append(new_performance_object)
        if new_performance_objects:
            new_service_object.contract_item_performance.set(new_performance_objects)
