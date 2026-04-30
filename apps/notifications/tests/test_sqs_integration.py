import json
from unittest.mock import Mock, patch

from django.test import TestCase

from apps.companies.models import Company
from apps.notifications.asynchronous import process_sqs_push_notification
from apps.notifications.models import Device, PushNotification
from apps.notifications.services import sqs_notification_service


class TestSQSIntegration(TestCase):
    """Test SQS integration for push notifications"""

    def setUp(self):
        super().setUp()
        self.company = Company.objects.create(name="Test Company")
        self.device = Device.objects.create(
            device_id="test_device", push_token="test_token"
        )

    @patch("apps.notifications.services.sqs_notification_service.publish_notification")
    def test_signal_publishes_to_sqs_on_create(self, mock_publish):
        """Test that creating a PushNotification triggers SQS publish"""
        mock_publish.return_value = True

        # Create a new notification
        notification = PushNotification.objects.create(
            message="Test notification", company=self.company, cleared=True
        )
        notification.devices.add(self.device)

        # Verify signal was called
        mock_publish.assert_called_once_with(
            notification_id=notification.id, company_id=str(self.company.uuid)
        )

    @patch("apps.notifications.services.sqs_notification_service.publish_notification")
    def test_signal_publishes_to_sqs_on_clear(self, mock_publish):
        """Test that clearing a PushNotification triggers SQS publish"""
        mock_publish.return_value = True

        # Create notification without clearing
        notification = PushNotification.objects.create(
            message="Test notification", company=self.company, cleared=False
        )
        notification.devices.add(self.device)

        # Reset mock after creation
        mock_publish.reset_mock()

        # Now clear the notification
        notification.cleared = True
        notification.save()

        # Verify signal was called
        mock_publish.assert_called_once_with(
            notification_id=notification.id, company_id=str(self.company.uuid)
        )

    @patch("apps.notifications.services.sqs_notification_service.publish_notification")
    def test_signal_skips_already_sent(self, mock_publish):
        """Test that signal skips already sent notifications"""
        # Create and immediately mark as sent
        notification = PushNotification.objects.create(
            message="Test notification", company=self.company, cleared=True, sent=True
        )
        notification.devices.add(self.device)

        # Verify publish was not called
        mock_publish.assert_not_called()

    def test_sqs_service_initialization(self):
        """Test SQS service initializes correctly"""
        self.assertIsNotNone(sqs_notification_service)
        # Note: In test environment, SQS might be disabled
        # so we can't assert much about the client

    @patch("apps.notifications.services.boto3.client")
    def test_sqs_service_publish_message(self, mock_boto_client):
        """Test SQS service publishes messages correctly"""
        # Mock SQS client
        mock_sqs = Mock()
        mock_boto_client.return_value = mock_sqs
        mock_sqs.send_message.return_value = {"MessageId": "test-message-id"}

        # Enable SQS for this test
        with patch.object(sqs_notification_service, "enabled", True):
            with patch.object(sqs_notification_service, "sqs_client", mock_sqs):
                success = sqs_notification_service.publish_notification(
                    notification_id=123, company_id=456
                )

        self.assertTrue(success)
        mock_sqs.send_message.assert_called_once()

        # Verify message content
        call_args = mock_sqs.send_message.call_args
        message_body = json.loads(call_args[1]["MessageBody"])
        self.assertEqual(message_body["notification_id"], 123)
        self.assertEqual(message_body["company_id"], 456)

    @patch(
        "apps.notifications.strategies.firebase.FirebaseNotificationService.initialize"
    )
    @patch("apps.notifications.strategies.firebase.FirebaseNotificationService.send")
    def test_process_sqs_notification(self, mock_firebase_send, mock_firebase_init):
        """Test processing notifications from SQS events"""
        mock_firebase_init.return_value = "fake_token"
        mock_firebase_send.return_value = {"success": True}

        # Create notification
        notification = PushNotification.objects.create(
            message="Test notification",
            company=self.company,
            cleared=True,
            extra_payload='{"test": "data"}',
        )
        notification.devices.add(self.device)

        # Create mock SQS event
        sqs_event = {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "notification_id": notification.id,
                            "company_id": str(self.company.uuid),
                        }
                    )
                }
            ]
        }

        # Process the event
        result = process_sqs_push_notification(sqs_event, {})

        # Verify response
        self.assertEqual(result["statusCode"], 200)
        response_body = json.loads(result["body"])
        self.assertEqual(response_body["processed"], 1)
        self.assertEqual(response_body["failed"], 0)

        # Verify notification was marked as sent
        notification.refresh_from_db()
        self.assertTrue(notification.sent)
        self.assertFalse(notification.in_progress)

    @patch(
        "apps.notifications.strategies.firebase.FirebaseNotificationService.initialize"
    )
    def test_process_sqs_notification_not_found(self, mock_firebase_init):
        """Test processing SQS event for non-existent notification"""
        mock_firebase_init.return_value = "fake_token"

        # Create mock SQS event with non-existent notification ID
        sqs_event = {
            "Records": [
                {
                    "body": json.dumps(
                        {"notification_id": 99999, "company_id": str(self.company.uuid)}
                    )
                }
            ]
        }

        # Process the event
        result = process_sqs_push_notification(sqs_event, {})

        # Verify response
        self.assertEqual(result["statusCode"], 200)
        response_body = json.loads(result["body"])
        self.assertEqual(response_body["processed"], 0)
        self.assertEqual(response_body["failed"], 1)

    @patch(
        "apps.notifications.strategies.firebase.FirebaseNotificationService.initialize"
    )
    def test_process_sqs_notification_already_sent(self, mock_firebase_init):
        """Test processing SQS event for already sent notification (idempotency)"""
        mock_firebase_init.return_value = "fake_token"

        # Create notification that's already sent
        notification = PushNotification.objects.create(
            message="Test notification",
            company=self.company,
            cleared=True,
            sent=True,
            extra_payload='{"test": "data"}',
        )
        notification.devices.add(self.device)

        # Create mock SQS event
        sqs_event = {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "notification_id": notification.id,
                            "company_id": str(self.company.uuid),
                        }
                    )
                }
            ]
        }

        # Process the event
        result = process_sqs_push_notification(sqs_event, {})

        # Verify response - should count as processed (idempotent)
        self.assertEqual(result["statusCode"], 200)
        response_body = json.loads(result["body"])
        self.assertEqual(response_body["processed"], 1)
        self.assertEqual(response_body["failed"], 0)

    def test_sqs_service_get_queue_metrics(self):
        """Test getting queue metrics"""
        with patch.object(sqs_notification_service, "enabled", False):
            metrics = sqs_notification_service.get_queue_metrics()
            self.assertEqual(metrics, {})

    @patch("apps.notifications.services.boto3.client")
    def test_sqs_service_get_queue_metrics_with_client(self, mock_boto_client):
        """Test getting queue metrics with active client"""
        # Mock SQS client
        mock_sqs = Mock()
        mock_boto_client.return_value = mock_sqs
        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {
                "ApproximateNumberOfMessages": "5",
                "ApproximateNumberOfMessagesNotVisible": "2",
                "ApproximateNumberOfMessagesDelayed": "0",
            }
        }

        # Enable SQS for this test
        with patch.object(sqs_notification_service, "enabled", True):
            with patch.object(sqs_notification_service, "sqs_client", mock_sqs):
                metrics = sqs_notification_service.get_queue_metrics()

        expected = {
            "messages_in_queue": 5,
            "messages_in_flight": 2,
            "messages_delayed": 0,
        }
        self.assertEqual(metrics, expected)
