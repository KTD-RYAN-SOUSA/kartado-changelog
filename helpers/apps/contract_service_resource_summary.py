import datetime
from typing import List

from django.db.models import Q
from rest_framework.response import Response

from apps.daily_reports.models import (
    DailyReportEquipment,
    DailyReportVehicle,
    DailyReportWorker,
)
from apps.resources.models import Contract, ContractService, ContractServiceBulletin
from apps.service_orders.models import MeasurementBulletin, ProcedureResource
from helpers.apps.performance_calculations import (
    ContracServiceScope,
    ContractItemPerformanceScope,
    MeasurementBulletinScope,
)


class ResourceSummaryEndpoint:
    def __init__(self, contract_service, request):
        self.contract_service = contract_service
        self.request = request
        self.extra_query = {}
        self.measurement_bulletin_obj = None
        self.administration_objects = []
        self.unit_price_objects = []
        self.performance_objects = []
        self.field_surveys_average = {}
        self.average_grade_percent_infos = {}
        self.contract_items_performance_scope = []
        self.section_total_price = 0.0

    def set_params(self):
        if "measurement_bulletin" in self.request.query_params:
            meassurement_bulletin_uuid = self.request.query_params[
                "measurement_bulletin"
            ]
            self.measurement_bulletin_obj = MeasurementBulletin.objects.filter(
                uuid=meassurement_bulletin_uuid
            )[0]
            self.extra_query["measurement_bulletin"] = meassurement_bulletin_uuid

    def set_response_items(self):
        daily_models = [
            DailyReportEquipment,
            DailyReportVehicle,
            DailyReportWorker,
        ]
        for daily_model in daily_models:
            objects = daily_model.objects.filter(
                contract_item_administration__contract_item_administration_services=self.contract_service,
                **self.extra_query
            ).prefetch_related(
                "contract_item_administration",
                "contract_item_administration__resource",
                "contract_item_administration__resource__resource",
                "contract_item_administration__resource__entity",
            )
            self.administration_objects.extend(objects)

        self.unit_price_objects = list(
            ProcedureResource.objects.filter(
                service_order_resource__resource_contract_unit_price_items__contract_item_unit_price_services=self.contract_service,
                **self.extra_query
            ).prefetch_related(
                "service_order_resource",
                "service_order_resource__resource",
                "service_order_resource__resource_contract_unit_price_items",
                "service_order_resource__entity",
            )
        )

        if self.contract_service.contract_item_performance.exists():
            self.contract_service = ContractServiceBulletin.objects.get(
                parent_uuid=self.contract_service.uuid,
                measurement_bulletins=self.measurement_bulletin_obj,
            )
            self.performance_objects = list(
                self.contract_service.contract_item_performance.all().prefetch_related(
                    "resource", "resource__resource"
                )
            )
        else:
            self.performance_objects = []

    def work_days(self, start_date, end_date, exclude=(6, 7)):
        if not start_date or not end_date:
            return 0
        start_date = datetime.date(start_date.year, start_date.month, start_date.day)
        end_date = datetime.date(end_date.year, end_date.month, end_date.day)
        work_days = 0
        gap = (end_date - start_date).days
        for i in range(gap + 1):
            if start_date.isoweekday() not in exclude:
                work_days += 1
            start_date += datetime.timedelta(days=1)
        return work_days

    def get_mb_field_surveys_data(self, contract_item_performance_scope) -> List[dict]:
        field_surveys_data = []
        contract_item_performance_scope.calculate_field_surveys_average()
        for (
            field_survey,
            field_survey_average,
        ) in contract_item_performance_scope.field_surveys_average_infos.items():
            data = {
                "uuid": str(field_survey.pk),
                "name": field_survey.name,
                "average_grade": field_survey_average,
                "executed_at": field_survey.executed_at,
            }
            field_surveys_data.append(data)
        return field_surveys_data

    def generate_average_grade_percent_data(self, contra_item_performance_scope):
        if self.measurement_bulletin_obj:
            return contra_item_performance_scope.calculate_average_grade_percent(
                self.measurement_bulletin_obj.contract.higher_grade
            )
        return 0.0

    def get_field_surveys(self):
        if self.measurement_bulletin_obj:
            return self.measurement_bulletin_obj.bulletin_surveys.all()
        return []

    def calculate_section_total_price(self):
        """
        PERFORMS THE CALCULUS "G" FROM THE ISSUE KTD-1156
        """
        try:
            maximum_price = (
                self.contract_service.price
                / self.measurement_bulletin_obj.contract.performance_months
            )
        except Exception:
            maximum_price = 0.0
        if self.measurement_bulletin_obj:
            mb_scope = MeasurementBulletinScope(
                self.measurement_bulletin_obj.contract,
                measurement_bulletin=self.measurement_bulletin_obj,
            )
            mb_scope.calculate_mb_average_grade_percent()
            self.section_total_price = mb_scope.average_grade_percent * maximum_price

    def get_item_total_price(self, contract_item_performance):
        """
        PERFORMS THE CALCULUS "F" FROM THE ISSUE KTD-1156
        """
        return contract_item_performance.weight / 100 * self.section_total_price

    def get_response(self):
        if "measurement_bulletin" in self.request.query_params:
            if self.measurement_bulletin_obj.work_day is not None:
                work_days = self.measurement_bulletin_obj.work_day
            else:
                end_date = self.measurement_bulletin_obj.period_ends_at
                start_date = self.measurement_bulletin_obj.period_starts_at
                if end_date and start_date:
                    work_days = self.work_days(start_date, end_date)
                else:
                    work_days = 22
        else:
            work_days = 22

        return_objects = {}
        contract = (
            Contract.objects.filter(
                Q(unit_price_services=self.contract_service)
                | Q(administration_services=self.contract_service)
                | Q(performance_services=self.contract_service)
            ).first()
            if isinstance(self.contract_service, ContractService)
            else Contract.objects.filter(
                contract_services_bulletins=self.contract_service
            ).first()
        )
        total_contract_month = (
            contract.performance_months
            if contract
            and contract.performance_months is not None
            and contract.performance_months > 0
            else 12
        )
        for obj in self.administration_objects:
            obj_contract_item = obj.contract_item_administration
            if obj_contract_item.pk not in return_objects:
                return_objects[obj_contract_item.pk] = {
                    "name": obj_contract_item.resource.resource.name,
                    "uuid": obj_contract_item.pk,
                    "service_order_resource": obj_contract_item.resource.uuid,
                    "entity": obj_contract_item.resource.entity.uuid
                    if obj_contract_item.resource.entity
                    else None,
                    "type": obj._meta.model.__name__,
                    "unit": obj_contract_item.resource.resource.unit,
                    "unit_price": obj.unit_price
                    if obj.unit_price is not None
                    else obj_contract_item.resource.unit_price,
                    "total_price": obj.total_price or 0,
                    "average_used_amount": obj.amount / work_days,
                    "amount_per_period": obj_contract_item.resource.amount
                    / total_contract_month,
                    "sort_string": obj_contract_item.sort_string,
                }
            else:
                return_objects[obj_contract_item.pk]["total_price"] += (
                    obj.total_price or 0
                )
                return_objects[obj_contract_item.pk]["average_used_amount"] += (
                    obj.amount / work_days
                )

        for obj in self.unit_price_objects:
            obj_contract_item = (
                obj.service_order_resource.resource_contract_unit_price_items.first()
            )
            if obj_contract_item.pk not in return_objects:
                return_objects[obj_contract_item.pk] = {
                    "name": obj.service_order_resource.resource.name,
                    "uuid": obj_contract_item.pk,
                    "service_order_resource": obj.service_order_resource.uuid,
                    "entity": obj.service_order_resource.entity.uuid
                    if obj.service_order_resource.entity
                    else None,
                    "type": obj._meta.model.__name__,
                    "unit": obj.service_order_resource.resource.unit,
                    "unit_price": obj.unit_price
                    if obj.unit_price is not None
                    else obj.service_order_resource.unit_price,
                    "total_price": obj.total_price or 0,
                    "average_used_amount": obj.amount,
                    "sort_string": obj_contract_item.sort_string,
                }
            else:
                return_objects[obj_contract_item.pk]["average_used_amount"] += (
                    obj.amount or 0
                )
                return_objects[obj_contract_item.pk]["total_price"] += (
                    obj.total_price or 0
                )

        self.calculate_section_total_price()
        for obj in self.performance_objects:
            if obj.parent_uuid not in return_objects:
                field_surveys = self.get_field_surveys()
                contra_item_performance_scope = ContractItemPerformanceScope(
                    obj, field_surveys
                )
                field_surveys_data = self.get_mb_field_surveys_data(
                    contra_item_performance_scope
                )

                return_objects[obj.parent_uuid] = {
                    "name": obj.resource.resource.name,
                    "uuid": obj.parent_uuid,
                    "average_grade_percent": self.generate_average_grade_percent_data(
                        contra_item_performance_scope
                    ),
                    "service_order_resource": obj.resource.pk,
                    "type": "ContractItemPerformance",
                    "total_price": self.get_item_total_price(obj),
                    "weight": obj.weight / 100,
                    "field_surveys": field_surveys_data,
                    "sort_string": obj.sort_string,
                }
            else:
                return_objects[obj.parent_uuid]["total_price"] += obj.total_price or 0
            self.contract_items_performance_scope.append(contra_item_performance_scope)
        contract_service_scope = ContracServiceScope(
            self.contract_items_performance_scope, self.contract_service
        )
        return Response(
            {
                "type": "ResourceSummary",
                "attributes": {
                    "summary": return_objects.values(),
                    "average_grade_percent": contract_service_scope.calculate_weighted_performances_average(),
                    "total_price": self.section_total_price,
                    "contract_service_price_divided": self.contract_service.price
                    / total_contract_month,
                    "weight": self.contract_service.weight or 0,
                },
            }
        )
