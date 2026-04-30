import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from dateutil.relativedelta import relativedelta
from django.utils import timezone

from apps.notifications.asynchronous import (
    delete_old_queued_push,
    send_queued_notifications,
    send_queued_push_notifications,
)
from apps.notifications.models import Device, PushNotification, UserPush
from apps.users.models import User
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestPushNotification(TestBase):
    model = "PushNotification"

    @pytest.mark.django_db
    @patch("sentry_sdk.capture_exception")
    @patch(
        "apps.notifications.strategies.firebase.FirebaseNotificationService.initialize"
    )
    def test_send_queued_push_notifications(
        self, mock_firebase_init, mock_capture_exception
    ):
        # Mock Firebase initialization
        mock_firebase_init.return_value = "fake_firebase_token"

        device = Device.objects.create(push_token="fake_device_token")
        # Create notifications in database
        push1 = PushNotification.objects.create(
            sent=False,
            in_progress=False,
            cleared=True,
            extra_payload=json.dumps({"message": "Test push 1"}),
        )

        push2 = PushNotification.objects.create(
            sent=False,
            in_progress=False,
            cleared=True,
            extra_payload=json.dumps({"message": "Test push 2"}),
        )

        # Create simulated devices
        push1.devices.add(device)
        push2.devices.add(device)

        # Call the function to be tested
        send_queued_push_notifications()

        # Verify that Firebase was initialized
        mock_firebase_init.assert_called_once()

        # Verify that notifications were sent
        assert PushNotification.objects.get(pk=push1.pk).sent is True
        assert PushNotification.objects.get(pk=push2.pk).sent is True

        # Verify that notifications are no longer in progress
        assert PushNotification.objects.get(pk=push1.pk).in_progress is False
        assert PushNotification.objects.get(pk=push2.pk).in_progress is False

        # Verify that exception function was not called (no error expected)
        mock_capture_exception.assert_not_called()

    def test_send_queued_notifications_without_Notification_subclass(self):
        """
        Tests that TypeError is raised when a class that is not a subclass of Notification is passed
        """
        with pytest.raises(TypeError) as exc_info:
            send_queued_notifications(Device)

        # Verify the exception message
        expected_message = "Device must be a subclass of Notification."
        assert str(exc_info.value) == expected_message

    def test_send_queued_notifications_without_model_class(self):
        """
        Tests that TypeError is raised when a non-class type is passed instead of a class
        """
        with pytest.raises(TypeError) as exc_info:
            send_queued_notifications("Test")

        # Verify the exception message
        expected_message = "Expected a class type, got instance of 'str'."
        assert str(exc_info.value) == expected_message


class TestDeleteOldQueuedPush(TestBase):
    model = "PushNotification"

    @pytest.mark.django_db
    @patch("logging.info")
    @patch("psycopg2.connect")
    def test_delete_old_queued_push_without_old_notifications(
        self, mock_connect, mock_logging
    ):
        """
        Tests the case where there are no old notifications to delete
        """
        # Mock connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Create recent notifications (less than 6 months)
        recent_notification = PushNotification.objects.create(
            sent=True,
            in_progress=False,
            cleared=True,
            extra_payload=json.dumps({"message": "Recent notification"}),
            created_at=timezone.now() - timedelta(days=30),  # 1 month ago
        )

        # Execute function
        delete_old_queued_push()

        # Verify that recent notification was not deleted
        assert PushNotification.objects.filter(pk=recent_notification.pk).exists()

        # Verify that connection was established and closed
        mock_connect.assert_called_once()
        mock_conn.close.assert_called_once()

        # Verify that log was called with 0 objects deleted
        mock_logging.assert_called()
        log_message = mock_logging.call_args[0][0]
        assert "0 objects deleted" in log_message

    @pytest.mark.django_db
    @patch("logging.info")
    @patch("psycopg2.connect")
    def test_delete_old_queued_push(self, mock_connect, mock_logging):
        """
        Tests the case where there are old notifications to delete with UserPush relationship
        """
        # Mock connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Create a test user
        test_user = User.objects.create(
            username="testuser",
            email="test@example.com",
        )

        # Create old notification (more than 6 months)
        seven_months_ago = timezone.now() - relativedelta(months=7)
        old_notification = PushNotification.objects.create(
            sent=True,
            in_progress=False,
            cleared=True,
            extra_payload=json.dumps({"message": "Old notification"}),
            created_at=seven_months_ago,
        )

        # Create UserPush related to the old notification
        UserPush.objects.create(
            user=test_user,
            push_message=old_notification,
            read=False,
        )

        # Execute function
        delete_old_queued_push()

        # Verify that SQL DELETE statements were executed for both UserPush and PushNotification
        # Should have at least 3 calls: DELETE UserPush, DELETE from ManyToMany table, DELETE PushNotification
        assert mock_cursor.execute.call_count >= 3

        # Verify that connection was established and closed
        mock_connect.assert_called_once()
        mock_conn.close.assert_called_once()

        # Verify that log was called
        mock_logging.assert_called()

        # Verify the cursor execute calls include UserPush deletion
        execute_calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
        user_push_delete_found = any(
            "DELETE FROM notifications_userpush" in call for call in execute_calls
        )
        assert user_push_delete_found, "UserPush deletion query should be executed"
