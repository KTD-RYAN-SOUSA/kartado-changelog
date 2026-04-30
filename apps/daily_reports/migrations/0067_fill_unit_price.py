# Generated on 2024-12-09 18:33

from django.db import migrations
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def fill_unit_price(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    DailyReportWorker = apps.get_model("daily_reports", "DailyReportWorker")
    DailyReportEquipment = apps.get_model("daily_reports", "DailyReportEquipment")
    DailyReportVehicle = apps.get_model("daily_reports", "DailyReportVehicle")

    company_qs = Company.objects.using(db_alias).all()

    for company in tqdm(company_qs):

        daily_workers = (
            DailyReportWorker.objects.using(db_alias)
            .filter(company=company)
            .prefetch_related(
                "contract_item_administration", "contract_item_administration__resource"
            )
        )

        daily_equipments = (
            DailyReportEquipment.objects.using(db_alias)
            .filter(company=company)
            .prefetch_related(
                "contract_item_administration", "contract_item_administration__resource"
            )
        )

        daily_vehicles = (
            DailyReportVehicle.objects.using(db_alias)
            .filter(company=company)
            .prefetch_related(
                "contract_item_administration", "contract_item_administration__resource"
            )
        )

        daily_workers_list = []
        for obj in daily_workers:
            if (
                obj.contract_item_administration
                and obj.contract_item_administration.resource
            ):
                obj.unit_price = obj.contract_item_administration.resource.unit_price
                daily_workers_list.append(obj)

        daily_equipments_list = []
        for obj in daily_equipments:
            if (
                obj.contract_item_administration
                and obj.contract_item_administration.resource
            ):
                obj.unit_price = obj.contract_item_administration.resource.unit_price
                daily_equipments_list.append(obj)

        daily_vehicles_list = []
        for obj in daily_vehicles:
            if (
                obj.contract_item_administration
                and obj.contract_item_administration.resource
            ):
                obj.unit_price = obj.contract_item_administration.resource.unit_price
                daily_vehicles_list.append(obj)

        bulk_update(daily_workers_list, batch_size=2000, update_fields=["unit_price"])
        bulk_update(
            daily_equipments_list, batch_size=2000, update_fields=["unit_price"]
        )
        bulk_update(daily_vehicles_list, batch_size=2000, update_fields=["unit_price"])


def reverse_fill_unit_price(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    DailyReportWorker = apps.get_model("daily_reports", "DailyReportWorker")
    DailyReportEquipment = apps.get_model("daily_reports", "DailyReportEquipment")
    DailyReportVehicle = apps.get_model("daily_reports", "DailyReportVehicle")

    company_qs = Company.objects.using(db_alias).all()

    for company in tqdm(company_qs):
        daily_workers = (
            DailyReportWorker.objects.using(db_alias)
            .filter(company=company)
            .distinct()
            .only("uuid", "unit_price")
        )

        daily_equipments = (
            DailyReportEquipment.objects.using(db_alias)
            .filter(company=company)
            .distinct()
            .only("uuid", "unit_price")
        )

        daily_vehicles = (
            DailyReportVehicle.objects.using(db_alias)
            .filter(company=company)
            .distinct()
            .only("uuid", "unit_price")
        )

        daily_workers.update(unit_price=None)
        daily_equipments.update(unit_price=None)
        daily_vehicles.update(unit_price=None)


class Migration(migrations.Migration):

    dependencies = [
        ("daily_reports", "0066_auto_20241206_1434"),
    ]

    operations = [
        migrations.RunPython(fill_unit_price, reverse_code=reverse_fill_unit_price),
    ]
