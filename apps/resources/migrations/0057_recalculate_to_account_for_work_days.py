from collections import defaultdict

from django.db import migrations
from django.db.models import Prefetch
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def recalculate_service_order_resource_fields(apps, schema_editor):
    WORK_DAY_DEFAULT = 22

    resources_to_update = []
    db_alias = schema_editor.connection.alias

    # Get all DailyReport items info beforehand
    daily_report_models = [
        apps.get_model("daily_reports", "DailyReportEquipment"),
        apps.get_model("daily_reports", "DailyReportVehicle"),
        apps.get_model("daily_reports", "DailyReportWorker"),
    ]
    daily_rep_item_amounts = defaultdict(list)
    for daily_report_model in daily_report_models:
        item_data = (
            daily_report_model.objects.using(db_alias)
            .filter(
                contract_item_administration__contract_item_administration_services__isnull=False,
                measurement_bulletin__isnull=False,
            )
            .values_list(
                "amount",
                "contract_item_administration",
                "measurement_bulletin",
                "contract_item_administration__contract_item_administration_services",
            )
        ).distinct()

        for item_amount, item_adm_id, bulletin_id, service_id in item_data:
            key = f"{service_id}__{bulletin_id}"
            daily_rep_item_amounts[key].append((item_adm_id, item_amount))

    # Models needed for the ServiceOrderResource update
    Contract = apps.get_model("resources", "Contract")
    ContractItemAdministration = apps.get_model(
        "resources", "ContractItemAdministration"
    )
    ContractService = apps.get_model("resources", "ContractService")
    ServiceOrderResource = apps.get_model("service_orders", "ServiceOrderResource")
    MeasurementBulletin = apps.get_model("service_orders", "MeasurementBulletin")

    # Get only Contract instances that have adm items
    contracts = (
        Contract.objects.using(db_alias)
        .filter(administration_services__contract_item_administration__isnull=False)
        .prefetch_related(
            Prefetch(
                "bulletins",
                MeasurementBulletin.objects.using(db_alias)
                .all()
                .only("uuid", "work_day"),
            ),
            Prefetch(
                "administration_services",
                ContractService.objects.using(db_alias)
                .filter(contract_item_administration__isnull=False)
                .only("uuid"),
            ),
        )
        .distinct()
    )

    # Find the remaining_amount and used_price for the related ServiceOrderResource instances
    for contract in tqdm(contracts, desc="contracts"):
        measurement_bulletins = contract.bulletins.all()
        admin_services = contract.administration_services.all()

        admin_avg_used_amount = defaultdict(float)
        for admin_service in admin_services:
            for measurement_bulletin in measurement_bulletins:
                work_day = measurement_bulletin.work_day
                key = f"{admin_service.uuid}__{measurement_bulletin.uuid}"
                daily_rep_amounts = daily_rep_item_amounts.get(key, [])

                if daily_rep_amounts:
                    for item_adm_id, obj_amount in daily_rep_amounts:
                        admin_avg_used_amount[item_adm_id] += (
                            obj_amount / work_day if work_day else WORK_DAY_DEFAULT
                        )

        admin_items_ids = admin_avg_used_amount.keys()
        admin_items = (
            ContractItemAdministration.objects.using(db_alias)
            .filter(pk__in=admin_items_ids)
            .prefetch_related(
                Prefetch(
                    "resource",
                    ServiceOrderResource.objects.using(db_alias)
                    .all()
                    .only("amount", "remaining_amount", "unit_price", "used_price"),
                )
            )
            .distinct()
        )
        for admin_item in admin_items:
            avg_usage_amount = admin_avg_used_amount[admin_item.uuid]
            resource = admin_item.resource

            # We'll finally calculate the field data here
            resource.remaining_amount = resource.amount - avg_usage_amount
            resource.used_price = avg_usage_amount * resource.unit_price

            resources_to_update.append(resource)

    bulk_update(
        resources_to_update,
        batch_size=2000,
        update_fields=["remaining_amount", "used_price"],
    )


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0056_set_contract_values"),
    ]

    operations = [migrations.RunPython(recalculate_service_order_resource_fields)]
