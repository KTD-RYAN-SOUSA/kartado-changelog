from django.db.models import Count
from django_bulk_update.helper import bulk_update
from rest_framework_json_api.serializers import ValidationError
from simple_history.utils import bulk_create_with_history

from apps.reportings.models import Reporting
from apps.service_orders.models import ServiceOrderActionStatusSpecs
from apps.services.models import (
    Measurement,
    MeasurementService,
    Service,
    ServiceSpecs,
    ServiceUsage,
)
from helpers.apps.json_logic import apply_reporting_json_logic
from helpers.histories import bulk_update_with_history


def calculate_amount(fields_json):
    for key, item in fields_json.items():
        data = item.get("data")
        formula_backend = item.get("formula").get("backend")
        item["amount"] = apply_reporting_json_logic(data, formula_backend)

    return fields_json


def create_usages_from_reporting(reporting, user):
    services_specs = (
        ServiceSpecs.objects.filter(
            occurrence_type=reporting.occurrence_type,
            service__company=reporting.company,
        )
        .select_related("service")
        .distinct()
    )

    final_json = {
        service_specs.service: {
            "data": reporting,
            "formula": service_specs.formula,
        }
        for service_specs in services_specs
    }

    final_json = calculate_amount(final_json)

    bulk_create_list = []
    bulk_update_list = []
    executed_status_order = reporting.company.metadata["executed_status_order"]

    for service, item in final_json.items():
        order = (
            ServiceOrderActionStatusSpecs.objects.filter(
                status=reporting.status, company=reporting.company
            )
            .first()
            .order
        )
        # Refresh current_balance from Service
        if order >= executed_status_order:
            service.current_balance -= item.get("amount")
            bulk_update_list.append(service)

        # Create ServiceUsage
        bulk_create_list.append(
            ServiceUsage(
                reporting=reporting,
                service=service,
                formula=item.get("formula"),
                amount=item.get("amount"),
            )
        )

    if bulk_update_list:
        bulk_update(bulk_update_list, update_fields=["current_balance"])
    ServiceUsage.objects.bulk_create(bulk_create_list)

    return True


def update_usages_from_reporting(reporting, user):
    final_json = {
        service_usage.service: {
            "data": reporting,
            "formula": service_usage.formula,
            "service_usage": service_usage,
            "last_amount": service_usage.amount,
            "measurement": service_usage.measurement,
        }
        for service_usage in reporting.reporting_usage.all()
        .select_related("service", "measurement")
        .prefetch_related("measurement__measurement_services__service")
    }

    final_json = calculate_amount(final_json)

    bulk_service_usage_list = []
    bulk_service_list = []
    bulk_measurement_service_list = []
    executed_status_order = reporting.company.metadata["executed_status_order"]

    for service, item in final_json.items():
        order = (
            ServiceOrderActionStatusSpecs.objects.filter(
                status=reporting.status, company=reporting.company
            )
            .first()
            .order
        )
        # Refresh current_balance from Service
        if order >= executed_status_order:
            service.current_balance += item.get("last_amount") - item.get("amount")
            bulk_service_list.append(service)

        service_usage = item.get("service_usage")
        measurement = item.get("measurement")
        if measurement:
            try:
                measurement_service = next(
                    a
                    for a in measurement.measurement_services.all()
                    if a.service == service_usage.service
                )
                measurement_service.balance += item.get("last_amount") - item.get(
                    "amount"
                )

                bulk_measurement_service_list.append(measurement_service)
            except StopIteration as e:
                print(e)

        # Refresh current_amount from ServiceUsage
        service_usage.amount = item.get("amount")
        service_usage.formula = item.get("formula")
        bulk_service_usage_list.append(service_usage)

    if bulk_service_list:
        bulk_update(bulk_service_list, update_fields=["current_balance"])
    if bulk_measurement_service_list:
        bulk_update(bulk_measurement_service_list, update_fields=["balance"])
    bulk_update(bulk_service_usage_list, update_fields=["amount", "formula"])

    return True


def find_in_qs(objs, pk, prop=None):
    # safely find an object in a queryset using 'next'
    # return None if not found
    try:
        obj = next(a for a in objs if a.pk == pk)
        if prop:
            return getattr(obj, prop)
        else:
            return obj
    except StopIteration:
        return None


def update_usages_from_measurement(instance, reportings, user):

    services_usage = (
        ServiceUsage.objects.filter(reporting__in=reportings)
        .select_related("service")
        .distinct()
    )

    if any([a.measurement for a in list(services_usage)]):
        raise ValidationError("Um ou mais apontamentos selecionados já foi medido")

    all_measurements = (
        Measurement.objects.filter(company=instance.company)
        .select_related("previous_measurement", "next_measurement")
        .prefetch_related("measurement_services__service")
    )

    impacted_measurements = [find_in_qs(all_measurements, instance.uuid)]
    try:
        next_id = impacted_measurements[0].next_measurement.uuid
    except Measurement.DoesNotExist:
        next_id = None
    while next_id:
        next_measurement = find_in_qs(all_measurements, next_id)
        impacted_measurements.append(next_measurement)
        try:
            next_id = find_in_qs(
                all_measurements, next_measurement.next_measurement.uuid, "uuid"
            )
        except Measurement.DoesNotExist:
            next_id = None

    measurement_services = list(
        MeasurementService.objects.filter(measurement=instance)
        .select_related("service")
        .distinct()
    )

    try:
        final_json = {
            service_usage: {
                "service": service_usage.service,
                "measurement_service": next(
                    a
                    for a in measurement_services
                    if a.service.uuid == service_usage.service.uuid
                ),
                "amount": service_usage.amount,
            }
            for service_usage in services_usage
        }
    except Exception:
        # This will be raised if trying to add a Reporting that contains a ServiceUsage
        # related to a Service for which there's no MeasurementService created in that
        # Measurement. Could happen with an old Measurement.
        raise ValidationError("Erro ao medir apontamentos")

    bulk_measurement_service_list = []
    bulk_service_usage_list = []

    for service_usage, item in final_json.items():
        # Get all MeasurementServices that need to be updated
        # (current and following Measurements)
        service = item.get("measurement_service").service
        measurement_services = []
        for measurement in impacted_measurements:
            try:
                impacted_service = next(
                    a
                    for a in measurement.measurement_services.all()
                    if a.service.uuid == service.uuid
                )
                measurement_services.append(impacted_service)
            except StopIteration:
                # This service no longer exists in following measurement so no
                # need to update anything
                pass

        # Refresh balance in MeasurementService
        for measurement_service in measurement_services:
            # COMMENTED OUT TO ALLOW NEGATIVE BALANCES
            # WILL PROBABLY BE ADDED BACK IN SOMEDAY
            # if measurement_service.balance < item.get("amount"):
            #     try:
            #         name = service_usage.reporting.occurrence_type.name
            #     except Exception:
            #         name = "classe não encontrada"
            #
            #     raise ValidationError(
            #         "Balanço atual é menor que a medição. Classe = {}".format(
            #             name
            #         )
            #     )
            try:
                # check if instance of this same measurement_service already exists
                # in update list
                update = next(
                    a
                    for a in bulk_measurement_service_list
                    if a.uuid == measurement_service.uuid
                )
                update.balance -= item.get("amount")
            except StopIteration:
                measurement_service.balance -= item.get("amount")
                bulk_measurement_service_list.append(measurement_service)

        # Relate ServiceUsage with Measurement
        service_usage.measurement = instance
        bulk_service_usage_list.append(service_usage)

    bulk_update_with_history(
        bulk_measurement_service_list,
        MeasurementService,
        user=user,
        use_django_bulk=True,
    )
    bulk_update(bulk_service_usage_list, update_fields=["measurement"])

    return True


def remove_usages_from_measurement(instance, reportings, user):

    services_usage = (
        ServiceUsage.objects.filter(reporting__in=reportings)
        .select_related("service", "measurement")
        .distinct()
    )

    if not any([a.measurement for a in list(services_usage)]):
        raise ValidationError(
            "Um ou mais apontamentos selecionados não estão em uma medição"
        )

    all_measurements = (
        Measurement.objects.filter(company=instance.company)
        .select_related("previous_measurement", "next_measurement")
        .prefetch_related("measurement_services__service")
    )

    impacted_measurements = [find_in_qs(all_measurements, instance.uuid)]

    try:
        next_id = impacted_measurements[0].next_measurement.uuid
    except Measurement.DoesNotExist:
        next_id = None

    while next_id:
        next_measurement = find_in_qs(all_measurements, next_id)
        impacted_measurements.append(next_measurement)
        try:
            next_id = find_in_qs(
                all_measurements, next_measurement.next_measurement.uuid, "uuid"
            )
        except Measurement.DoesNotExist:
            next_id = None

    measurement_services = list(
        MeasurementService.objects.filter(measurement=instance)
        .select_related("service")
        .distinct()
    )

    try:
        final_json = {
            service_usage: {
                "service": service_usage.service,
                "measurement_service": next(
                    a
                    for a in measurement_services
                    if a.service.uuid == service_usage.service.uuid
                ),
                "amount": service_usage.amount,
            }
            for service_usage in services_usage
        }
    except Exception:
        # This will be raised if trying to add a Reporting that contains a ServiceUsage
        # related to a Service for which there's no MeasurementService created in that
        # Measurement. Could happen with an old Measurement.
        raise ValidationError("Erro ao medir apontamentos")

    bulk_measurement_service_list = []
    bulk_service_usage_list = []

    for service_usage, item in final_json.items():
        # Get all MeasurementServices that need to be updated
        # (current and following Measurements)
        service = item.get("measurement_service").service
        measurement_services = []
        for measurement in impacted_measurements:
            try:
                impacted_service = next(
                    a
                    for a in measurement.measurement_services.all()
                    if a.service.uuid == service.uuid
                )
                measurement_services.append(impacted_service)
            except StopIteration:
                # This service no longer exists in following measurement so no
                # need to update anything
                pass

        # Refresh balance in MeasurementService
        for measurement_service in measurement_services:
            try:
                # check if instance of this same measurement_service already exists
                # in update list
                update = next(
                    a
                    for a in bulk_measurement_service_list
                    if a.uuid == measurement_service.uuid
                )
                update.balance += item.get("amount")
            except StopIteration:
                measurement_service.balance += item.get("amount")
                bulk_measurement_service_list.append(measurement_service)

        # Relate ServiceUsage with Measurement
        service_usage.measurement = None
        bulk_service_usage_list.append(service_usage)

    bulk_update_with_history(
        bulk_measurement_service_list,
        MeasurementService,
        user=user,
        use_django_bulk=True,
    )
    bulk_update(bulk_service_usage_list, update_fields=["measurement"])

    return True


def create_or_update_services_and_usages(
    instance, reportings=None, user=None, update=True
):

    if not update and isinstance(instance, Reporting):
        create_usages_from_reporting(instance, user)
    elif update and isinstance(instance, Reporting):
        update_usages_from_reporting(instance, user)
    elif update and isinstance(instance, Measurement):
        update_usages_from_measurement(instance, reportings, user)

    return True


def create_services_from_measurement(measurement):

    services = list(Service.objects.filter(company=measurement.company))

    previous_measurement_services = list(
        MeasurementService.objects.filter(
            measurement=measurement.previous_measurement
        ).select_related("service")
    )

    bulk_create_list = []

    for service in services:
        try:
            balance = next(
                a
                for a in previous_measurement_services
                if a.service.uuid == service.uuid
            ).balance
        except StopIteration:
            balance = service.current_balance

        bulk_create_list.append(
            MeasurementService(
                service=service,
                measurement=measurement,
                unit_price=service.unit_price,
                adjustment_coefficient=service.adjustment_coefficient,
                balance=balance,
            )
        )

    bulk_create_with_history(bulk_create_list, MeasurementService)

    return True


def impact_current_balance(reporting, increase=False):

    services_usages = reporting.reporting_usage.all().select_related("service")

    bulk_service_list = []

    for item in services_usages:
        service = item.service
        amount = item.amount
        if amount:
            if increase:
                service.current_balance += amount
            else:
                service.current_balance -= amount
        else:
            continue
        bulk_service_list.append(service)

    if bulk_service_list:
        bulk_update(bulk_service_list, update_fields=["current_balance"])

    return True


def impact_measurement_balance(reporting, increase=False, update=False):
    service_usages = reporting.reporting_usage.all().select_related("service")
    if len(service_usages):
        measurement = service_usages[0].measurement
        if measurement:
            services = [a.service for a in service_usages]
            measurement_services = MeasurementService.objects.filter(
                service__in=services, measurement=measurement
            ).select_related("service")

            bulk_measurement_service_list = []
            for item in measurement_services:
                try:
                    usage = next(a for a in service_usages if a.service == item.service)
                    if increase:
                        item.balance += usage.amount
                    else:
                        item.balance -= usage.amount
                    bulk_measurement_service_list.append(item)
                except StopIteration:
                    pass

            bulk_update_with_history(
                bulk_measurement_service_list,
                MeasurementService,
                use_django_bulk=True,
            )

            return True

    return False


def create_using_resources(reporting, resources):
    """
    This function need to check, before creating the new ServiceUsage,
    if the existing ServiceUsages for that given Reporting are already
    related to a Measurement. If they are, relate the new one too.
    """
    measurement = None
    service_usages = reporting.reporting_usage.filter(measurement__isnull=False)

    if service_usages.exists():
        count = service_usages.aggregate(count=Count("measurement", distinct=True))
        if count["count"] > 1:
            raise ValidationError("Não pode haver diferentes Measurements")

        measurement = service_usages[0].measurement

    services = Service.objects.filter(company_id=reporting.company.pk)

    services_usages_list = []

    for service_id, amount in resources.items():
        try:
            service = next(a for a in services if str(a.pk) == service_id)
        except StopIteration:
            raise ValidationError("Serviço não encontrado")

        services_usages_list.append(
            ServiceUsage(
                service=service,
                reporting=reporting,
                measurement=measurement,
                amount=amount,
                formula={"backend": amount},
            )
        )

    if services_usages_list:
        ServiceUsage.objects.bulk_create(services_usages_list)

    return True
