from functools import reduce

from rest_framework.response import Response
from rest_framework_json_api.utils import format_field_names

# Models
from apps.service_orders.models import ProcedureResource, ServiceOrderResource


class BulletinSummaryEndpoint:
    def __init__(self, obj):
        self.obj = obj

    def format(self, obj, format_type="camelize"):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, dict):
                    obj[key] = format_field_names(self.format(value), format_type)
                elif isinstance(value, list):
                    list_temp = value.copy()
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            list_temp[i] = format_field_names(
                                self.format(item), format_type
                            )
                        else:
                            list_temp[i] = item
                    obj[key] = list_temp

        return obj

    def get_response(self):
        old_bulletins = self.obj.contract.bulletins.filter(
            creation_date__lt=self.obj.creation_date
        )

        current_procedure_resources = self.obj.bulletin_resources.all()
        current_s_o_resources = (
            ServiceOrderResource.objects.filter(
                serviceorderresource_procedures__in=current_procedure_resources
            )
            .select_related("resource")
            .distinct()
        )

        old_procedure_resources = ProcedureResource.objects.filter(
            measurement_bulletin__in=old_bulletins,
            service_order_resource__in=current_s_o_resources,
        ).distinct()

        s_o_resources_summary = []

        def acc_amount(acc, val):
            return acc + val.amount

        def acc_total_price(acc, val):
            return acc + val.total_price

        for s_o_resource in current_s_o_resources:
            cur_pro_rec = [
                x
                for x in current_procedure_resources
                if x.service_order_resource_id == s_o_resource.uuid
            ]
            old_pro_rec = [
                x
                for x in old_procedure_resources
                if x.service_order_resource_id == s_o_resource.uuid
            ]

            cur_total_price = reduce(acc_total_price, cur_pro_rec, 0)

            cur_used_amount = reduce(acc_amount, cur_pro_rec, 0)
            old_used_amount = reduce(acc_amount, old_pro_rec, 0)

            s_o_resources_summary.append(
                {
                    "uuid": str(s_o_resource.pk),
                    "entity_id": str(s_o_resource.entity.pk)
                    if s_o_resource.entity
                    else "",
                    "name": s_o_resource.resource.name,
                    "unit": s_o_resource.resource.unit,
                    "used_amount": cur_used_amount,
                    "unit_price": s_o_resource.unit_price,
                    "total_price": cur_total_price,
                    "previous_used_amount": old_used_amount,
                    "current_balance": (
                        s_o_resource.amount - cur_used_amount - old_used_amount
                    )
                    * s_o_resource.unit_price,
                }
            )

        return Response(self.format(s_o_resources_summary))
