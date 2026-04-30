import json
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from apps.templates.models import ExcelImport
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestExcelImport(TestBase):
    model = "ExcelImport"

    @pytest.fixture(autouse=True)
    def set_up_excel_import(self):
        # super().setUp()
        # Create test ExcelImport
        self.excel_import = ExcelImport.objects.create(
            company=self.company,
            created_by=self.user,
            excel_file=SimpleUploadedFile(
                "test.xlsx",
                b"test content",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        )
        return self.excel_import

    def test_list_excel_import(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_excel_import_without_queryset(self, client):

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

    def test_list_excel_import_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_excel_import(self, client):

        excel_import = ExcelImport.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(excel_import.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_excel_import(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test_excel_import"},
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = ExcelImport.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_excel_import_without_company_id(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test_excel_import"},
                    "relationships": {"company": {"data": {"type": "Company"}}},
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_excel_import_without_permission(self, client):

        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test_excel_import"},
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_excel_import(self, client):

        excel_import = ExcelImport.objects.filter(company=self.company).first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(excel_import.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(excel_import.pk),
                    "attributes": {"name": "test_update"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_excel_import(self, client):

        excel_import = ExcelImport.objects.filter(company=self.company).first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(excel_import.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_get_company_id(self, client):
        excel_import = ExcelImport.objects.filter(company=self.company).first()

        assert excel_import.get_company_id == excel_import.company_id
        assert excel_import.get_company_id == self.company.pk

    @patch("apps.templates.views.parse_excel_to_json")
    def test_generate_preview_success(self, mock_parse, client):
        """Test successful preview generation with inventory code"""
        # Setup custom options for company

        response = client.get(
            path=f"/{self.model}/{self.excel_import.pk}/GeneratePreview/?company={self.company.pk}&inventory_code=number",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == status.HTTP_200_OK

        # Verify ExcelImport state
        self.excel_import.refresh_from_db()
        assert self.excel_import.generating_preview is True

        # Verify parse_excel_to_json called correctly
        mock_parse.assert_called_once_with(
            str(self.excel_import.pk), str(self.user.pk), "number"
        )

    def test_generate_preview_invalid_inventory_code(self, client):
        """Test preview generation with invalid inventory code"""
        response = client.get(
            path=f"/{self.model}/{self.excel_import.pk}/GeneratePreview/?company={self.company.pk}&inventory_code=invalid_code",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            "kartado.error.excel_import.generate_preview.invalid_inventory_code"
            in str(response.content)
        )

    @patch("apps.templates.views.parse_json_to_objs")
    def test_execute_success(self, mock_parse, client):
        """Test successful excel import execution"""
        # Setup ExcelImport without errors
        self.excel_import.error = False
        self.excel_import.save()

        response = client.get(
            path=f"/{self.model}/{self.excel_import.pk}/Execute/?company={self.company.pk}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == status.HTTP_200_OK

        # Verify parse_json_to_objs called correctly
        mock_parse.assert_called_once_with(str(self.excel_import.pk))

    def test_execute_with_errors(self, client):
        """Test excel import execution with errors"""
        # Setup ExcelImport with errors
        self.excel_import.error = True
        self.excel_import.save()

        response = client.get(
            path=f"/{self.model}/{self.excel_import.pk}/Execute/?company={self.company.pk}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_generate_preview_without_inventory_code(self, client):
        """Test preview generation without inventory code"""
        response = client.get(
            path=f"/{self.model}/{self.excel_import.pk}/GeneratePreview/?company={self.company.pk}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == status.HTTP_200_OK
