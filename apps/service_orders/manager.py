from django.db.models import F, Manager


class ServiceOrderResourceManager(Manager):
    def get_queryset(self):
        return (super().get_queryset()).annotate(
            balance=(F("unit_price") * F("remaining_amount"))
        )
