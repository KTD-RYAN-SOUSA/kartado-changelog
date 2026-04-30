import json

import pytest
from rest_framework import status

from apps.resources.models import Contract, FieldSurveyRoad
from apps.roads.models import Road
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestFieldSurveyRoad(TestBase):
    model = "FieldSurveyRoad"

    ATTRIBUTES = {"start_km": 10, "end_km": 11}

    def test_field_survey_road_list(self, client):
        """
        Ensures we can list using the FieldSurveyRoad endpoint
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

    def test_field_survey_road_without_company(self, client):
        """
        Ensures calling the FieldSurveyRoad endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_field_survey_road(self, client):
        """
        Ensures a specific FieldSurveyRoad can be fetched using the uuid
        """

        instance = FieldSurveyRoad.objects.first()
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

    def test_create_field_survey_road(self, client):
        """
        Ensures a new FieldSurveyRoad can be created using the endpoint
        """
        road = Road.objects.first()
        contract = Contract.objects.filter(subcompany__isnull=False)
        _ = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "FieldSurveyRoad",
                    "attributes": {"startKm": 22.0, "endKm": 23.0},
                    "relationships": {
                        "road": {"data": {"type": "Road", "id": str(road.pk)}},
                        "contract": {
                            "data": {
                                "type": "Contract",
                                "id": str(contract[0].pk),
                            }
                        },
                    },
                }
            },
        )

    def test_create_field_survey_road_without_company_id(self, client):
        """
        Ensures a new FieldSurveyRoad cannot be created
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

    def test_create_field_survey_road_without_permission(self, client):
        """
        Ensures a new FieldSurveyRoad cannot be created without
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

    def test_update_field_survey_road(self, client):
        """
        Ensure a FieldSurveyRoad can be updated using the endpoint
        """

        instance = FieldSurveyRoad.objects.first()

        # Change amount from 2 to 3 for the update
        self.ATTRIBUTES["end_km"] = 100

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

    def test_delete_field_survey_road(self, client):
        """
        Ensure a FieldSurveyRoad can be deleted using the endpoint
        """

        instance = FieldSurveyRoad.objects.first()

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
