import json

import pytest
from rest_framework import status

from apps.resources.models import ContractItemAdministration
from apps.service_orders.models import MeasurementBulletin
from helpers.testing.fixtures import TestBase, false_permission

from ..models import DailyReportVehicle

pytestmark = pytest.mark.django_db


class TestDailyReport(TestBase):
    model = "DailyReportVehicle"

    ATTRIBUTES = {
        "kind": "Interno",
        "description": "Kombi",
        "licensePlate": "CMF2206",
        "amount": 2,
    }

    def test_daily_report_vehicle_list(self, client):
        """
        Ensures we can list using the DailyReportVehicle endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 3

    def test_daily_report_vehicle_without_company(self, client):
        """
        Ensures calling the DailyReportVehicle endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_daily_report_vehicle(self, client):
        """
        Ensures a specific DailyReportVehicle can be fetched using the uuid
        """

        instance = DailyReportVehicle.objects.first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK

    def test_create_daily_report_vehicle(self, client):
        """
        Ensures a new DailyReportVehicle can be created using the endpoint
        """

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_daily_report_vehicle_without_company_id(self, client):
        """
        Ensures a new DailyReportVehicle cannot be created
        without a company id
        """

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_daily_report_vehicle_without_permission(self, client):
        """
        Ensures a new DailyReportVehicle cannot be created without
        the proper permissions
        """

        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_daily_report_vehicle(self, client):
        """
        Ensure a DailyReportVehicle can be updated using the endpoint
        """

        instance = DailyReportVehicle.objects.first()

        # Change amount from 2 to 3 for the update
        self.ATTRIBUTES["amount"] = 3

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(instance.pk),
                    "attributes": self.ATTRIBUTES,
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_should_update_field_when_measurement_bulletin_is_removed_from_vehicle(
        self, client
    ):
        vehicle_id = "955946ef-f488-4dd0-85a5-af23b733af8a"
        obj = DailyReportVehicle.objects.get(pk=vehicle_id)
        obj.contract_item_administration = ContractItemAdministration.objects.first()
        service_order_resource = obj.contract_item_administration.resource

        work_day = obj.measurement_bulletin.work_day
        expected_remaining_amount = (
            service_order_resource.remaining_amount + obj.amount / work_day
        )
        expected_used_price = service_order_resource.used_price - obj.total_price

        obj.measurement_bulletin = None
        obj.save()
        service_order_resource.refresh_from_db()

        assert service_order_resource.remaining_amount == expected_remaining_amount
        assert service_order_resource.used_price == expected_used_price

    def test_should_update_field_when_measurement_bulletin_is_added(self, client):
        vehicle_id = "1b08d44e-4bcd-490a-8bad-86d406bc12a2"
        mb_id = "0b02c96e-2632-42c4-afaa-0461b47c875b"
        obj = DailyReportVehicle.objects.get(pk=vehicle_id)
        obj.measurement_bulletin = MeasurementBulletin.objects.get(pk=mb_id)
        obj.contract_item_administration = ContractItemAdministration.objects.first()
        service_order_resource = obj.contract_item_administration.resource

        work_day = obj.measurement_bulletin.work_day
        expected_remaining_amount = (
            service_order_resource.remaining_amount - obj.amount / work_day
        )
        expected_used_price = service_order_resource.used_price + obj.total_price

        obj.save()
        service_order_resource.refresh_from_db()

        assert service_order_resource.remaining_amount == expected_remaining_amount
        assert service_order_resource.used_price == expected_used_price

    def test_delete_daily_report_vehicle(self, client):
        """
        Ensure a DailyReportVehicle can be deleted using the endpoint
        """

        instance = DailyReportVehicle.objects.first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT
