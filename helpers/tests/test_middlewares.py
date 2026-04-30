from unittest.mock import Mock, patch

import pytest
from django.test import TestCase
from django_ratelimit.exceptions import Ratelimited
from rest_framework.request import Request

pytestmark = pytest.mark.django_db


class TestGetCurrentRequest(TestCase):
    """Tests for get_current_request function"""

    def test_get_current_request_when_set(self):
        """Test getting current request when it exists"""
        from helpers.middlewares import _thread_locals, get_current_request

        mock_request = Mock()
        _thread_locals.request = mock_request

        result = get_current_request()

        assert result == mock_request

        del _thread_locals.request

    def test_get_current_request_when_not_set(self):
        """Test getting current request when it doesn't exist"""
        from helpers.middlewares import _thread_locals, get_current_request

        if hasattr(_thread_locals, "request"):
            del _thread_locals.request

        result = get_current_request()

        assert result is None

    def test_get_current_request_with_default_to_empty_request(self):
        """Test with default_to_empty_request=True"""
        from helpers.middlewares import _thread_locals, get_current_request

        if hasattr(_thread_locals, "request"):
            del _thread_locals.request

        result = get_current_request(default_to_empty_request=True)

        assert result is not None
        assert isinstance(result, Request)


class TestGetCurrentUser(TestCase):
    """Tests for get_current_user function"""

    def test_get_current_user_when_request_exists(self):
        """Test getting current user when request exists"""
        from helpers.middlewares import _thread_locals, get_current_user

        mock_user = Mock()
        mock_request = Mock()
        mock_request.user = mock_user
        _thread_locals.request = mock_request

        result = get_current_user()

        assert result == mock_user

        del _thread_locals.request

    def test_get_current_user_when_no_request(self):
        """Test getting current user when no request exists"""
        from helpers.middlewares import _thread_locals, get_current_user

        if hasattr(_thread_locals, "request"):
            del _thread_locals.request

        result = get_current_user()

        assert result is None

    def test_get_current_user_when_request_has_no_user(self):
        """Test when request exists but has no user attribute"""
        from helpers.middlewares import _thread_locals, get_current_user

        mock_request = Mock(spec=[])  # Empty spec = no attributes
        _thread_locals.request = mock_request

        result = get_current_user()

        assert result is None

        del _thread_locals.request


class TestActionLogMiddleware(TestCase):
    """Tests for ActionLogMiddleware"""

    def test_process_request_sets_thread_local(self):
        """Test that process_request sets the request in thread locals"""
        from helpers.middlewares import ActionLogMiddleware, _thread_locals

        middleware = ActionLogMiddleware(get_response=Mock())
        mock_request = Mock()

        middleware.process_request(mock_request)

        assert _thread_locals.request == mock_request

        del _thread_locals.request

    def test_process_response_removes_thread_local(self):
        """Test that process_response removes request from thread locals"""
        from helpers.middlewares import ActionLogMiddleware, _thread_locals

        middleware = ActionLogMiddleware(get_response=Mock())
        mock_request = Mock()
        mock_response = Mock()

        _thread_locals.request = mock_request

        result = middleware.process_response(mock_request, mock_response)

        assert not hasattr(_thread_locals, "request")
        assert result == mock_response

    def test_process_response_handles_missing_request(self):
        """Test that process_response handles when request wasn't set"""
        from helpers.middlewares import ActionLogMiddleware, _thread_locals

        middleware = ActionLogMiddleware(get_response=Mock())

        if hasattr(_thread_locals, "request"):
            del _thread_locals.request

        mock_response = Mock()

        result = middleware.process_response(Mock(), mock_response)

        assert result == mock_response

    def test_process_exception_removes_thread_local(self):
        """Test that process_exception removes request from thread locals"""
        from helpers.middlewares import ActionLogMiddleware, _thread_locals

        middleware = ActionLogMiddleware(get_response=Mock())
        mock_request = Mock()

        _thread_locals.request = mock_request

        middleware.process_exception(mock_request, Exception("test"))

        assert not hasattr(_thread_locals, "request")

    def test_process_exception_handles_missing_request(self):
        """Test that process_exception handles when request wasn't set"""
        from helpers.middlewares import ActionLogMiddleware, _thread_locals

        middleware = ActionLogMiddleware(get_response=Mock())

        if hasattr(_thread_locals, "request"):
            del _thread_locals.request

        middleware.process_exception(Mock(), Exception("test"))


class TestRatelimitExceededView(TestCase):
    """Tests for ratelimit_exceeded_view function"""

    @patch("helpers.middlewares.sentry_sdk")
    def test_ratelimit_exceeded_view_with_ratelimited_exception(self, mock_sentry):
        """Test handling of Ratelimited exception"""
        from helpers.middlewares import ratelimit_exceeded_view

        mock_request = Mock()
        exception = Ratelimited()

        response = ratelimit_exceeded_view(mock_request, exception)

        mock_sentry.capture_exception.assert_called_once_with(exception)
        assert response.status_code == 429
        assert response.content.decode("utf-8") == '{"detail": "Too many requests"}'

    @patch("helpers.middlewares.sentry_sdk")
    def test_ratelimit_exceeded_view_with_other_exception(self, mock_sentry):
        """Test handling of non-Ratelimited exception"""
        from helpers.middlewares import ratelimit_exceeded_view

        mock_request = Mock()
        exception = ValueError("Some error")

        response = ratelimit_exceeded_view(mock_request, exception)

        mock_sentry.capture_exception.assert_not_called()
        assert response.status_code == 403
        assert response.content.decode("utf-8") == '{"detail": "Forbidden"}'


class TestRawRequestBodyMiddleware(TestCase):
    """Tests for RawRequestBodyMiddleware"""

    def test_raw_request_body_middleware_init(self):
        """Test middleware initialization"""
        from helpers.middlewares import RawRequestBodyMiddleware

        mock_get_response = Mock()
        middleware = RawRequestBodyMiddleware(mock_get_response)

        assert middleware.get_response == mock_get_response

    def test_raw_request_body_middleware_caches_body_for_multiple_daily_report(self):
        """Test that raw body is cached for MultipleDailyReport POST requests"""
        from helpers.middlewares import RawRequestBodyMiddleware

        mock_get_response = Mock(return_value=Mock())
        middleware = RawRequestBodyMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.path = "/MultipleDailyReport/"
        mock_request.method = "POST"
        mock_request.content_type = "application/json"
        mock_request.body = b'{"data": "test"}'

        middleware(mock_request)

        assert mock_request.raw_body == b'{"data": "test"}'

    def test_raw_request_body_middleware_with_vnd_api_json(self):
        """Test with application/vnd.api+json content type"""
        from helpers.middlewares import RawRequestBodyMiddleware

        mock_get_response = Mock(return_value=Mock())
        middleware = RawRequestBodyMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.path = "/MultipleDailyReport/"
        mock_request.method = "POST"
        mock_request.content_type = "application/vnd.api+json"
        mock_request.body = b'{"data": "test"}'

        middleware(mock_request)

        assert mock_request.raw_body == b'{"data": "test"}'

    def test_raw_request_body_middleware_ignores_other_paths(self):
        """Test that middleware ignores requests to other paths"""
        from helpers.middlewares import RawRequestBodyMiddleware

        mock_get_response = Mock(return_value=Mock())
        middleware = RawRequestBodyMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.path = "/SomeOtherEndpoint/"
        mock_request.method = "POST"
        mock_request.content_type = "application/json"
        mock_request.body = b'{"data": "test"}'

        middleware(mock_request)

        assert mock_request.raw_body == b""

    def test_raw_request_body_middleware_ignores_get_requests(self):
        """Test that middleware ignores non-POST requests"""
        from helpers.middlewares import RawRequestBodyMiddleware

        mock_get_response = Mock(return_value=Mock())
        middleware = RawRequestBodyMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.path = "/MultipleDailyReport/"
        mock_request.method = "GET"
        mock_request.content_type = "application/json"

        middleware(mock_request)

        assert mock_request.raw_body == b""

    def test_raw_request_body_middleware_ignores_non_json_content_type(self):
        """Test that middleware ignores non-JSON content types"""
        from helpers.middlewares import RawRequestBodyMiddleware

        mock_get_response = Mock(return_value=Mock())
        middleware = RawRequestBodyMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.path = "/MultipleDailyReport/"
        mock_request.method = "POST"
        mock_request.content_type = "text/html"
        mock_request.body = b"<html></html>"

        middleware(mock_request)

        assert mock_request.raw_body == b""

    def test_raw_request_body_middleware_handles_exception(self):
        """Test that middleware handles exceptions when reading body"""
        from helpers.middlewares import RawRequestBodyMiddleware

        mock_get_response = Mock(return_value=Mock())
        middleware = RawRequestBodyMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.path = "/MultipleDailyReport/"
        mock_request.method = "POST"
        mock_request.content_type = "application/json"
        type(mock_request).body = property(Mock(side_effect=Exception("Error")))

        middleware(mock_request)

        assert mock_request.raw_body == b""

    def test_raw_request_body_middleware_calls_get_response(self):
        """Test that middleware calls get_response"""
        from helpers.middlewares import RawRequestBodyMiddleware

        mock_response = Mock()
        mock_get_response = Mock(return_value=mock_response)
        middleware = RawRequestBodyMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.path = "/other/"
        mock_request.method = "GET"

        result = middleware(mock_request)

        mock_get_response.assert_called_once_with(mock_request)
        assert result == mock_response

    def test_raw_request_body_middleware_caches_body_for_patch_with_vnd_api_json(self):
        """Test that raw body is cached for PATCH requests with application/vnd.api+json"""
        from helpers.middlewares import RawRequestBodyMiddleware

        mock_get_response = Mock(return_value=Mock())
        middleware = RawRequestBodyMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.path = "/MultipleDailyReport/123e4567-e89b-12d3-a456-426614174000/"
        mock_request.method = "PATCH"
        mock_request.content_type = "application/vnd.api+json"
        mock_request.body = b'{"data": {"attributes": {"notes": "Updated notes"}}}'

        middleware(mock_request)

        assert (
            mock_request.raw_body
            == b'{"data": {"attributes": {"notes": "Updated notes"}}}'
        )

    def test_raw_request_body_middleware_ignores_patch_to_other_endpoints(self):
        """Test that middleware ignores PATCH requests to other endpoints"""
        from helpers.middlewares import RawRequestBodyMiddleware

        mock_get_response = Mock(return_value=Mock())
        middleware = RawRequestBodyMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.path = "/SomeOtherEndpoint/123e4567-e89b-12d3-a456-426614174000/"
        mock_request.method = "PATCH"
        mock_request.content_type = "application/json"
        mock_request.body = b'{"data": "test"}'

        middleware(mock_request)

        assert mock_request.raw_body == b""

    def test_raw_request_body_middleware_ignores_patch_without_trailing_slash(self):
        """Test that middleware ignores PATCH requests without trailing slash"""
        from helpers.middlewares import RawRequestBodyMiddleware

        mock_get_response = Mock(return_value=Mock())
        middleware = RawRequestBodyMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.path = "/MultipleDailyReport/123e4567-e89b-12d3-a456-426614174000"
        mock_request.method = "PATCH"
        mock_request.content_type = "application/json"
        mock_request.body = b'{"data": "test"}'

        middleware(mock_request)

        assert mock_request.raw_body == b""

    def test_raw_request_body_middleware_handles_patch_exception(self):
        """Test that middleware handles exceptions when reading PATCH body"""
        from helpers.middlewares import RawRequestBodyMiddleware

        mock_get_response = Mock(return_value=Mock())
        middleware = RawRequestBodyMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.path = "/MultipleDailyReport/123e4567-e89b-12d3-a456-426614174000/"
        mock_request.method = "PATCH"
        mock_request.content_type = "application/json"
        type(mock_request).body = property(Mock(side_effect=Exception("Error")))

        middleware(mock_request)

        assert mock_request.raw_body == b""
