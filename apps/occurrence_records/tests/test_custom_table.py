import json
from datetime import date
from unittest.mock import patch

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase

from ..const import custom_table
from ..models import CustomTable, TableDataSeries

pytestmark = pytest.mark.django_db


class TestCustomTable(TestBase):
    model = "CustomTable"

    def test_list_custom_tables(self, client):
        """Test listing custom tables with company filter"""
        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_200_OK

    def test_create_custom_table(self, client):
        data = {
            "data": {
                "type": self.model,
                "attributes": {
                    "name": "Test Custom Table",
                    "description": "Test Description",
                    "start_period": str(date.today()),
                    "end_period": str(date.today()),
                    "table_type": custom_table.ANALYSIS,
                    "columns_break": custom_table.DAY,
                    "line_frequency": "DAILY",
                    "hidro_basins": [],
                    "additional_columns": [],
                    "additional_lines": [],
                    "table_descriptions": {},
                },
                "relationships": {
                    "company": {
                        "data": {"type": "Company", "id": str(self.company.pk)}
                    },
                    "can_be_edited_by": {
                        "data": [{"type": "User", "id": str(self.user.pk)}]
                    },
                },
            }
        }

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=json.dumps(data),
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_update_custom_table(self, client):
        custom_table_obj = CustomTable.objects.create(
            company=self.company,
            name="Test Table",
            description="Test Description",
            created_by=self.user,
            _start_period=date.today(),
            _end_period=date.today(),
            table_type=custom_table.ANALYSIS,
            columns_break=custom_table.DAY,
        )
        custom_table_obj.can_be_edited_by.add(self.user)

        data = {
            "data": {
                "type": self.model,
                "id": str(custom_table_obj.pk),
                "attributes": {
                    "name": "Updated Table Name",
                },
            }
        }

        response = client.patch(
            path="/{}/{}/".format(self.model, str(custom_table_obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=json.dumps(data),
        )
        assert response.status_code == status.HTTP_200_OK

    def test_delete_custom_table(self, client):
        custom_table_obj = CustomTable.objects.create(
            company=self.company,
            name="Test Table",
            description="Test Description",
            created_by=self.user,
            _start_period=date.today(),
            _end_period=date.today(),
            table_type=custom_table.ANALYSIS,
            columns_break=custom_table.DAY,
        )
        custom_table_obj.can_be_edited_by.add(self.user)

        response = client.delete(
            path="/{}/{}/".format(self.model, str(custom_table_obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_get_preview_missing_company(self, client):
        preview_params = {
            "line_frequency": "DAILY",
            "start_period": str(date.today()),
            "end_period": str(date.today()),
            "table_data_series": "[]",
            "table_type": "ANALYSIS",
            "dynamic_period_in_days": "null",
        }

        response = client.get(
            path="/{}/Preview/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=preview_params,
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_preview_missing_required_args(self, client):
        """Test preview endpoint with missing required arguments"""
        preview_params = {"company": str(self.company.pk), "table_type": "ANALYSIS"}

        response = client.get(
            path="/{}/Preview/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=preview_params,
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_preview_invalid_company(self, client):
        """Test preview endpoint with invalid company UUID"""
        preview_params = {
            "company": "invalid-uuid",
            "line_frequency": "DAILY",
            "start_period": str(date.today()),
            "end_period": str(date.today()),
            "table_data_series": "[]",
            "table_type": "ANALYSIS",
            "columns_break": "DAY",
            "dynamic_period_in_days": "null",
        }

        response = client.get(
            path="/{}/Preview/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=preview_params,
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_preview_invalid_line_frequency(self, client):
        """Test preview endpoint with invalid line frequency"""
        preview_params = {
            "company": str(self.company.pk),
            "line_frequency": "INVALID",
            "start_period": str(date.today()),
            "end_period": str(date.today()),
            "table_data_series": "[]",
            "table_type": "ANALYSIS",
            "columns_break": "DAY",
            "dynamic_period_in_days": "null",
        }

        response = client.get(
            path="/{}/Preview/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=preview_params,
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_preview_invalid_table_type(self, client):
        """Test preview endpoint with invalid table type"""
        preview_params = {
            "company": str(self.company.pk),
            "line_frequency": "DAILY",
            "start_period": str(date.today()),
            "end_period": str(date.today()),
            "table_data_series": "[]",
            "table_type": "INVALID",
            "columns_break": "DAY",
            "dynamic_period_in_days": "null",
        }

        response = client.get(
            path="/{}/Preview/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=preview_params,
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("helpers.sih_table.SihTable.get_row_datetimes")
    @patch("helpers.sih_table.fetch_sih_data")
    @patch("helpers.sih_table.SihTable.get_table_description")
    def test_get_preview_comparison_type(
        self,
        mock_get_table_description,
        mock_fetch_sih_data,
        mock_get_row_datetimes,
        client,
    ):
        """Test preview endpoint with comparison table type"""
        mock_fetch_sih_data.return_value = []
        mock_get_table_description.return_value = [{"data": "test"}]
        mock_get_row_datetimes.return_value = []

        table_data_series = TableDataSeries.objects.create(
            company=self.company,
            name="Test Series",
            created_by=self.user,
            sih_frequency="HOURLY",
        )

        preview_params = {
            "company": str(self.company.pk),
            "line_frequency": "HOURLY",
            "start_period": str(date.today()),
            "end_period": str(date.today()),
            "table_data_series": str(table_data_series.uuid),
            "table_type": "COMPARISON",
            "dynamic_period_in_days": "null",
        }

        response = client.get(
            path="/{}/Preview/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=preview_params,
        )
        assert response.status_code == status.HTTP_200_OK

    @patch("helpers.sih_table.SihTable.get_row_datetimes")
    @patch("helpers.sih_table.fetch_sih_data")
    @patch("helpers.sih_table.SihTable.get_table_description")
    def test_get_preview_success(
        self,
        mock_get_table_description,
        mock_fetch_sih_data,
        mock_get_row_datetimes,
        client,
    ):
        """Test successful preview generation"""
        mock_fetch_sih_data.return_value = []
        mock_get_table_description.return_value = [{"data": "test"}]
        mock_get_row_datetimes.return_value = []

        table_data_series = TableDataSeries.objects.create(
            company=self.company,
            name="Test Series",
            created_by=self.user,
            sih_frequency="DAILY",
        )

        preview_params = {
            "company": str(self.company.pk),
            "line_frequency": "HOURLY",
            "start_period": str(date.today()),
            "end_period": str(date.today()),
            "table_data_series": str(table_data_series.uuid),
            "table_type": "ANALYSIS",
            "columns_break": "DAY",
            "dynamic_period_in_days": "null",
        }

        response = client.get(
            path="/{}/Preview/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=preview_params,
        )

        assert response.status_code == status.HTTP_200_OK
        response_data = response.json()
        assert "data" in response_data
        assert isinstance(response_data["data"], list)
        assert len(response_data["data"]) > 0
        assert "data" in response_data["data"][0]
        assert response_data["data"][0]["data"] == "test"

    def test_get_excel_unauthorized(self, client):
        """Test excel generation without authorization"""
        test_table = CustomTable.objects.create(
            company=self.company,
            name="Test Table",
            description="Test Description",
            created_by=self.user,
            _start_period=date.today(),
            _end_period=date.today(),
            table_type=custom_table.ANALYSIS,
            columns_break=custom_table.DAY,
            line_frequency="HOURLY",
        )

        response = client.get(
            path="/{}/{}/Excel/".format(self.model, str(test_table.pk)),
            content_type="application/vnd.api+json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("helpers.sih_table.SihTable.get_excel")
    def test_get_excel_success(self, mock_get_excel, client):
        """Test successful excel generation"""
        mock_excel_url = "https://example.com/excel.xlsx"
        mock_get_excel.return_value = mock_excel_url

        test_table = CustomTable.objects.create(
            company=self.company,
            name="Test Table",
            description="Test Description",
            created_by=self.user,
            _start_period=date.today(),
            _end_period=date.today(),
            table_type=custom_table.ANALYSIS,
            columns_break=custom_table.DAY,
            line_frequency="HOURLY",
        )
        test_table.can_be_viewed_by.add(self.user)

        response = client.get(
            path="/{}/{}/Excel/".format(self.model, str(test_table.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"data": {"excel_url": mock_excel_url}}

    def test_create_custom_table_with_dynamic_period(self, client):
        """Test creating custom table with dynamic period"""
        data = {
            "data": {
                "type": self.model,
                "attributes": {
                    "name": "Test Dynamic Table",
                    "description": "Test Description with dynamic period",
                    "dynamic_period_in_days": 30,
                    "table_type": custom_table.ANALYSIS,
                    "columns_break": custom_table.DAY,
                    "line_frequency": "DAILY",
                    "hidro_basins": [],
                    "additional_columns": [],
                    "additional_lines": [],
                    "table_descriptions": {},
                },
                "relationships": {
                    "company": {
                        "data": {"type": "Company", "id": str(self.company.pk)}
                    },
                    "can_be_edited_by": {
                        "data": [{"type": "User", "id": str(self.user.pk)}]
                    },
                },
            }
        }

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=json.dumps(data),
        )
        assert response.status_code == status.HTTP_201_CREATED

    @patch("helpers.sih_table.SihTable.get_row_datetimes")
    @patch("helpers.sih_table.fetch_sih_data")
    @patch("helpers.sih_table.SihTable.get_table_description")
    def test_get_preview_with_dynamic_period(
        self,
        mock_get_table_description,
        mock_fetch_sih_data,
        mock_get_row_datetimes,
        client,
    ):
        """Test preview endpoint with dynamic period"""
        mock_fetch_sih_data.return_value = []
        mock_get_table_description.return_value = [{"data": "test"}]
        mock_get_row_datetimes.return_value = []

        table_data_series = TableDataSeries.objects.create(
            company=self.company,
            name="Test Series",
            created_by=self.user,
            sih_frequency="DAILY",
        )

        preview_params = {
            "company": str(self.company.pk),
            "line_frequency": "HOURLY",
            "start_period": str(date.today()),  # Will be overridden by dynamic period
            "end_period": str(date.today()),  # Will be overridden by dynamic period
            "table_data_series": str(table_data_series.uuid),
            "table_type": "ANALYSIS",
            "columns_break": "DAY",
            "dynamic_period_in_days": "30",
        }

        response = client.get(
            path="/{}/Preview/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=preview_params,
        )

        assert response.status_code == status.HTTP_200_OK
        response_data = response.json()
        assert "data" in response_data
        assert isinstance(response_data["data"], list)
        assert len(response_data["data"]) > 0
        assert "data" in response_data["data"][0]
        assert response_data["data"][0]["data"] == "test"
