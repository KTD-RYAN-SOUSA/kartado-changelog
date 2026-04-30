import json
import uuid
from unittest.mock import Mock, patch

import requests
from django.test import TestCase

from apps.daily_reports.services import send_daily_report_file_to_webhook


class TestSendDailyReportFileToWebhook(TestCase):
    def setUp(self):
        self.company_uuid = uuid.uuid4()
        self.instance_uuid = uuid.uuid4()
        self.mock_instance = Mock()
        self.mock_instance.multiple_daily_report.company.uuid = self.company_uuid
        self.mock_instance.multiple_daily_report.company.metadata = {
            "n8n_daily_report_file_webhook_url": "http://fake-webhook.com/test"
        }
        self.mock_instance.uuid = self.instance_uuid

        self.raw_body = json.dumps(
            {"data": {"attributes": {"some_key": "some_value"}}}
        ).encode("utf-8")

    @patch("apps.daily_reports.services.requests.post")
    @patch("apps.daily_reports.services.sentry_sdk")
    @patch("apps.daily_reports.serializers.MultipleDailyReportFileSerializer")
    def test_send_daily_report_file_to_webhook_success(
        self, mock_serializer, mock_sentry, mock_post
    ):
        """
        Tests that the webhook is sent successfully.
        """
        mock_serializer.return_value.data = {"upload": "http://fake-upload-url.com"}
        mock_post.return_value.raise_for_status = Mock()

        send_daily_report_file_to_webhook(
            self.mock_instance,
            self.raw_body,
            self.mock_instance.multiple_daily_report.company,
        )

        mock_post.assert_called_once()
        called_args, called_kwargs = mock_post.call_args
        self.assertEqual(called_args[0], "http://fake-webhook.com/test")

        expected_payload = {
            "data": {
                "attributes": {
                    "some_key": "some_value",
                    "uploadGetUrl": "http://fake-upload-url.com",
                    "companyId": str(self.company_uuid),
                    "uuid": str(self.instance_uuid),
                }
            }
        }
        self.assertEqual(called_kwargs["json"], expected_payload)
        mock_sentry.capture_exception.assert_not_called()

    @patch("apps.daily_reports.services.requests.post")
    @patch("apps.daily_reports.services.sentry_sdk")
    @patch("apps.daily_reports.serializers.MultipleDailyReportFileSerializer")
    def test_requests_exception(self, mock_serializer, mock_sentry, mock_post):
        """
        Tests that an exception is logged to Sentry if requests.post fails.
        """
        mock_serializer.return_value.data = {"upload": "http://fake-upload-url.com"}
        exception = requests.RequestException("Test error")
        mock_post.side_effect = exception

        send_daily_report_file_to_webhook(
            self.mock_instance,
            self.raw_body,
            self.mock_instance.multiple_daily_report.company,
        )

        mock_post.assert_called_once()
        mock_sentry.capture_exception.assert_called_once_with(exception)

    @patch("apps.daily_reports.services.requests.post")
    @patch("apps.daily_reports.services.sentry_sdk")
    def test_webhook_url_not_configured(self, mock_sentry, mock_post):
        """
        Tests that a message is logged to Sentry if the webhook URL is not configured.
        """
        # Remove URL do metadata para simular ausência
        self.mock_instance.multiple_daily_report.company.metadata = {}

        send_daily_report_file_to_webhook(
            self.mock_instance,
            self.raw_body,
            self.mock_instance.multiple_daily_report.company,
        )

        mock_post.assert_not_called()
        mock_sentry.capture_message.assert_called_once_with(
            "N8N_DAILY_REPORT_FILE_WEBHOOK_URL não configurada",
            "warning",
        )

    @patch("apps.daily_reports.services.requests.post")
    @patch("apps.daily_reports.services.sentry_sdk")
    def test_invalid_json(self, mock_sentry, mock_post):
        """
        Tests that an exception is logged to Sentry if the raw_body is not valid JSON.
        """
        invalid_raw_body = b"this is not json"

        send_daily_report_file_to_webhook(
            self.mock_instance,
            invalid_raw_body,
            self.mock_instance.multiple_daily_report.company,
        )

        mock_post.assert_not_called()
        mock_sentry.capture_exception.assert_called_once()
        self.assertIsInstance(
            mock_sentry.capture_exception.call_args[0][0], json.JSONDecodeError
        )
