import json

import pytest
from rest_framework import status

from apps.resources.models import Contract, ContractPeriod
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestContractPeriod(TestBase):
    model = "ContractPeriod"

    def test_list_contract_period(self, client):
        """Test listing ContractPeriods with company filter"""

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)

        assert content["meta"]["pagination"]["count"] == 2

    def test_list_contract_period_without_company_filter(self, client):
        """Test listing ContractPeriods without company filter should return 403"""

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_contract_period(self, client):
        """Test retrieving a specific ContractPeriod"""

        obj = ContractPeriod.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)
        attrs = content["data"]["attributes"]

        assert "totalHours" in attrs
        assert "periodCount" in attrs
        assert "editable" in attrs

    def test_create_contract_period(self, client):
        """Test creating a ContractPeriod"""

        contract = Contract.objects.get(uuid="1cede63e-8dd7-45b0-a11a-c45e89c87874")
        firm_uuid = "63656635-2476-44fa-bb42-c710c6b6620e"

        working_schedules = [
            {
                "start_time": "08:00",
                "end_time": "12:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "morning",
            },
            {
                "start_time": "13:00",
                "end_time": "17:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "afternoon",
            },
        ]

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "hours": 8.0,
                        "workingSchedules": working_schedules,
                    },
                    "relationships": {
                        "contract": {
                            "data": {"type": "Contract", "id": str(contract.pk)}
                        },
                        "company": {
                            "data": {"type": "Company", "id": str(self.company.pk)}
                        },
                        "firms": {"data": [{"type": "Firm", "id": firm_uuid}]},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        content = json.loads(response.content)
        obj_created = ContractPeriod.objects.get(pk=content["data"]["id"])
        assert obj_created.hours == 8.0
        assert obj_created.created_by == self.user
        assert obj_created.company == self.company
        assert len(obj_created.working_schedules) == 2

    def test_update_contract_period(self, client):
        """Test updating a ContractPeriod"""

        obj = ContractPeriod.objects.filter(company=self.company).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"hours": 10.0},
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

        obj.refresh_from_db()
        assert obj.hours == 10.0

    def test_delete_contract_period(self, client):
        """Test deleting a ContractPeriod"""

        obj = ContractPeriod.objects.filter(company=self.company).first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_period_count_total_hours_calculation(self, client):
        """Test that period_count and total_hours is calculated correctly from working_schedules"""

        obj = ContractPeriod.objects.get(pk="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)
        attrs = content["data"]["attributes"]

        # 08:00-12:00 = 4h + 13:00-17:00 = 4h = 8h total
        assert attrs["totalHours"] == 8.0
        # 2 schedules
        assert attrs["periodCount"] == 2

    def test_list_contract_period_with_filters(self, client):
        """Test listing ContractPeriods with contract filter"""

        contract_uuid = "1cede63e-8dd7-45b0-a11a-c45e89c87874"

        response = client.get(
            path="/{}/?company={}&contract={}".format(
                self.model, str(self.company.pk), contract_uuid
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)

        assert content["meta"]["pagination"]["count"] == 2
