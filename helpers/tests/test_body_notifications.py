import uuid
from unittest import TestCase
from unittest.mock import MagicMock, patch

from apps.users.models import User
from helpers.notifications import create_push_notifications, create_single_notification


class TestBodyNotification(TestCase):
    @patch("helpers.notifications.bulk_create_with_history")
    @patch("helpers.notifications.UserPush")
    @patch("helpers.notifications.Device")
    @patch("helpers.notifications.PushNotification")
    @patch("helpers.notifications.UserInCompany")
    @patch("helpers.notifications.render_to_string")
    @patch("helpers.notifications.QueuedEmail")
    @patch("django.db.transaction.atomic")
    @patch("helpers.histories.bulk_update")
    def test_create_single_notification_with_body(
        self,
        mock_bulk_update,
        mock_atomic,
        mock_queued_email,
        mock_render,
        mock_user_in_company,
        mock_push_notification,
        mock_device,
        mock_user_push,
        mock_bulk_history,
    ):

        mock_render.return_value = "rendered template"
        mock_atomic.return_value.__enter__ = MagicMock()
        mock_atomic.return_value.__exit__ = MagicMock()

        mock_user = MagicMock(spec=User)
        mock_user.pk = uuid.uuid4()

        mock_company = MagicMock(spec=["pk"])
        mock_company.pk = uuid.uuid4()

        user_company_instance = MagicMock(is_active=True)
        mock_user_in_company.objects.filter.return_value.first.return_value = (
            user_company_instance
        )

        mock_meta = MagicMock()
        mock_meta.simple_history_manager_attribute = "history"
        mock_queued_email._meta = mock_meta
        mock_queued_email.history = MagicMock()
        mock_queued_email.objects = MagicMock()

        queue_instance = MagicMock()
        queue_instance.pk = uuid.uuid4()
        mock_queued_email.objects.create.return_value = queue_instance
        mock_queued_email.objects.filter.return_value = [queue_instance]

        mock_bulk_history.return_value = [queue_instance]

        create_single_notification(
            user=mock_user,
            company=mock_company,
            context={"title": "Test Title", "message": "Test Message"},
            template_path="test/template",
            push=True,
            body="Test Body",
        )

        mock_push_notification.objects.create.assert_called_once()
        kwargs = mock_push_notification.objects.create.call_args[1]
        assert kwargs["body"] == "Test Body"

    @patch("apps.notifications.models.Device")
    def test_device_send_propagates_body_to_firebase(self, mock_device_class):

        push_notification = MagicMock()
        push_notification.body = "Test Body"

        device = mock_device_class()
        device.firebase_token = "test-token"

        device.send(
            push_message=push_notification, firebase_token=device.firebase_token
        )

        device.send.assert_called_once_with(
            push_message=push_notification, firebase_token=device.firebase_token
        )
        assert push_notification.body == "Test Body"

    @patch("helpers.notifications.PushNotification")
    def test_notification_with_malformed_extra_payload(self, mock_push_notification):

        push_instance = MagicMock()
        push_instance.extra_payload = "{'invalid': json"

        def process_side_effect(*args, **kwargs):
            push_instance.extra_payload = {}
            return None

        push_instance.process.side_effect = process_side_effect
        mock_push_notification.objects.create.return_value = push_instance

        push_instance.process(firebase_token="test-token")

        assert push_instance.extra_payload == {}

    @patch("helpers.notifications.PushNotification")
    def test_notification_with_missing_extra_payload(self, mock_push_notification):

        push_instance = MagicMock()
        push_instance.extra_payload = None

        def process_side_effect(*args, **kwargs):
            push_instance.extra_payload = {}
            return None

        push_instance.process.side_effect = process_side_effect
        mock_push_notification.objects.create.return_value = push_instance

        push_instance.process(firebase_token="test-token")

        assert push_instance.extra_payload == {}

    @patch("helpers.notifications.UserPush")
    @patch("helpers.notifications.Device")
    @patch("helpers.notifications.PushNotification")
    def test_create_push_notifications_with_and_without_body(
        self, mock_push_notification, mock_device, mock_user_push
    ):

        mock_users = [MagicMock(spec=User) for _ in range(2)]
        for user in mock_users:
            user.pk = uuid.uuid4()

        mock_company = MagicMock(spec=["pk"])
        mock_company.pk = uuid.uuid4()
        mock_instance = MagicMock()
        mock_device.objects.filter.return_value = []

        mock_user_push.objects.create.return_value = MagicMock()

        create_push_notifications(
            users=mock_users,
            message="Test Message",
            company=mock_company,
            instance=mock_instance,
            body="Test Body",
        )

        assert mock_push_notification.objects.create.call_count == 2
        for call in mock_push_notification.objects.create.call_args_list:
            assert call[1]["body"] == "Test Body"

        mock_push_notification.reset_mock()
        mock_user_push.reset_mock()

        create_push_notifications(
            users=mock_users,
            message="Test Message",
            company=mock_company,
            instance=mock_instance,
        )

        assert mock_push_notification.objects.create.call_count == 2
        for call in mock_push_notification.objects.create.call_args_list:
            assert call[1].get("body") is None

    @patch("helpers.notifications.UserPush")
    @patch("helpers.notifications.Device")
    @patch("helpers.notifications.PushNotification")
    def test_notification_persistence(
        self, mock_push_notification, mock_device, mock_user_push
    ):

        push_instance = MagicMock()
        mock_push_notification.objects.create.return_value = push_instance
        push_instance.save = MagicMock()

        mock_instance = MagicMock()
        mock_device.objects.filter.return_value = []

        mock_user = MagicMock(spec=User)
        mock_user.pk = uuid.uuid4()

        mock_company = MagicMock(spec=["pk"])
        mock_company.pk = uuid.uuid4()

        mock_user_push.objects.create.return_value = MagicMock()

        create_push_notifications(
            users=[mock_user],
            message="Test Message",
            company=mock_company,
            instance=mock_instance,
            body="Test Body",
        )

        mock_push_notification.objects.create.assert_called_once()
        push_instance.save.assert_called_once()
