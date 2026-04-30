from django.db.models.signals import pre_save
from django.dispatch import receiver
from fieldsignals.signals import pre_save_changed
from rest_framework.exceptions import ValidationError
from sequences import get_next_value

from .models import GoalAggregate, Service, ServiceSpecs


@receiver(pre_save_changed, sender=Service)
def update_balances(sender, instance, changed_fields, **kwargs):
    if not instance._state.adding:
        for field, (old, new) in changed_fields.items():
            if field == "total_amount":
                new_value = new - old
                instance.current_balance += new_value
                if instance.current_balance < 0.0:
                    raise ValidationError(
                        "O valor de current_balance ou last_measured_balance não pode ser negativo"
                    )


@receiver(pre_save, sender=ServiceSpecs)
def check_formula(sender, instance, **kwargs):
    if "backend" not in instance.formula.keys():
        raise ValidationError("A Formula não foi devidamente implementada.")


@receiver(pre_save, sender=GoalAggregate)
def fill_number(sender, instance, **kwargs):
    if not instance.number:
        instance.number = get_next_value(
            "goal-aggregate-company-{}".format(instance.company_id)
        )
