from datetime import datetime
from unittest.mock import Mock, patch

import pytest
import pytz
from django.test import TestCase
from rest_framework import status

from helpers.apis.hidro_api.functions import hidro_api

pytestmark = pytest.mark.django_db


class TestHidroApi(TestCase):
    """Tests for hidro_api function"""

    @patch("helpers.apis.hidro_api.functions.Log")
    @patch("helpers.apis.hidro_api.functions.requests")
    @patch("helpers.apis.hidro_api.functions.credentials")
    def test_hidro_api_successful_response(self, mock_creds, mock_requests, mock_log):
        """Test successful API call with valid response"""
        # Setup
        mock_creds.HIDRO_URL = "https://api.example.com"
        mock_creds.HIDRO_USERNAME = "user"
        mock_creds.HIDRO_PWD = "pass"

        mock_response = Mock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json.return_value = {
            "codResultado": "1",
            "NivelReservatorioDataHoraLista": [{"nivel": 100, "data": "01/01/2023"}],
        }
        mock_response.headers = {"Content-Type": "application/json"}
        mock_requests.post.return_value = mock_response

        # Call function
        dam = "DAM001"
        date = datetime(2023, 8, 22, 15, 30, tzinfo=pytz.UTC)
        result = hidro_api(dam, date)

        # Verify
        assert result["response"] == {"nivel": 100, "data": "01/01/2023"}
        assert result["error"] is None
        assert "tryFrom" in result
        assert "tryUntil" in result

        # Verify API was called
        mock_requests.post.assert_called_once()

        # Verify log was created
        mock_log.objects.create.assert_called_once()

    @patch("helpers.apis.hidro_api.functions.Log")
    @patch("helpers.apis.hidro_api.functions.requests")
    @patch("helpers.apis.hidro_api.functions.credentials")
    def test_hidro_api_zero_cod_resultado(self, mock_creds, mock_requests, mock_log):
        """Test when codResultado is 0 (no data)"""
        mock_creds.HIDRO_URL = "https://api.example.com"
        mock_creds.HIDRO_USERNAME = "user"
        mock_creds.HIDRO_PWD = "pass"

        mock_response = Mock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json.return_value = {"codResultado": "0"}
        mock_response.headers = {}
        mock_requests.post.return_value = mock_response

        dam = "DAM001"
        date = datetime(2023, 8, 22, 15, 30, tzinfo=pytz.UTC)
        result = hidro_api(dam, date)

        # Should return None as response when codResultado is 0
        assert result["response"] is None

    @patch("helpers.apis.hidro_api.functions.Log")
    @patch("helpers.apis.hidro_api.functions.requests")
    @patch("helpers.apis.hidro_api.functions.credentials")
    def test_hidro_api_request_exception(self, mock_creds, mock_requests, mock_log):
        """Test when request raises an exception"""
        mock_creds.HIDRO_URL = "https://api.example.com"
        mock_creds.HIDRO_USERNAME = "user"
        mock_creds.HIDRO_PWD = "pass"

        mock_requests.post.side_effect = Exception("Connection timeout")

        dam = "DAM001"
        date = datetime(2023, 8, 22, 15, 30, tzinfo=pytz.UTC)
        result = hidro_api(dam, date)

        # Should handle exception and return error
        assert result["response"] is None
        assert result["error"] == "Connection timeout"

        # Log should still be created
        mock_log.objects.create.assert_called_once()

    @patch("helpers.apis.hidro_api.functions.Log")
    @patch("helpers.apis.hidro_api.functions.requests")
    @patch("helpers.apis.hidro_api.functions.credentials")
    def test_hidro_api_non_200_status(self, mock_creds, mock_requests, mock_log):
        """Test when API returns non-200 status code"""
        mock_creds.HIDRO_URL = "https://api.example.com"
        mock_creds.HIDRO_USERNAME = "user"
        mock_creds.HIDRO_PWD = "pass"

        mock_response = Mock()
        mock_response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_response.headers = {}
        mock_requests.post.return_value = mock_response

        dam = "DAM001"
        date = datetime(2023, 8, 22, 15, 30, tzinfo=pytz.UTC)
        result = hidro_api(dam, date)

        # Should return None and error message
        assert result["response"] is None
        assert "Response Status Code 500" in result["error"]

    @patch("helpers.apis.hidro_api.functions.Log")
    @patch("helpers.apis.hidro_api.functions.requests")
    @patch("helpers.apis.hidro_api.functions.credentials")
    def test_hidro_api_creates_log_entry(self, mock_creds, mock_requests, mock_log):
        """Test that API call creates a log entry"""
        mock_creds.HIDRO_URL = "https://api.example.com"
        mock_creds.HIDRO_USERNAME = "user"
        mock_creds.HIDRO_PWD = "pass"

        mock_response = Mock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json.return_value = {
            "codResultado": "1",
            "NivelReservatorioDataHoraLista": [{}],
        }
        mock_response.headers = {}
        mock_requests.post.return_value = mock_response

        dam = "DAM001"
        date = datetime(2023, 8, 22, 18, 0, tzinfo=pytz.UTC)

        hidro_api(dam, date)

        # Verify log was created
        assert mock_log.objects.create.called
        call_args = mock_log.objects.create.call_args
        assert "description" in call_args[1]
        assert "date" in call_args[1]
