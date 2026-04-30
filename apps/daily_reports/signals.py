import threading

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from fieldsignals.signals import pre_save_changed

from apps.daily_reports.services import (
    send_daily_report_file_to_webhook,
    send_daily_report_same_db_edit_to_n8n,
)
from helpers.apps.daily_reports import (
    calculate_board_item_total_price,
    create_and_update_contract_usage,
    update_resource_amounts,
)
from helpers.middlewares import get_current_request
from helpers.signals import auto_add_number
from helpers.strings import get_obj_from_path

from .models import (
    DailyReport,
    DailyReportEquipment,
    DailyReportVehicle,
    DailyReportWorker,
    MultipleDailyReport,
    MultipleDailyReportFile,
)


@receiver(post_save, sender=MultipleDailyReportFile)
def on_multiple_daily_report_file_create(sender, instance, created, **kwargs):
    if created:
        mdr = instance.multiple_daily_report
        if not mdr or not mdr.firm:
            return

        company = mdr.company
        firm_uuids_for_webhook = (
            get_obj_from_path(
                company.metadata,
                "firm_uuids_that_should_call_daily_report_webhook",
            )
            or []
        )

        should_trigger_signal = str(mdr.firm.uuid) in firm_uuids_for_webhook

        wsgi_request = get_current_request()
        if wsgi_request and should_trigger_signal:
            raw_body = getattr(wsgi_request, "raw_body", None)
            if not raw_body:
                return
            # Modo CROSS-DB: condicionado à firm estar na lista
            send_daily_report_file_to_webhook(
                instance, raw_body, instance.multiple_daily_report.company
            )


@receiver(pre_save, sender=DailyReport)
def auto_add_daily_report_number(sender, instance, **kwargs):
    key_name = "DR_name_format"
    auto_add_number(instance, key_name)


@receiver(pre_save, sender=MultipleDailyReport)
def auto_add_multiple_daily_report_number(sender, instance, **kwargs):
    key_name = "MDR_name_format"
    auto_add_number(instance, key_name)


# DailyReportContractUsage creation
@receiver(post_save, sender=DailyReportWorker)
def auto_create_contract_usage_and_fill_contract_prices_for_worker(
    sender, instance, **kwargs
):
    create_and_update_contract_usage(instance)


@receiver(post_save, sender=DailyReportEquipment)
def auto_create_contract_usage_and_fill_contract_prices_for_equipment(
    sender, instance, **kwargs
):
    create_and_update_contract_usage(instance)


@receiver(post_save, sender=DailyReportVehicle)
def auto_create_contract_usage_and_fill_contract_prices_for_vehicle(
    sender, instance, **kwargs
):
    create_and_update_contract_usage(instance)


# Handle changing fields of ServiceOrderResource
@receiver(pre_save_changed, sender=DailyReportWorker)
def update_resource_amounts_for_worker(sender, instance, changed_fields, **kwargs):
    update_resource_amounts(instance, changed_fields)


@receiver(pre_save_changed, sender=DailyReportEquipment)
def update_resource_amounts_for_equipment(sender, instance, changed_fields, **kwargs):
    update_resource_amounts(instance, changed_fields)


@receiver(pre_save_changed, sender=DailyReportVehicle)
def update_resource_amounts_for_vehicle(sender, instance, changed_fields, **kwargs):
    update_resource_amounts(instance, changed_fields)


# Calculate the total_price
@receiver(pre_save, sender=DailyReportWorker)
def calc_daily_report_worker_price(sender, instance, **kwargs):
    if (
        instance.contract_item_administration
        and instance.contract_item_administration.resource
    ):
        if instance._state.adding or instance.unit_price is None:
            instance.unit_price = (
                instance.contract_item_administration.resource.unit_price
            )
    instance.total_price = calculate_board_item_total_price(instance)


@receiver(pre_save, sender=DailyReportEquipment)
def calc_daily_report_equipment_price(sender, instance, **kwargs):
    if (
        instance.contract_item_administration
        and instance.contract_item_administration.resource
    ):
        if instance._state.adding or instance.unit_price is None:
            instance.unit_price = (
                instance.contract_item_administration.resource.unit_price
            )
    instance.total_price = calculate_board_item_total_price(instance)


@receiver(pre_save, sender=DailyReportVehicle)
def calc_daily_report_vehicle_price(sender, instance, **kwargs):
    if (
        instance.contract_item_administration
        and instance.contract_item_administration.resource
    ):
        if instance._state.adding or instance.unit_price is None:
            instance.unit_price = (
                instance.contract_item_administration.resource.unit_price
            )
    instance.total_price = calculate_board_item_total_price(instance)


# Same-Database Edit Webhook
@receiver(post_save, sender=MultipleDailyReport)
def trigger_edit_webhook_for_same_db(sender, instance, created, **kwargs):
    """
    Dispara webhook de edição para N8N quando um RDO é editado (PATCH).

    Apenas dispara se:
    - RDO está sendo editado (não é criação)
    - RDO possui legacy_number (é um original com cópia no mesmo banco)
    - Company possui webhook URL configurada em metadata
    """
    import logging

    logger = logging.getLogger(__name__)

    if created:
        # Criação usa outro webhook (POST), não PATCH
        logger.debug(
            f"[EDIT_WEBHOOK_SIGNAL] RDO {instance.uuid} é novo (created=True), ignorando"
        )
        return

    logger.info(
        f"[EDIT_WEBHOOK_SIGNAL] ✓ RDO editado: {instance.uuid} (number={instance.number})"
    )

    # Usar on_commit para garantir que workers e demais relacionamentos já estejam
    # commitados no banco antes de disparar o webhook (evita race condition com n8n)
    def _fire_and_forget():
        threading.Thread(
            target=send_daily_report_same_db_edit_to_n8n,
            args=(instance,),
            daemon=True,
        ).start()

    transaction.on_commit(_fire_and_forget)
