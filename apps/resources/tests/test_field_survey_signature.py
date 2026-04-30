import json

import pytest
from rest_framework import status

from apps.resources.models import FieldSurveySignature
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestFieldSurveySignature(TestBase):
    model = "FieldSurveySignature"

    ATTRIBUTES = {}

    def test_field_survey_signature_list(self, client):
        """
        Ensures we can list using the FieldSurveySignature endpoint
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
        assert content["meta"]["pagination"]["count"] == 9

    def test_field_survey_signature_without_company(self, client):
        """
        Ensures calling the FieldSurveySignature endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_field_survey_signature(self, client):
        """
        Ensures a specific FieldSurveySignature can be fetched using the uuid
        """

        instance = FieldSurveySignature.objects.first()

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

    def test_update_field_survey_signature(self, client):
        """
        Ensure a FieldSurveySignature can be updated using the endpoint
        """

        instance = FieldSurveySignature.objects.filter(hirer=self.user).first()

        # Change amount from 2 to 3 for the update
        self.ATTRIBUTES["signed_at"] = "2022-05-10T12:49:03.562715-03:00"

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
