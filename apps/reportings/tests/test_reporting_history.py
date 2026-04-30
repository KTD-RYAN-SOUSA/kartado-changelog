from unittest.mock import MagicMock

import pytest

from apps.reportings.helpers.get.history import get_reporting_history

pytestmark = pytest.mark.django_db


class TestGetReportingHistory:
    def test_get_reporting_history_with_matching_approval_step(self):
        mock_company = MagicMock()
        mock_company.metadata = {"approved_approval_steps": ["1", "2", "3"]}

        mock_reporting = MagicMock()
        mock_reporting.company = mock_company

        hist1 = MagicMock()
        hist1.approval_step_id = "5"  # Não está nos approved_statuses

        hist2 = MagicMock()
        hist2.approval_step_id = "2"  # Está nos approved_statuses

        hist3 = MagicMock()
        hist3.approval_step_id = "4"  # Não está nos approved_statuses

        mock_reporting.historicalreporting.all.return_value = [hist1, hist2, hist3]

        result = get_reporting_history(mock_reporting)

        assert result == hist2

    def test_get_reporting_history_with_no_matching_approval_step(self):
        mock_company = MagicMock()
        mock_company.metadata = {"approved_approval_steps": ["1", "2", "3"]}

        mock_reporting = MagicMock()
        mock_reporting.company = mock_company

        hist1 = MagicMock()
        hist1.approval_step_id = "4"

        hist2 = MagicMock()
        hist2.approval_step_id = "5"

        mock_reporting.historicalreporting.all.return_value = [hist1, hist2]

        result = get_reporting_history(mock_reporting)

        assert result is None

    def test_get_reporting_history_with_empty_history(self):
        mock_company = MagicMock()
        mock_company.metadata = {"approved_approval_steps": ["1", "2", "3"]}

        mock_reporting = MagicMock()
        mock_reporting.company = mock_company

        mock_reporting.historicalreporting.all.return_value = []

        result = get_reporting_history(mock_reporting)

        assert result is None

    def test_get_reporting_history_with_empty_approved_statuses(self):
        mock_company = MagicMock()
        mock_company.metadata = {"approved_approval_steps": []}

        mock_reporting = MagicMock()
        mock_reporting.company = mock_company

        hist1 = MagicMock()
        hist1.approval_step_id = "1"

        mock_reporting.historicalreporting.all.return_value = [hist1]
        result = get_reporting_history(mock_reporting)

        assert result is None

    def test_get_reporting_history_with_missing_metadata(self):
        mock_company = MagicMock()
        mock_company.metadata = {}

        mock_reporting = MagicMock()
        mock_reporting.company = mock_company

        hist1 = MagicMock()
        hist1.approval_step_id = "1"

        mock_reporting.historicalreporting.all.return_value = [hist1]
        result = get_reporting_history(mock_reporting)

        assert result is None
