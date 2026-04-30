import json

import pytest
from rest_framework import status

from apps.companies.models import Firm
from apps.occurrence_records.models import OccurrenceType
from apps.service_orders.models import ServiceOrderActionStatus
from helpers.testing.fixtures import TestBase, false_permission

from ..models import PDFImport

pytestmark = pytest.mark.django_db


class TestDailyReport(TestBase):
    model = "PDFImport"

    ATTRIBUTES = {"name": "PDFImport testing", "lane": "15"}

    def test_pdf_import_list(self, client):
        """
        Ensures we can list using the PDFImport endpoint
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

    def test_pdf_import_without_company(self, client):
        """
        Ensures calling the PDFImport endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_pdf_import(self, client):
        """
        Ensures a specific PDFImport can be fetched using the uuid
        """

        instance = PDFImport.objects.first()

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

    def test_create_pdf_import(self, client):
        """
        Ensures a new PDFImport can be created using the endpoint
        """

        firm = Firm.objects.first()
        firm_id = str(firm.uuid)

        action_status = ServiceOrderActionStatus.objects.first()
        action_status_id = str(action_status.uuid)

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
                        "firm": {"data": {"type": "Firm", "id": firm_id}},
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": action_status_id,
                            }
                        },
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

    def test_create_pdf_import_without_company_id(self, client):
        """
        Ensures a new PDFImport cannot be created
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

    def test_create_pdf_import_without_permission(self, client):
        """
        Ensures a new PDFImport cannot be created without
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

    def test_update_pdf_import(self, client):
        """
        Ensure a PDFImport can be updated using the endpoint
        """

        instance = PDFImport.objects.first()

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

    def test_delete_pdf_import(self, client):
        """
        Ensure a PDFImport can be deleted using the endpoint
        """

        instance = PDFImport.objects.first()

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
