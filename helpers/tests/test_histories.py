from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

pytestmark = pytest.mark.django_db


class TestGetHistoriesByApps(TestCase):
    """Tests for get_histories_by_apps function"""

    @patch("helpers.histories.apps")
    def test_get_histories_by_apps_counts_histories(self, mock_apps):
        """Test counting histories per model in an app"""
        from helpers.histories import get_histories_by_apps

        mock_model1 = Mock()
        mock_model1.history.all.return_value = [1, 2, 3]  # 3 histories

        mock_model2 = Mock()
        mock_model2.history.all.return_value = [1, 2, 3, 4, 5]  # 5 histories

        mock_apps.all_models = {"test_app": ["model1", "model2", "historical_model"]}
        mock_apps.get_model.side_effect = lambda app_label, model_name: {
            "model1": mock_model1,
            "model2": mock_model2,
        }[model_name]

        result = get_histories_by_apps("test_app")

        assert result["model1"] == 3
        assert result["model2"] == 5
        assert result["total"] == 8
        assert "historical_model" not in result

    @patch("helpers.histories.apps")
    def test_get_histories_by_apps_excludes_historical_models(self, mock_apps):
        """Test that historical models are excluded"""
        from helpers.histories import get_histories_by_apps

        mock_model = Mock()
        mock_model.history.all.return_value = [1, 2]

        mock_apps.all_models = {
            "test_app": ["model", "historicalmodel", "another_historical"]
        }
        mock_apps.get_model.return_value = mock_model

        result = get_histories_by_apps("test_app")

        assert "model" in result
        assert "historicalmodel" not in result
        assert "another_historical" not in result

    @patch("helpers.histories.apps")
    def test_get_histories_by_apps_excludes_underscore_models(self, mock_apps):
        """Test that models with underscore are excluded"""
        from helpers.histories import get_histories_by_apps

        mock_model = Mock()
        mock_model.history.all.return_value = [1]

        mock_apps.all_models = {"test_app": ["model", "_private_model"]}
        mock_apps.get_model.return_value = mock_model

        result = get_histories_by_apps("test_app")

        assert "model" in result
        assert "_private_model" not in result


class TestAddHistoryChangeReason(TestCase):
    """Tests for add_history_change_reason function"""

    def test_add_history_change_reason_with_reason(self):
        """Test adding change reason to history"""
        from helpers.histories import add_history_change_reason

        mock_hist = Mock()
        mock_instance = Mock()
        mock_instance.history.first.return_value = mock_hist

        initial_data = {"history_change_reason": "Updated by user"}

        add_history_change_reason(mock_instance, initial_data)

        assert mock_hist.history_change_reason == "Updated by user"
        mock_hist.save.assert_called_once()

    def test_add_history_change_reason_without_reason(self):
        """Test when no change reason is provided"""
        from helpers.histories import add_history_change_reason

        mock_instance = Mock()

        initial_data = {}

        add_history_change_reason(mock_instance, initial_data)

        mock_instance.history.first.assert_not_called()

    def test_add_history_change_reason_with_non_string_reason(self):
        """Test when change reason is not a string"""
        from helpers.histories import add_history_change_reason

        mock_instance = Mock()

        initial_data = {"history_change_reason": 123}  # Not a string

        add_history_change_reason(mock_instance, initial_data)

        mock_instance.history.first.assert_not_called()

    def test_add_history_change_reason_with_empty_string(self):
        """Test with empty string reason"""
        from helpers.histories import add_history_change_reason

        mock_hist = Mock()
        mock_instance = Mock()
        mock_instance.history.first.return_value = mock_hist

        initial_data = {"history_change_reason": ""}

        add_history_change_reason(mock_instance, initial_data)

        mock_instance.history.first.assert_not_called()


class TestHistoricalRecordField(TestCase):
    """Tests for HistoricalRecordField"""

    def test_historical_record_field_to_representation(self):
        """Test to_representation converts dict values to list"""
        from helpers.histories import HistoricalRecordField

        field = HistoricalRecordField()

        mock_data = Mock()
        mock_data.values.return_value = [
            {"id": 1, "name": "Item 1"},
            {"id": 2, "name": "Item 2"},
        ]

        result = field.to_representation(mock_data)

        mock_data.values.assert_called_once()
        assert isinstance(result, list)
