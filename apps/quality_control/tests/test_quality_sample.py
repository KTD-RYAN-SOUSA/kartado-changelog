import json

import pytest
from django.db.models.signals import pre_save
from rest_framework import status

from apps.companies.models import Firm
from apps.occurrence_records.models import OccurrenceType
from helpers.testing.fixtures import TestBase, false_permission

from ..models import QualityProject, QualitySample
from ..signals import auto_add_quality_sample_number

pytestmark = pytest.mark.django_db


class TestQualitySample(TestBase):
    model = "QualitySample"

    ATTRIBUTES = {"formData": {"test": "data"}}

    def test_quality_sample_list(self, client):
        """
        Ensures we can list using the QualitySample endpoint
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

    def test_quality_sample_without_company(self, client):
        """
        Ensures calling the QualitySample endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_quality_sample(self, client):
        """
        Ensures a specific QualitySample can be fetched using the uuid
        """

        instance = QualitySample.objects.first()

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

    def test_create_quality_sample(self, client):
        """
        Ensures a new QualitySample can be created using the endpoint
        """

        pre_save.disconnect(auto_add_quality_sample_number, sender=QualitySample)

        occ_type_id = OccurrenceType.objects.first().uuid
        quality_project_id = QualityProject.objects.first().uuid
        construction_firm_id = Firm.objects.first().uuid

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
                        "constructionFirm": {
                            "data": {
                                "type": "Firm",
                                "id": str(construction_firm_id),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_quality_sample_without_company_id(self, client):
        """
        Ensures a new QualitySample cannot be created
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

    def test_create_quality_sample_without_permission(self, client):
        """
        Ensures a new QualitySample cannot be created without
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

    def test_update_quality_sample(self, client):
        """
        Ensure a QualitySample can be updated using the endpoint
        """

        instance = QualitySample.objects.first()

        self.ATTRIBUTES["formData"] = {"new": "data"}

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

    def test_delete_quality_sample(self, client):
        """
        Ensure a QualitySample can be deleted using the endpoint
        """

        instance = QualitySample.objects.first()

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

    def test_get_company_id_property(self):
        quality_sample = QualitySample.objects.first()

        assert quality_sample.get_company_id == quality_sample.company_id
        assert quality_sample.get_company_id == quality_sample.company.pk
