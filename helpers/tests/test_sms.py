from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

from helpers.sms import send_sms

pytestmark = pytest.mark.django_db


class TestSendSms(TestCase):
    """Tests for send_sms function"""

    @patch("helpers.sms.TextMessageService")
    @patch("helpers.sms.credentials")
    def test_send_sms_success(self, mock_credentials, mock_text_service_class):
        """Test successful SMS sending"""
        # Setup mocks
        mock_credentials.COMTELE_API_KEY = "test-api-key-123"
        mock_service_instance = Mock()
        mock_text_service_class.return_value = mock_service_instance

        # Test data
        sender = "TestSender"
        content = "Test message content"
        receivers = ["5511999999999", "5511888888888"]

        # Call function
        send_sms(sender, content, receivers)

        # Verify TextMessageService was initialized with API key
        mock_text_service_class.assert_called_once_with("test-api-key-123")

        # Verify send method was called with correct parameters
        mock_service_instance.send.assert_called_once_with(sender, content, receivers)

    @patch("helpers.sms.TextMessageService")
    @patch("helpers.sms.credentials")
    def test_send_sms_single_receiver(self, mock_credentials, mock_text_service_class):
        """Test SMS sending to single receiver"""
        # Setup mocks
        mock_credentials.COMTELE_API_KEY = "api-key"
        mock_service_instance = Mock()
        mock_text_service_class.return_value = mock_service_instance

        # Test data
        sender = "Kartado"
        content = "Your code is 123456"
        receivers = ["5511987654321"]

        # Call function
        send_sms(sender, content, receivers)

        # Verify
        mock_service_instance.send.assert_called_once_with(sender, content, receivers)

    @patch("helpers.sms.TextMessageService")
    @patch("helpers.sms.credentials")
    def test_send_sms_empty_content(self, mock_credentials, mock_text_service_class):
        """Test SMS sending with empty content"""
        # Setup mocks
        mock_credentials.COMTELE_API_KEY = "api-key"
        mock_service_instance = Mock()
        mock_text_service_class.return_value = mock_service_instance

        # Test data
        sender = "Kartado"
        content = ""
        receivers = ["5511999999999"]

        # Call function
        send_sms(sender, content, receivers)

        # Should still call send even with empty content
        mock_service_instance.send.assert_called_once_with(sender, content, receivers)

    @patch("helpers.sms.TextMessageService")
    @patch("helpers.sms.credentials")
    def test_send_sms_multiple_receivers(
        self, mock_credentials, mock_text_service_class
    ):
        """Test SMS sending to multiple receivers"""
        # Setup mocks
        mock_credentials.COMTELE_API_KEY = "test-key"
        mock_service_instance = Mock()
        mock_text_service_class.return_value = mock_service_instance

        # Test data with multiple receivers
        sender = "Alert"
        content = "Emergency notification"
        receivers = [
            "5511111111111",
            "5522222222222",
            "5533333333333",
            "5544444444444",
        ]

        # Call function
        send_sms(sender, content, receivers)

        # Verify all receivers were passed
        mock_service_instance.send.assert_called_once_with(sender, content, receivers)
