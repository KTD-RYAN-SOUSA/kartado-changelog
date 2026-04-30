import pytest
from django.test import TestCase

pytestmark = pytest.mark.django_db


class TestCustomDjangoPaginator(TestCase):
    """Tests for CustomDjangoPaginator"""

    def test_count_with_list(self):
        """Test count with regular list (not QuerySet)"""
        from helpers.pagination import CustomDjangoPaginator

        items = [1, 2, 3, 4, 5]
        paginator = CustomDjangoPaginator(items, per_page=2)

        result = paginator.count

        assert result == 5

    def test_count_with_empty_list(self):
        """Test count with empty list"""
        from helpers.pagination import CustomDjangoPaginator

        items = []
        paginator = CustomDjangoPaginator(items, per_page=10)

        result = paginator.count

        assert result == 0

    def test_count_with_large_list(self):
        """Test count with large list"""
        from helpers.pagination import CustomDjangoPaginator

        items = list(range(1000))
        paginator = CustomDjangoPaginator(items, per_page=50)

        result = paginator.count

        assert result == 1000


class TestCustomPagination(TestCase):
    """Tests for CustomPagination"""

    def test_custom_pagination_configuration(self):
        """Test CustomPagination settings"""
        from helpers.pagination import CustomPagination

        pagination = CustomPagination()

        assert pagination.page_query_param == "page"
        assert pagination.page_size_query_param == "page_size"
        assert pagination.max_page_size == 100000

    def test_custom_pagination_uses_custom_django_paginator(self):
        """Test that CustomPagination uses CustomDjangoPaginator"""
        from helpers.pagination import CustomDjangoPaginator, CustomPagination

        pagination = CustomPagination()

        assert pagination.django_paginator_class == CustomDjangoPaginator

    def test_custom_pagination_inherits_from_json_api_pagination(self):
        """Test that CustomPagination inherits from JsonApiPageNumberPagination"""
        from rest_framework_json_api import pagination

        from helpers.pagination import CustomPagination

        assert issubclass(CustomPagination, pagination.JsonApiPageNumberPagination)
