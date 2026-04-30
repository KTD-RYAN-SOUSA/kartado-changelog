import json

import pytest
from rest_framework import status

from apps.reportings.models import Reporting
from apps.templates.models import ExcelImport, ExcelReporting
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestExcelReporting(TestBase):
    model = "ExcelReporting"

    def test_list_excel_reporting(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_excel_reporting_without_queryset(self, client):

        false_permission(self.user, self.company, self.model, allowed="none")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        false_permission(self.user, self.company, self.model, allowed="self")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_excel_reporting_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_excel_reporting(self, client):

        excel_reporting = ExcelReporting.objects.filter(
            excel_import__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(excel_reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_excel_reporting(self, client):

        excel_import = ExcelImport.objects.filter(company=self.company).first()
        reporting = Reporting.objects.filter(company=self.company).first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"row": "2", "operation": "CREATE"},
                    "relationships": {
                        "excelImport": {
                            "data": {
                                "type": "ExcelImport",
                                "id": str(excel_import.pk),
                            }
                        },
                        "reporting": {
                            "data": {
                                "type": "Reporting",
                                "id": str(reporting.pk),
                            }
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = ExcelReporting.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_excel_reporting_without_permission(self, client):

        excel_import = ExcelImport.objects.filter(company=self.company).first()
        reporting = Reporting.objects.filter(company=self.company).first()

        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"row": "2", "operation": "CREATE"},
                    "relationships": {
                        "excelImport": {
                            "data": {
                                "type": "ExcelImport",
                                "id": str(excel_import.pk),
                            }
                        },
                        "reporting": {
                            "data": {
                                "type": "Reporting",
                                "id": str(reporting.pk),
                            }
                        },
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_excel_reporting(self, client):

        excel_reporting = ExcelReporting.objects.filter(
            excel_import__company=self.company
        ).first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(excel_reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(excel_reporting.pk),
                    "attributes": {"row": "3"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_excel_reporting(self, client):

        excel_reporting = ExcelReporting.objects.filter(
            excel_import__company=self.company
        ).first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(excel_reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT
