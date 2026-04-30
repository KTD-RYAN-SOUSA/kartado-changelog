from collections import defaultdict
from math import ceil, floor
from typing import List

from apps.resources.models import FieldSurveyRoad


class ContractItemPerformanceScope:
    def __init__(
        self,
        contract_item_performance,
        field_surveys=[],
        survey_roads=[],
        survey_has_bulletin=True,
    ):
        self.contract_item_performance = contract_item_performance
        self.field_surveys = field_surveys
        self.field_surveys_average_infos = {}
        self.average_grade_percent_infos = {}
        self.mb_average_grade_percent_infos = {}
        self.field_surveys_average_infos = {}
        self.contract_item_performance_average_infos = {}
        self.average_grade_percent = 0.0
        self.survey_roads = survey_roads
        self.survey_has_bulletin = survey_has_bulletin

    def calculate_field_surveys_average(self):
        """
        PERFORMS THE CALCULUS "A" FROM THE ISSUE KTD-1156
        returns a list containing the average of each field survey that was passed as a parameter related
        to one contract item performance.
        """
        average = 0.0
        if not self.field_surveys:
            return average
        if not self.survey_roads:
            self.survey_roads = FieldSurveyRoad.objects.filter(
                contract_id__in=[fs.contract_id for fs in self.field_surveys]
            )
        for field_survey in self.field_surveys:
            if field_survey.manual is True:
                average = field_survey.final_grade / 10
                self.field_surveys_average_infos[field_survey] = average
            else:
                total_grade = 0
                total_km = 0
                for road_id, value in field_survey.grades.items():
                    if not isinstance(value, dict):
                        continue

                    data_key = (
                        self.contract_item_performance.parent_uuid
                        if self.survey_has_bulletin
                        else self.contract_item_performance.uuid
                    )
                    data = value.get(str(data_key))
                    if data:
                        for value in data.values():
                            total_grade += value

                for survey_road in self.survey_roads:
                    if survey_road.contract_id == field_survey.contract_id:
                        total_km += ceil(survey_road.end_km) - floor(
                            survey_road.start_km
                        )
                try:
                    average = total_grade / total_km
                except Exception:
                    average = 0.0
                self.field_surveys_average_infos[field_survey] = average
        return average

    def calculate_average_grade_percent(self, higher_value) -> float:
        """
        PERFORMS THE CALCULUS "B" FROM THE ISSUE KTD-1156
        Returns the arithmetic average of the items passed in the parameter divided by the highest value.
        """
        try:
            self.average_grade_percent = (
                sum(self.field_surveys_average_infos.values())
                / len(self.field_surveys_average_infos)
            ) / higher_value

        except Exception:
            self.average_grade_percent = 0.0

        return self.average_grade_percent


class ContracServiceScope:
    def __init__(
        self,
        contract_items_performance_scope: List[ContractItemPerformanceScope],
        contract_service,
    ):
        self.contract_items_performance_scope = contract_items_performance_scope
        self.contract_service = contract_service
        self.weighted_average = 0.0

    def calculate_weighted_performances_average(self):
        """
        PERFORMS THE CALCULUS "C" FROM THE ISSUE KTD-1156
        """
        total_weight = 0.0
        total = 0.0
        for cip_scope in self.contract_items_performance_scope:
            total += (
                cip_scope.average_grade_percent
                * cip_scope.contract_item_performance.weight
                / 100
            )

            total_weight += cip_scope.contract_item_performance.weight / 100
        try:
            self.weighted_average = total / total_weight
        except Exception:
            self.weighted_average = 0.0
        return self.weighted_average


class MeasurementBulletinScope:
    def __init__(
        self,
        contract,
        aditional_field_surveys=False,
        measurement_bulletin=False,
        item_list=defaultdict(list),
        is_from_preview=False,
    ):
        self.contract_services_scope = []
        self.average_grade_percent = 0.0
        self.measurement_bulletin = measurement_bulletin
        self.additional_field_surveys = aditional_field_surveys
        self.contract = contract
        self.item_list = item_list
        self.is_from_preview = is_from_preview

    def perform_necessary_calculation(self):
        if self.additional_field_surveys and self.measurement_bulletin:
            field_surveys = self.measurement_bulletin.bulletin_surveys.all().union(
                self.additional_field_surveys
            )
        elif not self.additional_field_surveys and self.measurement_bulletin:
            field_surveys = self.measurement_bulletin.bulletin_surveys.all()

        elif self.additional_field_surveys and not self.measurement_bulletin:
            field_surveys = self.additional_field_surveys

        if self.item_list:
            if self.measurement_bulletin:
                contract_services = {
                    k: v
                    for k, (v, mb_control_list) in self.item_list.items()
                    if self.measurement_bulletin in mb_control_list
                    and k in self.contract.contract_services_bulletins.all()
                }
            else:
                contract_services = {
                    k: v
                    for k, (v, _) in self.item_list.items()
                    if k in self.contract.contract_services_bulletins.all()
                }

            for (
                contract_service,
                contract_items_performance,
            ) in contract_services.items():
                contract_items_performance_scope = []

                for contract_item_performance in contract_items_performance:
                    contract_item_performance_scope = ContractItemPerformanceScope(
                        contract_item_performance, field_surveys
                    )
                    contract_item_performance_scope.calculate_field_surveys_average()
                    contract_item_performance_scope.calculate_average_grade_percent(
                        self.contract.higher_grade
                    )
                    contract_items_performance_scope.append(
                        contract_item_performance_scope
                    )
                contract_service_scope = ContracServiceScope(
                    contract_items_performance_scope, contract_service
                )
                contract_service_scope.calculate_weighted_performances_average()
                self.contract_services_scope.append(contract_service_scope)
        else:
            if self.measurement_bulletin and not self.is_from_preview:
                contract_services_items = (
                    self.contract.contract_services_bulletins.filter(
                        measurement_bulletins=self.measurement_bulletin
                    )
                )
            else:
                contract_services_items = self.contract.performance_services.all()
            for contract_service in contract_services_items.prefetch_related(
                "contract_item_performance"
            ):
                contract_items_performance_scope = []
                contract_items_performance = (
                    contract_service.contract_item_performance.all()
                )

                for contract_item_performance in contract_items_performance:
                    contract_item_performance_scope = ContractItemPerformanceScope(
                        contract_item_performance,
                        field_surveys,
                        survey_has_bulletin=bool(
                            self.measurement_bulletin and not self.is_from_preview
                        ),
                    )
                    contract_item_performance_scope.calculate_field_surveys_average()
                    contract_item_performance_scope.calculate_average_grade_percent(
                        self.contract.higher_grade
                    )
                    contract_items_performance_scope.append(
                        contract_item_performance_scope
                    )
                contract_service_scope = ContracServiceScope(
                    contract_items_performance_scope, contract_service
                )
                contract_service_scope.calculate_weighted_performances_average()
                self.contract_services_scope.append(contract_service_scope)

    def calculate_mb_average_grade_percent(self):
        self.perform_necessary_calculation()
        total = 0.0
        total_weight = 0.0
        for contract_service_escope in self.contract_services_scope:
            total += (
                contract_service_escope.weighted_average
                * contract_service_escope.contract_service.weight
                / 100
            )
            total_weight += contract_service_escope.contract_service.weight / 100
        try:
            self.average_grade_percent = total
        except Exception:
            self.average_grade_percent = 0.0
        return self.average_grade_percent
