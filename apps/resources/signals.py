from django.conf import settings
from django.db.models import F, Q
from django.db.models.signals import (
    post_delete,
    post_init,
    post_save,
    pre_delete,
    pre_save,
)
from django.dispatch import receiver

from apps.resources.models import (
    Contract,
    ContractAdditive,
    ContractItemAdministration,
    ContractItemPerformance,
    ContractItemUnitPrice,
    ContractService,
    ContractServiceBulletin,
    FieldSurvey,
    FieldSurveySignature,
)
from apps.to_dos.models import ToDoAction
from helpers.apps.contract_utils import get_spent_price, get_total_price
from helpers.apps.todo import generate_todo
from helpers.middlewares import get_current_user
from helpers.notifications import create_push_notifications
from helpers.signals import DisableSignals, auto_add_number


@receiver(post_save, sender=Contract)
def generate_contract_todos(sender, instance, created, **kwargs):
    try:
        company = (
            instance.firm.company if instance.firm else instance.subcompany.company
        )
        todo_action = ToDoAction.objects.get(
            default_options="see", company_group=company.company_group
        )
        send_to = []
        if instance.responsibles_hirer.exists():
            for user in instance.responsibles_hirer.all():
                send_to.append(user)
        if instance.responsibles_hired.exists():
            for user in instance.responsibles_hired.all():
                send_to.append(user)
        description = {}
        description["description"] = instance.name
        if instance.extra_info["r_c_number"]:
            description["contract"] = instance.extra_info["r_c_number"]
        if created:
            description["activity"] = "CONTRACT_CREATED_MESSAGE"
        if not (created):
            description["activity"] = "CONTRACT_EDITED_MESSAGE"

        url = "{}/#/SharedLink/Contract/{}/show?company={}".format(
            settings.FRONTEND_URL, str(instance.uuid), str(company.uuid)
        )
        send_to = set(send_to)
        if len(send_to):
            generate_todo(
                company=company,
                responsibles=send_to,
                action=todo_action,
                due_at=None,
                is_done=False,
                description=description,
                url=url,
                created_by=get_current_user(),
                independent_todos=True,
                resource=instance,
            )
    except Exception:
        pass


@receiver(pre_delete, sender=ContractService)
def delete_items_related_to_contract_service(sender, instance, **kwargs):
    if instance.contract_item_unit_prices.exists():
        instance.contract_item_unit_prices.all().delete()

    if instance.contract_item_administration.exists():
        instance.contract_item_administration.all().delete()

    if instance.contract_item_performance.exists():
        instance.contract_item_performance.all().delete()


@receiver(pre_delete, sender=ContractItemUnitPrice)
def delete_unit_resource_related_to_contract_item(sender, instance, **kwargs):

    try:
        contract = instance.resource.contract
        instance.resource.delete()
    except Exception:
        pass
    else:
        contract.total_price = get_total_price(contract)
        contract.spent_price = get_spent_price(contract)
        contract.save()


@receiver(pre_delete, sender=ContractItemAdministration)
def delete_adm_resource_related_to_contract_item(sender, instance, **kwargs):
    try:
        contract = instance.resource.contract

        instance.resource.delete()
    except Exception:
        pass
    else:
        contract.total_price = get_total_price(contract)
        contract.spent_price = get_spent_price(contract)
        contract.save()


@receiver(pre_delete, sender=ContractItemPerformance)
def delete_perf_resource_related_to_contract_item(sender, instance, **kwargs):
    try:
        instance.resource.delete()
    except Exception:
        pass


@receiver(post_delete, sender=ContractItemPerformance)
def post_delete_perf_resource_related_to_contract_item(sender, instance, **kwargs):

    try:
        contract = instance.resource.contract

        instance.resource.delete()
    except Exception:
        pass
    else:
        contract.total_price = get_total_price(contract)
        contract.spent_price = get_spent_price(contract)
        contract.save()


@receiver(post_init, sender=FieldSurvey)
def keep_orignal_approval_status(sender, instance, **kwargs):
    instance.original_approval_status = instance.approval_status


@receiver(post_save, sender=FieldSurvey)
def send_signature_notifications(sender, instance, **kwargs):
    if instance.original_approval_status != "APPROVED_APPROVAL":
        if instance.approval_status == "APPROVED_APPROVAL":
            user = get_current_user()
            hireds = instance.responsibles_hired.exclude(uuid=user.pk)
            hirers = instance.responsibles_hirer.exclude(uuid=user.pk)
            all_responsibles = hireds.union(hirers)
            notification_message = "Você tem uma nova avaliação de campo para assinar"
            company = instance.contract.subcompany.company
            url = "{}/#/SharedLink/FieldSurvey/{}/?company={}".format(
                settings.FRONTEND_URL, str(instance.uuid), str(company.pk)
            )
            create_push_notifications(
                all_responsibles, notification_message, company, instance, url
            )


@receiver(post_save, sender=FieldSurvey)
def calculate_contract_prices_after_survey_change(sender, instance, **kwargs):
    instance_has_measurement_bulletin = instance.measurement_bulletin is not None
    if not instance_has_measurement_bulletin:
        try:
            if not instance._state.adding:
                contract = instance.contract
                contract.total_price = get_total_price(contract)
                contract.spent_price = get_spent_price(contract)
                with DisableSignals():
                    contract.save()
        except Exception:
            pass


@receiver(pre_save, sender=FieldSurvey)
def auto_add_multiple_daily_report_number(sender, instance, **kwargs):
    key_name = "FS_name_format"
    auto_add_number(instance, key_name)


@receiver(post_save, sender=FieldSurveySignature)
def change_fields_survey_status(sender, instance, **kwargs):
    # avoid unecessary query
    if instance.field_survey.status != "SURVEY_APPROVED":
        if not instance.field_survey.signatures.filter(signed_at__isnull=True).exists():
            instance.field_survey.status = "SURVEY_APPROVED"
            instance.field_survey.save()


@receiver(pre_delete, sender=ContractItemUnitPrice)
def balance_unit_items(sender, instance, **kwargs):
    if instance.order is not None:
        contract_service = instance.contract_item_unit_price_services.first()

        contract_items = (
            ContractItemUnitPrice.objects.filter(
                contract_item_unit_price_services=contract_service,
                order__gt=instance.order,
            )
            .exclude(pk=instance.pk)
            .exclude(order__isnull=True)
        )

        contract_items.update(order=F("order") - 1)


@receiver(pre_delete, sender=ContractItemAdministration)
def balance_adm_items(sender, instance, **kwargs):
    if instance.order is not None:
        contract_service = instance.contract_item_administration_services.first()

        contract_items = (
            ContractItemAdministration.objects.filter(
                contract_item_administration_services=contract_service,
                order__gt=instance.order,
            )
            .exclude(pk=instance.pk)
            .exclude(order__isnull=True)
        )

        contract_items.update(order=F("order") - 1)


@receiver(pre_delete, sender=ContractItemPerformance)
def balance_perf_items(sender, instance, **kwargs):
    if instance.order is not None:
        contract_service = instance.contract_item_performance_services.first()

        contract_items = (
            ContractItemPerformance.objects.filter(
                contract_item_performance_services=contract_service,
                order__gt=instance.order,
            )
            .exclude(pk=instance.pk)
            .exclude(order__isnull=True)
        )
        contract_items.update(order=F("order") - 1)


@receiver(pre_delete, sender=Contract)
def delete_contract_services(sender, instance, **kwargs):
    contract_services = ContractService.objects.filter(
        Q(unit_price_service_contracts=instance)
        | Q(administration_service_contracts=instance)
        | Q(performance_service_contracts=instance)
    )

    contract_services.delete()


@receiver(pre_delete, sender=ContractServiceBulletin)
def delete_contract_services_bulletins(sender, instance, **kwargs):
    if instance.contract_item_performance.exists():
        instance.contract_item_performance.all().delete()


@receiver(pre_save, sender=ContractAdditive)
def auto_add_contract_additive_number(sender, instance, **kwargs):
    key_name = "ADV_name_format"
    auto_add_number(instance, key_name)
