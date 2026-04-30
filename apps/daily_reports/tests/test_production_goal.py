import json

import pytest
from rest_framework import status

from apps.services.models import Service
from helpers.testing.fixtures import TestBase, false_permission

from ..models import ProductionGoal

pytestmark = pytest.mark.django_db


class TestDailyReport(TestBase):
    model = "ProductionGoal"

    ATTRIBUTES = {
        "startsAt": "2022-01-01",
        "endsAt": "2022-06-01",
        "daysOfWork": 25,
        "amount": 123.4,
    }

    def test_production_goal_list(self, client):
        """
        Ensures we can list using the ProductionGoal endpoint
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
        assert content["meta"]["pagination"]["count"] == 1

    def test_production_goal_without_company(self, client):
        """
        Ensures calling the ProductionGoal endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_production_goal(self, client):
        """
        Ensures a specific ProductionGoal can be fetched using the uuid
        """

        instance = ProductionGoal.objects.first()

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

    def test_create_production_goal(self, client):
        """
        Ensures a new ProductionGoal can be created using the endpoint
        """

        service = Service.objects.first()
        service_id = str(service.uuid)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "service": {"data": {"type": "Service", "id": service_id}}
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_production_goal_without_company_id(self, client):
        """
        Ensures a new ProductionGoal cannot be created
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

    def test_create_production_goal_without_permission(self, client):
        """
        Ensures a new ProductionGoal cannot be created without
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

    def test_update_production_goal(self, client):
        """
        Ensure a ProductionGoal can be updated using the endpoint
        """

        instance = ProductionGoal.objects.first()

        # Change days_of_work from 25 to 32 for the update
        self.ATTRIBUTES["days_of_work"] = 32

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

    def test_delete_production_goal(self, client):
        """
        Ensure a ProductionGoal can be deleted using the endpoint
        """

        instance = ProductionGoal.objects.first()

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

    def test_production_goal_dates(self, client):
        """
        Ensure a ProductionGoal starts_at date can't be after the ends_at date
        """

        service = Service.objects.first()
        service_id = str(service.uuid)

        # Backup old starts_at and ends_at values
        old_starts_at = self.ATTRIBUTES["startsAt"]
        old_ends_at = self.ATTRIBUTES["endsAt"]
        # Change starts_at and ends_at to offending dates
        self.ATTRIBUTES["startsAt"] = "2022-01-01"
        self.ATTRIBUTES["endsAt"] = "2021-01-01"

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "service": {"data": {"type": "Service", "id": service_id}}
                    },
                }
            },
        )

        content = json.loads(response.content)

        # Error creating object
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        expected_message = (
            "kartado.error.production_goal.ends_at_should_be_after_starts_at"
        )
        assert content["errors"][0]["detail"] == expected_message

        # Reset changed values
        self.ATTRIBUTES["startsAt"] = old_starts_at
        self.ATTRIBUTES["endsAt"] = old_ends_at
