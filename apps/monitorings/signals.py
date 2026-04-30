from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from helpers.signals import auto_add_number
from helpers.strings import get_autonumber_array

from .models import (
    MaterialItem,
    MaterialUsage,
    MonitoringCollect,
    MonitoringCycle,
    MonitoringPlan,
    MonitoringRecord,
    OperationalCycle,
)


@receiver(pre_save, sender=MonitoringPlan)
def auto_add_plan_number(sender, instance, **kwargs):
    if instance.number in [None, ""]:
        instance_type = "PM"
        key_name = "{}_name_format".format(instance_type)
        # Get datetime and serial arrays
        data = get_autonumber_array(instance.company.uuid, instance_type)
        # Get company prefix
        if "company_prefix" in instance.company.metadata:
            data["prefixo"] = instance.company.metadata["company_prefix"]
        else:
            data["prefixo"] = "[{}]".format(instance.company.name)
        # Make number
        try:
            if key_name in instance.company.metadata:
                number = instance.company.metadata[key_name].format(**data)
            else:
                raise Exception("Variáveis de nome inválidas!")
        except Exception as e:
            print(e)
            # Fallback
            # UHIT-RG-2018.0001
            number = "{prefixo}-{nome}-{anoCompleto}.{serialAno}".format(**data)

        instance.number = number


@receiver(pre_save, sender=MonitoringCycle)
def auto_add_cycle_number(sender, instance, **kwargs):
    if instance.number in [None, ""]:
        instance_type = "CM"
        key_name = "{}_name_format".format(instance_type)
        company = instance.monitoring_plan.company
        # Get datetime and serial arrays
        data = get_autonumber_array(company.uuid, instance_type)
        # Get company prefix
        if "company_prefix" in company.metadata:
            data["prefixo"] = company.metadata["company_prefix"]
        else:
            data["prefixo"] = "[{}]".format(company.name)
        # Make number
        try:
            if key_name in company.metadata:
                number = company.metadata[key_name].format(**data)
            else:
                raise Exception("Variáveis de nome inválidas!")
        except Exception as e:
            print(e)
            # Fallback
            # UHIT-RG-2018.0001
            number = "{prefixo}-{nome}-{anoCompleto}.{serialAno}".format(**data)

        instance.number = number


@receiver(pre_save, sender=MonitoringRecord)
def auto_add_record_number(sender, instance, **kwargs):
    if instance.number in [None, ""]:
        instance_type = "RM"
        key_name = "{}_name_format".format(instance_type)
        company = instance.company
        # Get datetime and serial arrays
        data = get_autonumber_array(company.uuid, instance_type)
        # Get company prefix
        if "company_prefix" in company.metadata:
            data["prefixo"] = company.metadata["company_prefix"]
        else:
            data["prefixo"] = "[{}]".format(company.name)
        # Make number
        try:
            if key_name in company.metadata:
                number = company.metadata[key_name].format(**data)
            else:
                raise Exception("Variáveis de nome inválidas!")
        except Exception as e:
            print(e)
            # Fallback
            # UHIT-RG-2018.0001
            number = "{prefixo}-{nome}-{anoCompleto}.{serialAno}".format(**data)

        instance.number = number


@receiver(pre_save, sender=MonitoringCollect)
def auto_add_collect_number(sender, instance, **kwargs):
    if instance.number in [None, ""]:
        instance_type = "COM"
        key_name = "{}_name_format".format(instance_type)
        company = instance.company
        # Get datetime and serial arrays
        data = get_autonumber_array(company.uuid, instance_type)
        # Get company prefix
        if "company_prefix" in company.metadata:
            data["prefixo"] = company.metadata["company_prefix"]
        else:
            data["prefixo"] = "[{}]".format(company.name)
        # Make number
        try:
            if key_name in company.metadata:
                number = company.metadata[key_name].format(**data)
            else:
                raise Exception("Variáveis de nome inválidas!")
        except Exception as e:
            print(e)
            # Fallback
            # UHIT-RG-2018.0001
            number = "{prefixo}-{nome}-{anoCompleto}.{serialAno}".format(**data)

        instance.number = number


@receiver(post_save, sender=MaterialItem)
def auto_fill_material_item(sender, instance, created, **kwargs):
    if created:
        try:
            MaterialItem.objects.filter(pk=instance.pk).update(
                remaining_amount=instance.amount
            )
        except Exception:
            pass


@receiver(pre_save, sender=OperationalCycle)
def auto_add_operational_cycle_number(sender, instance, **kwargs):
    key_name = "OC_name_format"
    auto_add_number(instance, key_name)


@receiver(pre_delete, sender=MaterialUsage)
def change_material_item_remaining_amount(sender, instance, **kwargs):
    material_item = instance.material_item
    material_item.remaining_amount += instance.amount
    material_item.used_price -= instance.amount * material_item.unit_price
    material_item.save()
