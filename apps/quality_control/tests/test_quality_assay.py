import json

import pytest
from django.db.models.signals import pre_save
from rest_framework import status

from apps.occurrence_records.models import OccurrenceType
from helpers.testing.fixtures import TestBase, false_permission

from ..models import QualityAssay, QualityProject
from ..signals import auto_add_quality_assay_number

pytestmark = pytest.mark.django_db


class TestQualityAssay(TestBase):
    model = "QualityAssay"

    ATTRIBUTES = {"formData": {"exampleData": 24}}

    def test_quality_assay_list(self, client):
        """
        Ensures we can list using the QualityAssay endpoint
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

    def test_quality_assay_without_company(self, client):
        """
        Ensures calling the QualityAssay endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_quality_assay(self, client):
        """
        Ensures a specific QualityAssay can be fetched using the uuid
        """

        instance = QualityAssay.objects.first()

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

    def test_create_quality_assay(self, client):
        """
        Ensures a new QualityAssay can be created using the endpoint
        """

        pre_save.disconnect(auto_add_quality_assay_number, sender=QualityAssay)

        occ_type_id = OccurrenceType.objects.first().uuid
        quality_project_id = QualityProject.objects.first().uuid

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
                        },
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occ_type_id),
                            }
                        },
                        "qualityProject": {
                            "data": {
                                "type": "QualityProject",
                                "id": str(quality_project_id),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_quality_assay_without_company_id(self, client):
        """
        Ensures a new QualityAssay cannot be created
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

    def test_create_quality_assay_without_permission(self, client):
        """
        Ensures a new QualityAssay cannot be created without
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

    def test_update_quality_assay(self, client):
        """
        Ensure a QualityAssay can be updated using the endpoint
        """

        instance = QualityAssay.objects.first()

        self.ATTRIBUTES["formData"] = {"newFormData": 22}

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

    def test_delete_quality_assay(self, client):
        """
        Ensure a QualityAssay can be deleted using the endpoint
        """

        instance = QualityAssay.objects.first()

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
