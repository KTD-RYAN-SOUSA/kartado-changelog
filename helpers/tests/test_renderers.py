from unittest.mock import Mock, patch

from django.test import TestCase

from helpers.renderers import LimitedSizeJSONRenderer


class TestLimitedSizeJSONRenderer(TestCase):
    """Tests for LimitedSizeJSONRenderer class"""

    def setUp(self):
        """Set up test renderer instance"""
        self.renderer = LimitedSizeJSONRenderer()

    def test_render_inheritance_from_json_renderer(self):
        """Test that LimitedSizeJSONRenderer properly inherits from JSONRenderer"""
        from helpers.json_parser import JSONRenderer

        # Verify inheritance
        self.assertTrue(issubclass(LimitedSizeJSONRenderer, JSONRenderer))

        # Verify it has the render method
        self.assertTrue(hasattr(self.renderer, "render"))
        self.assertTrue(callable(getattr(self.renderer, "render")))

    @patch("helpers.renderers.sys.getsizeof")
    @patch("helpers.renderers.logging.error")
    def test_render_small_data_no_logging(self, mock_logging_error, mock_getsizeof):
        """Test render with small data that doesn't trigger 6MB limit"""
        # Setup: data under 6MB limit
        test_data = {"message": "test"}
        mock_getsizeof.return_value = 1024  # 1KB - well under limit

        # Mock the parent render method
        with patch.object(
            self.renderer.__class__.__bases__[0], "render"
        ) as mock_parent_render:
            mock_parent_render.return_value = b'{"message": "test"}'

            result = self.renderer.render(test_data)

            # Verify parent render was called
            mock_parent_render.assert_called_once_with(test_data, None, None)

            # Verify no error logging occurred
            mock_logging_error.assert_not_called()

            # Verify normal result is returned
            self.assertEqual(result, b'{"message": "test"}')

    @patch("helpers.renderers.sys.getsizeof")
    @patch("helpers.renderers.logging.error")
    def test_render_exceeds_limit_with_request_context(
        self, mock_logging_error, mock_getsizeof
    ):
        """Test render with data exceeding 6MB limit with request context"""
        # Setup: data exceeding 6MB limit
        test_data = {"large": "data"}
        SIX_MB_IN_BYTES = 6 * 1024 * 1024
        mock_getsizeof.return_value = SIX_MB_IN_BYTES + 1000  # Over limit

        # Mock request context
        mock_user = Mock()
        mock_user.get_full_name.return_value = "Test User"
        mock_request = Mock()
        mock_request.path = "/api/test"
        mock_request.user = mock_user
        mock_request.method = "GET"

        renderer_context = {"request": mock_request}

        # Mock the parent render method
        with patch.object(
            self.renderer.__class__.__bases__[0], "render"
        ) as mock_parent_render:
            mock_parent_render.return_value = b'{"large": "data"}'

            result = self.renderer.render(test_data, renderer_context=renderer_context)

            # Verify parent render was called
            mock_parent_render.assert_called_once_with(
                test_data, None, renderer_context
            )

            # Verify error logging occurred with correct message
            expected_log_message = "LimitedSizeJSONRenderer: GET /api/test by user 'Test User' has reached the 6MB body size limit"
            mock_logging_error.assert_called_once_with(expected_log_message)

            # Verify error response is returned
            expected_error_response = b'{"errors":[{"detail":"kartado.error.api.request_payload_cannot_exceed_six_megabytes"}]}'
            self.assertEqual(result, expected_error_response)
