import logging

import sentry_sdk
from django.db.models import Q, Sum, prefetch_related_objects
from zappa.asynchronous import task

from apps.companies.models import Firm
from apps.daily_reports.models import DailyReportContractUsage
from apps.resources.models import Contract
from apps.service_orders.models import MeasurementBulletin
from helpers.apps.performance_calculations import MeasurementBulletinScope
from helpers.signals import DisableSignals


@task
def calculate_contract_prices(contract_uuid):
    """Calculates contract price
    Args:
        contract_instance (Contract): Contract model instance
    """
    contract_instance = Contract.objects.get(uuid=contract_uuid)
    contract_instance.refresh_from_db()
    contract_instance.total_price = get_total_price(contract_instance)
    contract_instance.spent_price = get_spent_price(contract_instance)
    with DisableSignals():
        contract_instance.save()


def get_spent_price(contract_instance):
    """Returns spent price from contract.
    Args:
        contract_instance (Contract): Contract model instance

    Raises:
        Exception: generic expeption

    Returns:
        int | float: contract spent price
    """
    prefetch_related_objects([contract_instance], "bulletins")
    unit_spent_price = 0
    resource_list = []
    for resource in contract_instance.resources.all().prefetch_related(
        "serviceorderresource_procedures",
        "serviceorderresource_procedures__measurement_bulletin",
    ):
        resource_list.append(resource.pk)

        for procedure_resource in resource.serviceorderresource_procedures.all():
            try:
                resource_spent_price = (
                    (procedure_resource.unit_price * procedure_resource.amount)
                    if procedure_resource.measurement_bulletin
                    else 0
                )
                if not isinstance(resource_spent_price, (int, float)):
                    raise Exception()
                unit_spent_price += resource_spent_price
            except Exception:
                continue

    # administration services
    administration_spent_price = 0
    worker_contract_usages = DailyReportContractUsage.objects.filter(
        worker__contract_item_administration__resource__in=resource_list
    )
    equipment_contract_usages = DailyReportContractUsage.objects.filter(
        equipment__contract_item_administration__resource__in=resource_list
    )
    vehicle_contract_usages = DailyReportContractUsage.objects.filter(
        vehicle__contract_item_administration__resource__in=resource_list
    )
    base_contract_usages = DailyReportContractUsage.objects.filter(
        uuid__in=(
            list(worker_contract_usages.values_list("uuid", flat=True))
            + list(equipment_contract_usages.values_list("uuid", flat=True))
            + list(vehicle_contract_usages.values_list("uuid", flat=True))
        )
    )
    administration_items_used = (
        base_contract_usages.filter(
            (
                (
                    Q(worker__multiple_daily_reports__isnull=True)
                    & Q(equipment__multiple_daily_reports__isnull=True)
                    & Q(vehicle__multiple_daily_reports__isnull=True)
                )
                | (
                    Q(worker__multiple_daily_reports__isnull=False)
                    & Q(worker__multiple_daily_reports__day_without_work=False)
                    & Q(worker__worker_relations__active=True)
                )
                | (
                    Q(vehicle__multiple_daily_reports__isnull=False)
                    & Q(vehicle__multiple_daily_reports__day_without_work=False)
                    & Q(vehicle__vehicle_relations__active=True)
                )
                | (
                    Q(equipment__multiple_daily_reports__isnull=False)
                    & Q(equipment__multiple_daily_reports__day_without_work=False)
                    & Q(equipment__equipment_relations__active=True)
                )
            ),
        )
        .prefetch_related(
            "worker__measurement_bulletin",
            "equipment__measurement_bulletin",
            "vehicle__measurement_bulletin",
        )
        .distinct()
    )
    for used in administration_items_used:
        if used.worker:
            administration_spent_price += (
                used.worker.total_price if used.worker.measurement_bulletin else 0
            )
        elif used.equipment:
            administration_spent_price += (
                used.equipment.total_price if used.equipment.measurement_bulletin else 0
            )
        elif used.vehicle:
            administration_spent_price += (
                used.vehicle.total_price if used.vehicle.measurement_bulletin else 0
            )
        else:
            pass

    performance_spent_price = 0

    def calculate_contract_average_grade(obj, bulletin: MeasurementBulletin):
        measurement_bulletin_scope = MeasurementBulletinScope(
            obj, measurement_bulletin=bulletin
        )
        measurement_bulletin_scope.calculate_mb_average_grade_percent()
        bulletin_average_grade_percent = (
            measurement_bulletin_scope.average_grade_percent
        )
        return bulletin_average_grade_percent

    for bulletin in contract_instance.bulletins.all():
        try:
            bulletin_average_grade = calculate_contract_average_grade(
                contract_instance, bulletin=bulletin
            )
            for (
                contract_service
            ) in contract_instance.contract_services_bulletins.filter(
                measurement_bulletins=bulletin
            ):
                if (
                    contract_instance.performance_months
                    and contract_instance.performance_months > 0
                ):
                    performance_spent_price += (
                        contract_service.price / contract_instance.performance_months
                    ) * bulletin_average_grade
        except Exception:
            continue

    total_spent_price = (
        unit_spent_price + administration_spent_price + performance_spent_price
    )
    return total_spent_price


def get_total_price(contract_instance):
    """Returns total price from contract

    Args:
        contract_instance (Contract): Contract model instance

    Raises:
        Exception: generic expeption

    Returns:
        int | float: contract total price
    """
    prefetch_related_objects([contract_instance], "resources", "performance_services")
    total_price = 0
    for resource in contract_instance.resources.all():
        try:
            resource_total_price = resource.unit_price * resource.amount
            if not isinstance(resource_total_price, (int, float)):
                raise Exception()
            total_price += resource_total_price
        except Exception:
            continue
    for performance_service in contract_instance.performance_services.all():
        if not isinstance(performance_service.price, (int, float)):
            raise Exception()
        total_price += performance_service.price

    return total_price


def get_provisioned_price(contract_instance):
    try:
        provisioned_price = sum(contract_instance.spend_schedule.values())
    except Exception:
        provisioned_price = 0
    return provisioned_price


def get_unit_price(item):
    if item.unit_price is not None:
        return item.unit_price
    if item.contract_item_administration and item.contract_item_administration.resource:
        return item.contract_item_administration.resource.unit_price
    return 0


def recalculate_total_price_based_on_work_day(instance, resource_approval_status):
    work_day = instance.work_day
    total_price = 0

    workers = instance.bulletin_workers.prefetch_related(
        "contract_item_administration", "contract_item_administration__resource"
    ).filter(approval_status=resource_approval_status.APPROVED_APPROVAL)

    for item in workers:
        unit_price = get_unit_price(item)
        item.total_price = (item.amount * unit_price) / work_day

    if workers:
        type(workers[0]).objects.bulk_update(workers, ["total_price"])

    equipments = instance.bulletin_equipments.prefetch_related(
        "contract_item_administration", "contract_item_administration__resource"
    ).filter(approval_status=resource_approval_status.APPROVED_APPROVAL)

    for item in equipments:
        unit_price = get_unit_price(item)
        item.total_price = (item.amount * unit_price) / work_day

    if equipments:
        type(equipments[0]).objects.bulk_update(equipments, ["total_price"])

    vehicles = instance.bulletin_vehicles.prefetch_related(
        "contract_item_administration", "contract_item_administration__resource"
    ).filter(approval_status=resource_approval_status.APPROVED_APPROVAL)

    for item in vehicles:
        unit_price = get_unit_price(item)
        item.total_price = (item.amount * unit_price) / work_day

    if vehicles:
        type(vehicles[0]).objects.bulk_update(vehicles, ["total_price"])

    total_price += workers.aggregate(Sum("total_price"))["total_price__sum"] or 0
    total_price += equipments.aggregate(Sum("total_price"))["total_price__sum"] or 0
    total_price += vehicles.aggregate(Sum("total_price"))["total_price__sum"] or 0

    resources = instance.bulletin_resources.filter(
        approval_status=resource_approval_status.APPROVED_APPROVAL
    )
    total_price += resources.aggregate(Sum("total_price"))["total_price__sum"] or 0

    instance.total_price = total_price
    instance.save()


@task
def set_related_firms(measurement_bulletin_uuid):
    try:
        bulletin_instance = MeasurementBulletin.objects.get(
            uuid=measurement_bulletin_uuid
        )
        bulletin_instance.refresh_from_db()

        prefetch_related_objects(
            [bulletin_instance],
            "bulletin_resources",
            "bulletin_workers",
            "bulletin_vehicles",
            "bulletin_equipments",
        )

        reporting_firms = list(
            bulletin_instance.bulletin_resources.values_list(
                "reporting__firm_id", flat=True
            )
        )

        workers_firms = list(
            bulletin_instance.bulletin_workers.values_list(
                "multiple_daily_reports__firm_id", flat=True
            )
        )
        vehicles_firms = list(
            bulletin_instance.bulletin_vehicles.values_list(
                "multiple_daily_reports__firm_id", flat=True
            )
        )
        equipments_firms = list(
            bulletin_instance.bulletin_equipments.values_list(
                "multiple_daily_reports__firm_id", flat=True
            )
        )

        firm_list = list(
            filter(
                None,
                set(
                    reporting_firms + workers_firms + equipments_firms + vehicles_firms
                ),
            )
        )
        ordered_firms = Firm.objects.filter(uuid__in=firm_list).order_by("name")

        bulletin_instance.related_firms.set(ordered_firms)

        bulletin_instance.is_processing = False

        with DisableSignals():
            bulletin_instance.save()
    except Exception as e:
        logging.error(f"Error setting MeasurementBulletin related_firms: {e}")
        sentry_sdk.capture_exception(e)
