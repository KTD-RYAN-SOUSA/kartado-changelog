import json

import pytest
from rest_framework import status

from apps.occurrence_records.models import OccurrenceType
from helpers.testing.fixtures import TestBase, false_permission

from ..models import CSVImport

pytestmark = pytest.mark.django_db


class TestDailyReport(TestBase):
    model = "CSVImport"

    ATTRIBUTES = {"name": "CSVImport testing"}

    def test_csv_import_list(self, client):
        """
        Ensures we can list using the CSVImport endpoint
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

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] == 1

    def test_csv_import_without_company(self, client):
        """
        Ensures calling the CSVImport endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_csv_import(self, client):
        """
        Ensures a specific CSVImport can be fetched using the uuid
        """

        instance = CSVImport.objects.first()

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

    def test_create_csv_import(self, client):
        """
        Ensures a new CSVImport can be created using the endpoint
        """

        occ_type = OccurrenceType.objects.first()
        occ_type_id = str(occ_type.uuid)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "occurrence_type": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": occ_type_id,
                            }
                        },
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

    def test_create_csv_import_without_company_id(self, client):
        """
        Ensures a new CSVImport cannot be created
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

    def test_create_csv_import_without_permission(self, client):
        """
        Ensures a new CSVImport cannot be created without
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

    def test_update_csv_import(self, client):
        """
        Ensure a CSVImport can be updated using the endpoint
        """

        instance = CSVImport.objects.first()

        # Change lane from 15 to 11 for the update
        self.ATTRIBUTES["lane"] = "11"

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

    def test_delete_csv_import(self, client):
        """
        Ensure a CSVImport can be deleted using the endpoint
        """

        instance = CSVImport.objects.first()

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
