# Generated on 2025-03-26 09:25

import sys

from django.db import migrations
from django.db.models import Prefetch, Sum
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def recalculate_total_price_based_on_work_day(apps, schema_editor):
    db_alias = schema_editor.connection.alias

    Bulletin = apps.get_model("service_orders", "MeasurementBulletin")
    Worker = apps.get_model("daily_reports", "DailyReportWorker")
    Equipment = apps.get_model("daily_reports", "DailyReportEquipment")
    Vehicle = apps.get_model("daily_reports", "DailyReportVehicle")
    ProcedureResource = apps.get_model("service_orders", "ProcedureResource")
    ContractItem = apps.get_model("resources", "ContractItemAdministration")

    APPROVED = "APPROVED_APPROVAL"

    contract_item_prefetch = Prefetch(
        "contract_item_administration",
        queryset=ContractItem.objects.using(db_alias).prefetch_related(
            Prefetch(
                "resource",
                queryset=ProcedureResource.objects.using(db_alias).only("unit_price"),
            )
        ),
    )

    bulletins = (
        Bulletin.objects.using(db_alias)
        .filter(work_day__gt=0)
        .prefetch_related(
            Prefetch(
                "bulletin_workers",
                queryset=Worker.objects.using(db_alias)
                .filter(approval_status=APPROVED)
                .prefetch_related(contract_item_prefetch),
            ),
            Prefetch(
                "bulletin_equipments",
                queryset=Equipment.objects.using(db_alias)
                .filter(approval_status=APPROVED)
                .prefetch_related(contract_item_prefetch),
            ),
            Prefetch(
                "bulletin_vehicles",
                queryset=Vehicle.objects.using(db_alias)
                .filter(approval_status=APPROVED)
                .prefetch_related(contract_item_prefetch),
            ),
            Prefetch(
                "bulletin_resources",
                queryset=ProcedureResource.objects.using(db_alias).filter(
                    approval_status=APPROVED
                ),
            ),
        )
    )

    updated_bulletins = []
    updated_workers = []
    updated_equipments = []
    updated_vehicles = []

    bulletin_iter = (
        tqdm(
            bulletins, desc="recalculate_total_price_based_on_work_day", file=sys.stdout
        )
        if sys.stdout.isatty()
        else bulletins
    )

    for bulletin in bulletin_iter:
        work_day = bulletin.work_day
        total_price = 0

        for item in bulletin.bulletin_workers.all():
            unit_price = (
                item.unit_price
                or getattr(
                    getattr(item.contract_item_administration, "resource", None),
                    "unit_price",
                    0,
                )
                or 0
            )
            item.total_price = (item.amount * unit_price) / work_day
            total_price += item.total_price
            updated_workers.append(item)

        for item in bulletin.bulletin_equipments.all():
            unit_price = (
                item.unit_price
                or getattr(
                    getattr(item.contract_item_administration, "resource", None),
                    "unit_price",
                    0,
                )
                or 0
            )
            item.total_price = (item.amount * unit_price) / work_day
            total_price += item.total_price
            updated_equipments.append(item)

        for item in bulletin.bulletin_vehicles.all():
            unit_price = (
                item.unit_price
                or getattr(
                    getattr(item.contract_item_administration, "resource", None),
                    "unit_price",
                    0,
                )
                or 0
            )
            item.total_price = (item.amount * unit_price) / work_day
            total_price += item.total_price
            updated_vehicles.append(item)

        total_price += (
            bulletin.bulletin_resources.aggregate(total=Sum("total_price"))["total"]
            or 0
        )

        bulletin.total_price = total_price
        updated_bulletins.append(bulletin)

    bulk_update(updated_workers, update_fields=["total_price"], batch_size=1000)
    bulk_update(updated_equipments, update_fields=["total_price"], batch_size=1000)
    bulk_update(updated_vehicles, update_fields=["total_price"], batch_size=1000)
    bulk_update(updated_bulletins, update_fields=["total_price"], batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [
        ("service_orders", "0105_delete_historicalpendingproceduresexport"),
    ]

    operations = [migrations.RunPython(recalculate_total_price_based_on_work_day)]
