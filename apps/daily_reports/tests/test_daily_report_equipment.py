import json

import pytest
from rest_framework import status

from apps.resources.models import ContractItemAdministration
from apps.service_orders.models import MeasurementBulletin
from helpers.testing.fixtures import TestBase, false_permission

from ..models import DailyReportEquipment

pytestmark = pytest.mark.django_db


class TestDailyReport(TestBase):
    model = "DailyReportEquipment"

    ATTRIBUTES = {"kind": "Interno", "description": "Soprador", "amount": 2}

    def test_daily_report_equipment_list(self, client):
        """
        Ensures we can list using the DailyReportEquipment endpoint
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
        assert content["meta"]["pagination"]["count"] == 2

    def test_daily_report_equipment_without_company(self, client):
        """
        Ensures calling the DailyReportEquipment endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_daily_report_equipment(self, client):
        """
        Ensures a specific DailyReportEquipment can be fetched using the uuid
        """

        equipment = DailyReportEquipment.objects.first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(equipment.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK

    def test_create_daily_report_equipment(self, client):
        """
        Ensures a new DailyReportEquipment can be created using the endpoint
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

    def test_create_daily_report_equipment_without_company_id(self, client):
        """
        Ensures a new DailyReportEquipment cannot be created
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

    def test_create_daily_report_equipment_without_permission(self, client):
        """
        Ensures a new DailyReportEquipment cannot be created without
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

    def test_update_daily_report_equipment(self, client):
        """
        Ensure a DailyReportEquipment can be updated using the endpoint
        """

        equipment = DailyReportEquipment.objects.first()

        # Change amount from 2 to 3 for the update
        self.ATTRIBUTES["amount"] = 3

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(equipment.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(equipment.pk),
                    "attributes": self.ATTRIBUTES,
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_should_update_field_when_measurement_bulletin_is_removed_from_equipment(
        self, client
    ):
        obj = DailyReportEquipment.objects.first()
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
        equip_id = "795b821b-3f0f-466b-a2fa-e0d70823ce72"
        mb_id = "0b02c96e-2632-42c4-afaa-0461b47c875b"
        obj = DailyReportEquipment.objects.get(pk=equip_id)
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

    def test_delete_daily_report_equipment(self, client):
        """
        Ensure a DailyReportEquipment can be deleted using the endpoint
        """

        equipment = DailyReportEquipment.objects.first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(equipment.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT
