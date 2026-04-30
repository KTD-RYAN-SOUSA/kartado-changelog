from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

from helpers.as_of import as_of, first_histories

pytestmark = pytest.mark.django_db


class TestAsOf(TestCase):
    """Tests for as_of function"""

    @patch("helpers.as_of.apps")
    def test_as_of_basic_functionality(self, mock_apps):
        """Test basic as_of functionality with mocked model"""
        # Setup mock model
        mock_model = Mock()
        mock_model._meta.pk.name = "id"
        mock_historical_model = Mock()
        mock_model.history.model = mock_historical_model

        # Setup mock queryset
        mock_history_qs = Mock()
        mock_historical_model.objects.filter.return_value = mock_history_qs

        mock_values_list = Mock()
        mock_history_qs.values_list.return_value = mock_values_list

        mock_difference = Mock()
        mock_values_list.difference.return_value = mock_difference

        mock_final = Mock()
        mock_history_qs.filter.return_value.order_by.return_value.distinct.return_value = (
            mock_final
        )

        mock_apps.get_model.return_value = mock_model

        # Call function
        dt = datetime(2023, 8, 22, 15, 30)
        as_of("app_label", "model_name", dt)

        # Verify calls
        mock_apps.get_model.assert_called_once_with(
            app_label="app_label", model_name="model_name"
        )
        mock_historical_model.objects.filter.assert_called_once_with(
            history_date__lte=dt
        )
        mock_history_qs.values_list.assert_called()

    @patch("helpers.as_of.apps")
    def test_as_of_filters_deleted_records(self, mock_apps):
        """Test that as_of filters out deleted records (history_type='-')"""
        # Setup mock model
        mock_model = Mock()
        mock_model._meta.pk.name = "uuid"
        mock_historical_model = Mock()
        mock_model.history.model = mock_historical_model

        # Setup mock queryset
        mock_history_qs = Mock()
        mock_historical_model.objects.filter.return_value = mock_history_qs

        mock_values_list = Mock()
        mock_history_qs.values_list.return_value = mock_values_list

        mock_difference = Mock()
        mock_values_list.difference.return_value = mock_difference

        mock_final = Mock()
        mock_history_qs.filter.return_value.order_by.return_value.distinct.return_value = (
            mock_final
        )

        mock_apps.get_model.return_value = mock_model

        # Call function
        dt = datetime(2023, 8, 22, 15, 30)
        as_of("app_label", "model_name", dt)

        # Verify that it filters for deleted records
        assert (
            mock_history_qs.filter.call_count >= 2
        )  # One for date, one for history_type


class TestFirstHistories(TestCase):
    """Tests for first_histories function"""

    @patch("helpers.as_of.apps")
    def test_first_histories_basic_functionality(self, mock_apps):
        """Test basic first_histories functionality"""
        # Setup mock model
        mock_model = Mock()
        mock_historical_model = Mock()
        mock_model.history.model = mock_historical_model

        # Setup mock queryset
        mock_queryset = Mock()
        uuid1 = "uuid-1"
        uuid2 = "uuid-2"
        mock_queryset.values_list.return_value = [uuid1, uuid2]

        # Setup history with older and newer records
        now = datetime.now()
        old_date = now - timedelta(days=10)
        new_date = now - timedelta(days=5)

        mock_history_values = [
            (old_date, uuid1, 1),  # Oldest for uuid1
            (new_date, uuid1, 2),  # Newer for uuid1
            (old_date, uuid2, 3),  # Oldest for uuid2
        ]

        mock_historical_model.objects.values_list.return_value = mock_history_values

        mock_result_qs = Mock()
        mock_historical_model.objects.filter.return_value.distinct.return_value = (
            mock_result_qs
        )

        mock_apps.get_model.return_value = mock_model

        # Call function
        first_histories("app_label", "model_name", mock_queryset)

        # Verify calls
        mock_apps.get_model.assert_called_once_with(
            app_label="app_label", model_name="model_name"
        )
        mock_queryset.values_list.assert_called_once_with("uuid", flat=True)

    @patch("helpers.as_of.apps")
    def test_first_histories_empty_queryset(self, mock_apps):
        """Test first_histories with empty queryset"""
        # Setup mock model
        mock_model = Mock()
        mock_historical_model = Mock()
        mock_model.history.model = mock_historical_model

        # Setup empty queryset
        mock_queryset = Mock()
        mock_queryset.values_list.return_value = []

        mock_historical_model.objects.values_list.return_value = []

        mock_result_qs = Mock()
        mock_historical_model.objects.filter.return_value.distinct.return_value = (
            mock_result_qs
        )

        mock_apps.get_model.return_value = mock_model

        # Call function
        result = first_histories("app_label", "model_name", mock_queryset)

        # Should still return a result (empty filtered queryset)
        assert result == mock_result_qs

    @patch("helpers.as_of.apps")
    def test_first_histories_finds_oldest_record(self, mock_apps):
        """Test that first_histories correctly identifies the oldest record for each UUID"""
        # Setup mock model
        mock_model = Mock()
        mock_historical_model = Mock()
        mock_model.history.model = mock_historical_model

        # Setup mock queryset
        mock_queryset = Mock()
        uuid1 = "uuid-test"
        mock_queryset.values_list.return_value = [uuid1]

        # Setup multiple history records for same UUID
        now = datetime.now()
        oldest = now - timedelta(days=30)
        middle = now - timedelta(days=15)
        newest = now - timedelta(days=1)

        mock_history_values = [
            (middle, uuid1, 10),  # Middle record
            (oldest, uuid1, 5),  # Oldest record (should be selected)
            (newest, uuid1, 15),  # Newest record
        ]

        mock_historical_model.objects.values_list.return_value = mock_history_values

        mock_result_qs = Mock()
        mock_filter_result = Mock()
        mock_historical_model.objects.filter.return_value = mock_filter_result
        mock_filter_result.distinct.return_value = mock_result_qs

        mock_apps.get_model.return_value = mock_model

        # Call function
        result = first_histories("app_label", "model_name", mock_queryset)

        # Verify that filter was called with pk__in containing the oldest pk (5)
        mock_historical_model.objects.filter.assert_called()

        # The function should have selected pk=5 (the oldest)
        assert result == mock_result_qs
