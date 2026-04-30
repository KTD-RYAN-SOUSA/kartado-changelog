from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from django.test import TestCase
from rest_framework.response import Response

from apps.reportings.views import InventoryView

pytestmark = pytest.mark.django_db


class InventoryViewTestCase(TestCase):
    def setUp(self):
        self.view = InventoryView()
        self.view.request = Mock()
        self.view.request.query_params = {"company": str(uuid4())}
        self.view.get_queryset = Mock()
        self.view.filter_queryset = Mock()
        self.view.paginate_queryset = Mock()
        self.view.get_paginated_response = Mock(
            return_value=Response({"data": "paginated"})
        )

        self.queryset = Mock()
        self.queryset.filter.return_value = self.queryset
        self.queryset.values_list.return_value = self.queryset
        self.queryset.first.return_value = Mock(road_name="test_road/123")

        self.view.filter_queryset.return_value = self.queryset

    @patch("apps.reportings.views.Company.objects.get")
    @patch("apps.reportings.views.InventoryScheduleEndpoint")
    def test_inventory_schedule(self, mock_endpoint, mock_company_get):
        mock_company = Mock()
        mock_company_get.return_value = mock_company

        mock_endpoint_instance = Mock()
        mock_endpoint_instance.get_data.return_value = {"test": "data"}
        mock_endpoint.return_value = mock_endpoint_instance

        response = self.view.inventory_schedule(self.view.request)

        self.queryset.filter.assert_called_with(occurrence_type__is_oae=True)
        mock_company_get.assert_called_with(
            uuid=self.view.request.query_params["company"]
        )
        mock_endpoint.assert_called_with(inventory=self.queryset, company=mock_company)
        mock_endpoint_instance.get_data.assert_called_once()

        self.assertEqual(
            response.data, {"type": "InventorySchedule", "attributes": {"test": "data"}}
        )

    @patch("apps.reportings.views.Company.objects.get")
    @patch("apps.reportings.views.get_excel_name")
    @patch("apps.reportings.views.run_async_artesp_excel_export")
    @patch("apps.reportings.views.get_url")
    def test_schedule_excel_export(
        self, mock_get_url, mock_run_export, mock_get_excel_name, mock_company_get
    ):
        mock_company = Mock()
        mock_company.uuid = uuid4()
        mock_company_get.return_value = mock_company

        mock_get_excel_name.return_value = "test_excel_name"
        mock_get_url.return_value = "https://example.com/excel"

        self.queryset.values_list.return_value.flat = True
        self.queryset.values_list.return_value = [uuid4(), uuid4()]

        response = self.view.schedule_excel_export(self.view.request)

        self.queryset.filter.assert_called_with(occurrence_type__is_oae=True)
        mock_company_get.assert_called_with(
            uuid=self.view.request.query_params["company"]
        )
        mock_get_excel_name.assert_called_with("test_road_123")

        mock_run_export.assert_called_once()
        mock_get_url.assert_called_with("test_excel_name")

        self.assertEqual(
            response.data,
            {"type": "ArtespExcelExport", "attributes": "https://example.com/excel"},
        )

    @patch("apps.reportings.views.Company.objects.get")
    @patch("apps.reportings.views.get_excel_name")
    @patch("apps.reportings.views.run_async_artesp_excel_export_compact")
    @patch("apps.reportings.views.get_url_compact")
    def test_schedule_excel_compact_export(
        self,
        mock_get_url_compact,
        mock_run_export_compact,
        mock_get_excel_name,
        mock_company_get,
    ):
        mock_company = Mock()
        mock_company.uuid = uuid4()
        mock_company_get.return_value = mock_company

        mock_get_excel_name.return_value = "test_excel_name"
        mock_get_url_compact.return_value = "https://example.com/excel-compact"

        self.queryset.values_list.return_value.flat = True
        self.queryset.values_list.return_value = [uuid4(), uuid4()]

        response = self.view.schedule_excel_compact_export(self.view.request)

        self.queryset.filter.assert_called_with(occurrence_type__is_oae=True)
        mock_company_get.assert_called_with(
            uuid=self.view.request.query_params["company"]
        )
        mock_get_excel_name.assert_called_with("test_road_123")

        mock_run_export_compact.assert_called_once()
        mock_get_url_compact.assert_called_with("test_excel_name")

        self.assertEqual(
            response.data,
            {
                "type": "ArtespExcelExport",
                "attributes": "https://example.com/excel-compact",
            },
        )

    @patch("apps.reportings.views.Company.objects.get")
    @patch("apps.reportings.views.return_inventory_fields")
    def test_return_choices(self, mock_return_inventory_fields, mock_company_get):
        mock_company = Mock()
        mock_company_get.return_value = mock_company
        mock_return_inventory_fields.return_value = {"choices": ["choice1", "choice2"]}

        response = self.view.return_choices(self.view.request)

        mock_company_get.assert_called_with(
            uuid=self.view.request.query_params["company"]
        )
        mock_return_inventory_fields.assert_called_with(mock_company)

        self.assertEqual(response.data, {"choices": ["choice1", "choice2"]})

    @patch("apps.reportings.views.Company.objects.get")
    @patch("apps.reportings.views.InventorySpreadsheeetEndpoint")
    def test_spreadsheeet_inventory_list_with_pagination(
        self, mock_endpoint, mock_company_get
    ):
        mock_company = Mock()
        mock_company_get.return_value = mock_company

        mock_endpoint_instance = Mock()
        mock_endpoint_instance.get_data.return_value = {"spreadsheet": "data"}
        mock_endpoint.return_value = mock_endpoint_instance

        page = ["item1", "item2"]
        self.view.paginate_queryset.return_value = page

        response = self.view.spreadsheeet_inventory_list(self.view.request)

        mock_company_get.assert_called_with(
            uuid=self.view.request.query_params["company"]
        )
        self.view.paginate_queryset.assert_called_with(self.queryset)
        mock_endpoint.assert_called_with(page, mock_company)
        mock_endpoint_instance.get_data.assert_called_once()
        self.view.get_paginated_response.assert_called_with({"spreadsheet": "data"})

        self.assertEqual(response.data, {"data": "paginated"})

    @patch("apps.reportings.views.Company.objects.get")
    @patch("apps.reportings.views.InventorySpreadsheeetEndpoint")
    def test_spreadsheeet_inventory_list_without_pagination(
        self, mock_endpoint, mock_company_get
    ):
        mock_company = Mock()
        mock_company_get.return_value = mock_company

        mock_endpoint_instance = Mock()
        mock_endpoint_instance.get_data.return_value = {"spreadsheet": "data"}
        mock_endpoint.return_value = mock_endpoint_instance

        self.view.paginate_queryset.return_value = None

        response = self.view.spreadsheeet_inventory_list(self.view.request)

        mock_company_get.assert_called_with(
            uuid=self.view.request.query_params["company"]
        )
        self.view.paginate_queryset.assert_called_with(self.queryset)
        mock_endpoint.assert_called_with(self.queryset, mock_company)
        mock_endpoint_instance.get_data.assert_called_once()

        self.assertEqual(response.data, {"spreadsheet": "data"})

    @patch("apps.reportings.views.error_message")
    def test_return_choices_without_company(self, mock_error_message):
        self.view.request.query_params = {}
        mock_error_message.return_value = Response(
            {"error": "Company required"}, status=400
        )

        response = self.view.return_choices(self.view.request)

        mock_error_message.assert_called_with(400, 'Parâmetro "Unidade" é obrigatório')
        self.assertEqual(response.data, {"error": "Company required"})
