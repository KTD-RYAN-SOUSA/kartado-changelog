from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

from helpers.custom_endpoints import get_pagination_info

pytestmark = pytest.mark.django_db


class TestGetPaginationInfo(TestCase):
    """Tests for get_pagination_info function"""

    @patch("helpers.custom_endpoints.settings")
    def test_get_pagination_info_default_values(self, mock_settings):
        """Test pagination with default page and page_size"""
        mock_settings.REST_FRAMEWORK = {"PAGE_SIZE": 20}

        request = Mock()
        request.query_params.get.return_value = None

        result = get_pagination_info(request, item_count=100)

        assert result["pagination"]["page"] == 1
        assert result["pagination"]["pages"] == 5  # ceil(100/20)
        assert result["pagination"]["count"] == 100

    @patch("helpers.custom_endpoints.settings")
    def test_get_pagination_info_custom_page_size(self, mock_settings):
        """Test pagination with custom page_size"""
        mock_settings.REST_FRAMEWORK = {"PAGE_SIZE": 20}

        request = Mock()
        request.query_params.get.side_effect = (
            lambda key: "50" if key == "page_size" else None
        )

        result = get_pagination_info(request, item_count=100)

        assert result["pagination"]["page"] == 1
        assert result["pagination"]["pages"] == 2  # ceil(100/50)
        assert result["pagination"]["count"] == 100

    @patch("helpers.custom_endpoints.settings")
    def test_get_pagination_info_custom_page_num(self, mock_settings):
        """Test pagination with custom page number"""
        mock_settings.REST_FRAMEWORK = {"PAGE_SIZE": 20}

        request = Mock()
        request.query_params.get.side_effect = (
            lambda key: "3" if key == "page" else None
        )

        result = get_pagination_info(request, item_count=100)

        assert result["pagination"]["page"] == 3
        assert result["pagination"]["pages"] == 5
        assert result["pagination"]["count"] == 100

    @patch("helpers.custom_endpoints.settings")
    def test_get_pagination_info_both_custom(self, mock_settings):
        """Test pagination with both custom page and page_size"""
        mock_settings.REST_FRAMEWORK = {"PAGE_SIZE": 20}

        request = Mock()
        request.query_params.get.side_effect = (
            lambda key: "2" if key == "page" else "25" if key == "page_size" else None
        )

        result = get_pagination_info(request, item_count=100)

        assert result["pagination"]["page"] == 2
        assert result["pagination"]["pages"] == 4  # ceil(100/25)
        assert result["pagination"]["count"] == 100

    @patch("helpers.custom_endpoints.settings")
    def test_get_pagination_info_no_items(self, mock_settings):
        """Test pagination with zero items"""
        mock_settings.REST_FRAMEWORK = {"PAGE_SIZE": 20}

        request = Mock()
        request.query_params.get.return_value = None

        result = get_pagination_info(request, item_count=0)

        assert result["pagination"]["page"] == 1
        assert result["pagination"]["pages"] == 1  # At least 1 page
        assert result["pagination"]["count"] == 0

    @patch("helpers.custom_endpoints.settings")
    def test_get_pagination_info_exact_page_size(self, mock_settings):
        """Test when item count is exact multiple of page_size"""
        mock_settings.REST_FRAMEWORK = {"PAGE_SIZE": 25}

        request = Mock()
        request.query_params.get.return_value = None

        result = get_pagination_info(request, item_count=100)

        assert result["pagination"]["pages"] == 4  # Exact: 100/25 = 4

    @patch("helpers.custom_endpoints.settings")
    def test_get_pagination_info_less_than_page_size(self, mock_settings):
        """Test when item count is less than page_size"""
        mock_settings.REST_FRAMEWORK = {"PAGE_SIZE": 50}

        request = Mock()
        request.query_params.get.return_value = None

        result = get_pagination_info(request, item_count=30)

        assert result["pagination"]["pages"] == 1
        assert result["pagination"]["count"] == 30

    @patch("helpers.custom_endpoints.settings")
    def test_get_pagination_info_large_dataset(self, mock_settings):
        """Test pagination with large dataset"""
        mock_settings.REST_FRAMEWORK = {"PAGE_SIZE": 100}

        request = Mock()
        request.query_params.get.return_value = None

        result = get_pagination_info(request, item_count=1523)

        assert result["pagination"]["pages"] == 16  # ceil(1523/100)
        assert result["pagination"]["count"] == 1523
