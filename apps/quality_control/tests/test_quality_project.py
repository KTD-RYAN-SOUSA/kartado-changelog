import json

import pytest
from rest_framework import status

from apps.occurrence_records.models import OccurrenceType
from helpers.testing.fixtures import TestBase, false_permission

from ..models import QualityProject

pytestmark = pytest.mark.django_db


class TestQualityProject(TestBase):
    model = "QualityProject"

    ATTRIBUTES = {
        "projectNumber": "ABC123",
        "expiresAt": "2021-07-06",
        "registeredAt": "2021-07-05",
    }

    def test_quality_project_list(self, client):
        """
        Ensures we can list using the QualityProject endpoint
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

    def test_quality_project_without_company(self, client):
        """
        Ensures calling the QualityProject endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_quality_project(self, client):
        """
        Ensures a specific QualityProject can be fetched using the uuid
        """

        instance = QualityProject.objects.first()

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

    def test_create_quality_project(self, client):
        """
        Ensures a new QualityProject can be created using the endpoint
        """

        occ_type_id = OccurrenceType.objects.first().uuid

        # Get same Firm as fixture
        firm = QualityProject.objects.first().firm
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
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occ_type_id),
                            }
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_quality_project_without_company_id(self, client):
        """
        Ensures a new QualityProject cannot be created
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

    def test_create_quality_project_without_permission(self, client):
        """
        Ensures a new QualityProject cannot be created without
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

    def test_update_quality_project(self, client):
        """
        Ensure a QualityProject can be updated using the endpoint
        """

        instance = QualityProject.objects.first()

        # Change amount from 2 to 3 for the update
        self.ATTRIBUTES["projectNumber"] = "123ACB"

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

    def test_delete_quality_project(self, client):
        """
        Ensure a QualityProject can be deleted using the endpoint
        """

        instance = QualityProject.objects.first()

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
