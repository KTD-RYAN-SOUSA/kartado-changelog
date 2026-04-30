import json

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase

from ..models import ExcelDnitReport

pytestmark = pytest.mark.django_db


class TestExcelDnitReport(TestBase):
    model = "ExcelDnitReport"

    def test_list_excel_dnit_report(self, client):
        objects_count = ExcelDnitReport.objects.count()
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        # The call was successful and the object count in the request is equal to
        # the object count in the database

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == objects_count

    def test_retrieve_excel_dnit_report(self, client):
        instance = ExcelDnitReport.objects.filter(company=self.company).first()

        if not instance:
            # Create an instance if it doesn't exist
            instance = ExcelDnitReport.objects.create(
                company=self.company,
                created_by=self.user,
                extra_info={},
                filters={},
            )

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

    def test_create_excel_dnit_report(self, client):
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "filters": {"a": "b", "c": "d"},
                        "extraInfo": {"1": 2},
                        "done": False,
                        "error": False,
                    },
                    "relationships": {
                        "company": {
                            "data": {"type": "Company", "id": str(self.company.pk)}
                        }
                    },
                },
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_filter_done_excel_dnit_report(self, client):
        response = client.get(
            path="/{}/?company={}&done={}&page_size=1".format(
                self.model, str(self.company.pk), False
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] >= 0

    def test_filter_error_excel_dnit_report(self, client):
        response = client.get(
            path="/{}/?company={}&error={}&page_size=1".format(
                self.model, str(self.company.pk), False
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] >= 0

    def test_filter_created_at_excel_dnit_report(self, client):
        response = client.get(
            path="/{}/?company={}&created_at_after={}&page_size=1".format(
                self.model, str(self.company.pk), "2024-06-20"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] >= 0

    def test_get_company_id(self, client):
        instance = ExcelDnitReport.objects.filter(company=self.company).first()

        if not instance:
            # Create an instance if it doesn't exist
            instance = ExcelDnitReport.objects.create(
                company=self.company,
                created_by=self.user,
                extra_info={},
                filters={},
            )

        assert instance.get_company_id == instance.company_id
        assert instance.get_company_id == self.company.pk

    def test_str_method(self, client):
        instance = ExcelDnitReport.objects.filter(company=self.company).first()

        if not instance:
            # Create an instance if it doesn't exist
            instance = ExcelDnitReport.objects.create(
                company=self.company,
                created_by=self.user,
                extra_info={},
                filters={},
            )

        expected_str = "[{}] {}: ExcelDnitReport".format(
            instance.company.name, instance.uuid
        )
        assert str(instance) == expected_str
