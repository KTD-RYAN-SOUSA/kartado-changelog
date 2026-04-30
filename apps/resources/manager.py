from django.db.models import F, Manager


class ContractManager(Manager):
    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .annotate(remaining_price=(F("total_price") - F("spent_price")))
        )
        return qs


class ContractItemAdministrationManager(Manager):
    def get_queryset(self):
        return (super().get_queryset()).annotate(
            balance=(F("resource__unit_price") * F("resource__remaining_amount"))
        )


class ContractItemUnitPriceManager(Manager):
    def get_queryset(self):
        return (super().get_queryset()).annotate(
            balance=(F("resource__unit_price") * F("resource__remaining_amount"))
        )
