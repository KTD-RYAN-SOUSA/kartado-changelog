import logging

import sentry_sdk
from django.conf import settings
from django.db import transaction
from django.db.models import prefetch_related_objects
from zappa.asynchronous import task

from apps.resources.models import ContractAdditive, ContractService
from apps.service_orders.models import ServiceOrderResource
from helpers.apps.contract_utils import get_total_price
from helpers.histories import bulk_update_with_history
from helpers.notifications import create_push_notifications
from helpers.signals import DisableSignals


@task
def calculate_contract_additive_values(instance_pk):
    try:
        contract_additive = ContractAdditive.objects.get(uuid=instance_pk)
        contract = contract_additive.contract
        additional_percentage = contract_additive.additional_percentage
        created_by = contract_additive.created_by
        company = contract_additive.company

        contract_number = contract.extra_info.get("r_c_number", "")
        error = True

        with transaction.atomic(savepoint=False):
            prefetch_related_objects([contract], "resources", "performance_services")

            resource_list = []

            for resource in contract.resources.all():
                resource.unit_price = round(
                    resource.unit_price * (1 + additional_percentage / 100), 4
                )
                resource_list.append(resource)

            if resource_list:
                bulk_update_with_history(
                    resource_list,
                    ServiceOrderResource,
                    use_django_bulk=True,
                    user=created_by,
                )

            performance_list = []

            for performance_service in contract.performance_services.all():
                if not isinstance(performance_service.price, (int, float)):
                    raise Exception()
                performance_service.price = round(
                    performance_service.price * (1 + additional_percentage / 100), 4
                )
                performance_list.append(performance_service)

            if performance_list:
                bulk_update_with_history(
                    performance_list,
                    ContractService,
                    use_django_bulk=True,
                    user=created_by,
                )

            contract.refresh_from_db()

            contract.total_price = round(get_total_price(contract), 4)

            with DisableSignals():
                contract.save()

        error = False
    except Exception as e:
        logging.error(f"Error adding ContractAdditive: {str(e)}")
        sentry_sdk.capture_exception(e)
    finally:
        url = "{}/#/SharedLink/Contract/{}/show/additives?company={}".format(
            settings.FRONTEND_URL, str(contract.pk), str(company.pk)
        )

        message = (
            f'A criação de aditivo no objeto "{contract_number}" foi bem sucedida.'
            if not error
            else f'A criação de aditivo no objeto "{contract_number}" NÃO pode ser concluída.'
        )

        create_push_notifications(
            [created_by], message, company, contract_additive, url=url
        )

        contract_additive.error = error
        contract_additive.done = True
        contract_additive.save()
