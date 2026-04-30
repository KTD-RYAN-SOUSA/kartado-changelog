import uuid

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework_json_api import serializers

from apps.resources.models import FieldSurvey
from apps.service_orders.models import MeasurementBulletin
from helpers.apps.performance_calculations import MeasurementBulletinScope


class MeasurementBulletinPreview:
    def __init__(self, request):
        self.request = request
        self.contract = None
        self.field_surveys = []
        self.measurement_bulletin_obj = False
        self.provisioned_price = 0.0
        self.average_grade_percent = 0.0
        self.performance_total_price = 0.0
        self.response_data = {}
        self.main()

    def main(self):
        self.set_field_surveys()
        self.set_measurement_bulletin()
        self.set_contract()
        self.set_privisioned_price()
        self.set_average_grade_percent()
        self.set_performance_total_price()
        self.set_response_data()

    def validate_uuid(self, id):
        try:
            return uuid.UUID(id)
        except Exception:
            raise serializers.ValidationError("Invalid field survey id.")

    def set_field_surveys(self):
        if "field_survey" not in self.request.query_params:
            raise serializers.ValidationError()
        field_surveys_ids = self.request.query_params["field_survey"].split(",")
        # verify if uuid is valid to avoid 500 server error
        ids = [self.validate_uuid(id) for id in field_surveys_ids]
        if ids:
            field_surveys = FieldSurvey.objects.filter(uuid__in=ids).distinct()
            if not field_surveys:
                raise serializers.ValidationError()
        self.field_surveys = field_surveys

    def set_measurement_bulletin(self):
        if "measurement_bulletin" in self.request.query_params:
            mb_id = self.request.query_params["measurement_bulletin"]
            self.measurement_bulletin_obj = get_object_or_404(
                MeasurementBulletin, pk=mb_id
            )
            self.field_surveys = self.field_surveys.exclude(
                measurement_bulletin_id=self.measurement_bulletin_obj.pk
            )

    def set_contract(self):
        if self.measurement_bulletin_obj:
            self.contract = self.measurement_bulletin_obj.contract
        else:
            self.contract = self.field_surveys[0].contract

    def set_privisioned_price(self):
        self.provisioned_price = (
            self.contract.performance_services.aggregate(Sum("price")).get("price__sum")
            / self.contract.performance_months
        )

    def set_average_grade_percent(self):
        measurement_bulletin_scope = MeasurementBulletinScope(
            self.contract,
            self.field_surveys,
            self.measurement_bulletin_obj,
            is_from_preview=True,
        )
        self.average_grade_percent = (
            measurement_bulletin_scope.calculate_mb_average_grade_percent()
        )

    def set_performance_total_price(self):
        for contract_service in self.contract.performance_services.all():
            try:
                self.performance_total_price += (
                    contract_service.price / self.contract.performance_months
                ) * self.average_grade_percent
            except Exception:
                pass

    def set_response_data(self):
        self.response_data = {
            "provisionedPrice": self.provisioned_price,
            "averageGradePercent": self.average_grade_percent,
            "totalPrice": self.performance_total_price,
        }

    def get_response(self):
        return Response(data=self.response_data, status=status.HTTP_200_OK)
