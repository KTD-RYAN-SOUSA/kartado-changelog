import json

import pytest
from rest_framework import status

from apps.daily_reports.models import DailyReportWorker
from apps.resources.models import ContractItemAdministration
from apps.service_orders.models import MeasurementBulletin
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestDailyReport(TestBase):
    model = "DailyReportWorker"

    ATTRIBUTES = {
        "members": "Garrosh, Thrall",
        "amount": 2,
        "role": "Warrior & Shaman",
    }

    def test_daily_report_worker_list(self, client):
        """
        Ensures we can list using the DailyReportWorker endpoint
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

    def test_daily_report_worker_without_company(self, client):
        """
        Ensures calling the DailyReportWorker endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_daily_report_worker(self, client):
        """
        Ensures a specific daily report worker can be fetched using the uuid
        """

        worker = DailyReportWorker.objects.first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(worker.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK

    def test_create_daily_report_worker(self, client):
        """
        Ensures a new daily report worker can be created using the endpoint
        """

        # Get same Firm as fixture
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_daily_report_worker_without_company_id(self, client):
        """
        Ensures a new daily report worker cannot be created
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

    def test_create_daily_report_worker_without_permission(self, client):
        """
        Ensures a new daily report worker cannot be created without
        the proper permissions
        """

        # Get same Firm as fixture
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}}
                    },
                }
            },
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_daily_report_worker(self, client):
        """
        Ensure a DailyReportWorker can be updated using the endpoint
        """

        worker = DailyReportWorker.objects.first()

        # Change amount from 2 to 3 for the update
        self.ATTRIBUTES["amount"] = 3

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(worker.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(worker.pk),
                    "attributes": self.ATTRIBUTES,
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_should_update_field_when_measurement_bulletin_is_removed_from_worker(
        self, client
    ):
        worker_id = "d0b36749-bd45-42c1-80d0-4a5f7820b16d"
        obj = DailyReportWorker.objects.get(pk=worker_id)
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
        worker_id = "e87d3bfc-ae17-400a-967d-cb1c3b2611f3"
        mb_id = "0b02c96e-2632-42c4-afaa-0461b47c875b"
        obj = DailyReportWorker.objects.get(pk=worker_id)
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

    def test_delete_daily_report_worker(self, client):
        """
        Ensure a DailyReportWorker can be deleted using the endpoint
        """

        worker = DailyReportWorker.objects.first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(worker.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_list_with_active_field(self, client):
        response = client.get(
            path="/{}/?company={}&multiple_daily_reports=0a2daca5-416e-4679-bb59-af8fe1801bba&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)

        assert "active" in content["data"][0]["attributes"]
