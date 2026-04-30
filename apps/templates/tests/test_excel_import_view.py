from unittest.mock import patch

import pytest
from rest_framework import status

from apps.templates.models import ExcelImport
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestExcelImportViewGeneratePreview(TestBase):
    model = "ExcelImport"

    @patch("apps.templates.views.return_inventory_fields")
    @patch("apps.templates.views.parse_excel_to_json")
    def test_generate_preview_without_inventory_code(
        self, mock_parse_excel, mock_return_inventory_fields, client
    ):
        excel_import = ExcelImport.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/GeneratePreview/?company={}".format(
                self.model, str(excel_import.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"data": {"status": "OK"}}

        excel_import.refresh_from_db()
        assert excel_import.generating_preview is True

        mock_parse_excel.assert_called_once_with(
            str(excel_import.pk), str(self.user.pk), None
        )
        mock_return_inventory_fields.assert_not_called()

    @patch("apps.templates.views.Company.objects.get")
    @patch("apps.templates.views.return_inventory_fields")
    @patch("apps.templates.views.parse_excel_to_json")
    def test_generate_preview_with_valid_inventory_code(
        self, mock_parse_excel, mock_return_inventory_fields, mock_get_company, client
    ):
        excel_import = ExcelImport.objects.filter(company=self.company).first()
        mock_get_company.return_value = self.company
        mock_return_inventory_fields.return_value = [
            {"id": "code1"},
            {"id": "code2"},
        ]

        response = client.get(
            path="/{}/{}/GeneratePreview/?company={}&inventory_code=code1".format(
                self.model, str(excel_import.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"data": {"status": "OK"}}

        excel_import.refresh_from_db()
        assert excel_import.generating_preview is True

        mock_parse_excel.assert_called_once_with(
            str(excel_import.pk), str(self.user.pk), "code1"
        )
        mock_get_company.assert_called_once_with(pk=str(self.company.pk))
        mock_return_inventory_fields.assert_called_once_with(self.company)

    @patch("apps.templates.views.Company.objects.get")
    @patch("apps.templates.views.return_inventory_fields")
    def test_generate_preview_with_invalid_inventory_code(
        self, mock_return_inventory_fields, mock_get_company, client
    ):
        excel_import = ExcelImport.objects.filter(company=self.company).first()
        mock_get_company.return_value = self.company
        mock_return_inventory_fields.return_value = [
            {"id": "code1"},
            {"id": "code2"},
        ]

        response = client.get(
            path="/{}/{}/GeneratePreview/?company={}&inventory_code=invalid_code".format(
                self.model, str(excel_import.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestExcelImportViewExecute(TestBase):
    model = "ExcelImport"

    @patch("apps.templates.views.parse_json_to_objs")
    def test_execute_success(self, mock_parse_json, client):
        excel_import = ExcelImport.objects.filter(company=self.company).first()
        excel_import.error = False
        excel_import.save()

        response = client.get(
            path="/{}/{}/Execute/?company={}".format(
                self.model, str(excel_import.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"data": {"status": "OK"}}

        mock_parse_json.assert_called_once_with(str(excel_import.pk))

    def test_execute_with_error(self, client):
        excel_import = ExcelImport.objects.filter(company=self.company).first()
        excel_import.error = True
        excel_import.save()

        response = client.get(
            path="/{}/{}/Execute/?company={}".format(
                self.model, str(excel_import.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Excel contém erros." in str(response.data)
