from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

from helpers.error_messages import error_message

pytestmark = pytest.mark.django_db


class TestErrorMessage(TestCase):
    """Tests for error_message function"""

    def test_error_message_with_valid_status_code(self):
        """Test error_message with valid HTTP status code"""
        result = error_message(404, "Not found")

        assert result.status_code == 404
        assert len(result.data) == 1
        assert result.data[0]["detail"] == "Not found"
        assert result.data[0]["status"] == 404
        assert result.data[0]["source"]["pointer"] == "/data"

    def test_error_message_with_400_bad_request(self):
        """Test error_message with 400 Bad Request"""
        result = error_message(400, "Bad request")

        assert result.status_code == 400
        assert result.data[0]["detail"] == "Bad request"
        assert result.data[0]["status"] == 400

    def test_error_message_with_401_unauthorized(self):
        """Test error_message with 401 Unauthorized"""
        result = error_message(401, "Unauthorized access")

        assert result.status_code == 401
        assert result.data[0]["detail"] == "Unauthorized access"

    def test_error_message_with_403_forbidden(self):
        """Test error_message with 403 Forbidden"""
        result = error_message(403, "Forbidden")

        assert result.status_code == 403
        assert result.data[0]["detail"] == "Forbidden"

    def test_error_message_with_500_internal_server_error(self):
        """Test error_message with 500 Internal Server Error"""
        result = error_message(500, "Internal server error")

        assert result.status_code == 500
        assert result.data[0]["detail"] == "Internal server error"

    def test_error_message_with_invalid_status_code(self):
        """Test error_message with invalid HTTP status code"""
        result = error_message(999, "Invalid status")

        assert "status" in result.data["attributes"]
        assert (
            result.data["attributes"]["status"] == "Erro! Http status não encontrado."
        )

    def test_error_message_with_custom_message(self):
        """Test error_message preserves custom error message"""
        custom_msg = "This is a custom error message"
        result = error_message(422, custom_msg)

        assert result.status_code == 422
        assert result.data[0]["detail"] == custom_msg

    def test_error_message_response_structure(self):
        """Test that error_message returns correct response structure"""
        result = error_message(404, "Resource not found")

        assert hasattr(result, "status_code")
        assert hasattr(result, "data")

        assert isinstance(result.data, list)
        assert "detail" in result.data[0]
        assert "source" in result.data[0]
        assert "status" in result.data[0]
        assert "pointer" in result.data[0]["source"]

    def test_error_message_with_200_ok(self):
        """Test error_message with 200 OK (edge case)"""
        result = error_message(200, "OK")

        assert result.status_code == 200
        assert result.data[0]["detail"] == "OK"

    def test_error_message_with_201_created(self):
        """Test error_message with 201 Created"""
        result = error_message(201, "Created")

        assert result.status_code == 201
        assert result.data[0]["detail"] == "Created"


class TestCustomExceptionHandler(TestCase):
    """Tests for custom_exception_handler function"""

    @patch("helpers.error_messages.exception_handler")
    def test_custom_exception_handler_non_patch_method(self, mock_exception_handler):
        """Test that non-PATCH requests just call default exception handler"""
        from helpers.error_messages import custom_exception_handler

        mock_response = Mock()
        mock_exception_handler.return_value = mock_response

        mock_request = Mock()
        mock_request._request.method = "GET"
        mock_view = Mock()
        mock_view.request = mock_request

        context = {"view": mock_view, "kwargs": {}}
        exc = Exception("Test exception")

        result = custom_exception_handler(exc, context)

        assert result == mock_response
        mock_exception_handler.assert_called_once_with(exc, context)

    @patch("helpers.error_messages.send_email_export_request")
    @patch("helpers.error_messages.ExportRequest")
    @patch("helpers.error_messages.exception_handler")
    def test_custom_exception_handler_patch_with_export_request(
        self, mock_exception_handler, mock_export_request_model, mock_send_email
    ):
        """Test PATCH request with ExportRequest model"""
        from helpers.error_messages import custom_exception_handler

        mock_response = Mock()
        mock_exception_handler.return_value = mock_response

        mock_obj = Mock()
        mock_obj.error = False
        mock_export_request_model.objects.get.return_value = mock_obj

        mock_serializer_class = Mock()
        mock_serializer_class().Meta.model = mock_export_request_model
        mock_request = Mock()
        mock_request._request.method = "PATCH"
        mock_view = Mock()
        mock_view.request = mock_request
        mock_view.serializer_class = mock_serializer_class

        context = {"view": mock_view, "kwargs": {"pk": 123}}
        exc = Exception("Test exception")

        result = custom_exception_handler(exc, context)

        assert mock_obj.error is True
        mock_obj.save.assert_called_once()
        mock_send_email.assert_called_once_with(mock_obj)
        assert result == mock_response

    @patch("helpers.error_messages.exception_handler")
    def test_custom_exception_handler_patch_without_export_request(
        self, mock_exception_handler
    ):
        """Test PATCH request with non-ExportRequest model"""
        from helpers.error_messages import custom_exception_handler

        mock_response = Mock()
        mock_exception_handler.return_value = mock_response

        mock_other_model = Mock()
        mock_serializer_class = Mock()
        mock_serializer_class().Meta.model = mock_other_model
        mock_request = Mock()
        mock_request._request.method = "PATCH"
        mock_view = Mock()
        mock_view.request = mock_request
        mock_view.serializer_class = mock_serializer_class

        context = {"view": mock_view, "kwargs": {}}
        exc = Exception("Test exception")

        result = custom_exception_handler(exc, context)

        assert result == mock_response
