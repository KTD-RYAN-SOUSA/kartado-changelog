from django.db.models.signals import pre_save
from django.dispatch import receiver

from helpers.signals import auto_add_number

from .models import QualityAssay, QualitySample


@receiver(pre_save, sender=QualitySample)
def auto_add_quality_sample_number(sender, instance, **kwargs):
    key_name = "QS_name_format"
    auto_add_number(instance, key_name)


@receiver(pre_save, sender=QualityAssay)
def auto_add_quality_assay_number(sender, instance, **kwargs):
    key_name = "QA_name_format"
    auto_add_number(instance, key_name)
