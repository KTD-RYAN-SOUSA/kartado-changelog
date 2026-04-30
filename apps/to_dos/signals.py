from datetime import datetime

from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import ToDo


@receiver(pre_save, sender=ToDo)
def to_do_if_action_see(sender, instance, **kwargs):
    instance_actual = ToDo.objects.filter(pk=instance.pk).first()

    if (
        instance_actual is not None
        and getattr(instance, "action")
        and instance.action.default_options == "see"
    ):
        old_read_at = instance_actual.read_at
        old_is_done = instance_actual.is_done

        new_read_at = instance.read_at
        new_is_done = instance.is_done

        if new_read_at and old_read_at is None:
            instance.is_done = True

        elif new_read_at is None and old_read_at:
            instance.is_done = False

        elif new_is_done and not old_is_done:
            instance.read_at = datetime.now()

        elif not new_is_done and old_is_done:
            instance.read_at = None
