from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

pytestmark = pytest.mark.django_db


class TestGetDisclaimer(TestCase):
    """Tests for get_disclaimer function"""

    def test_get_disclaimer_with_company_group(self):
        """Test getting disclaimer when company_group exists"""
        from helpers.notifications import get_disclaimer

        mock_company_group = Mock()
        mock_company_group.metadata = {"disclaimer": "Test Disclaimer"}
        mock_company_group.mobile_app = "TestApp"

        disclaimer, mobile_app = get_disclaimer(mock_company_group)

        assert disclaimer == "Test Disclaimer"
        assert mobile_app == "TestApp"

    def test_get_disclaimer_without_company_group(self):
        """Test getting disclaimer when company_group is None"""
        from helpers.notifications import get_disclaimer

        disclaimer, mobile_app = get_disclaimer(None)

        assert disclaimer == ""
        assert mobile_app == "undefined"

    def test_get_disclaimer_with_missing_disclaimer_key(self):
        """Test when company_group exists but has no disclaimer in metadata"""
        from helpers.notifications import get_disclaimer

        mock_company_group = Mock()
        mock_company_group.metadata = {}  # No disclaimer key
        mock_company_group.mobile_app = "TestApp"

        disclaimer, mobile_app = get_disclaimer(mock_company_group)

        assert disclaimer == ""
        assert mobile_app == "TestApp"


class TestCreateSingleNotification(TestCase):
    """Tests for create_single_notification function"""

    @patch("helpers.notifications.bulk_update_with_history")
    @patch("helpers.notifications.QueuedEmail")
    @patch("helpers.notifications.UserInCompany")
    @patch("helpers.notifications.render_to_string")
    @patch("helpers.notifications.settings")
    def test_create_single_notification_skips_inactive_user(
        self,
        mock_settings,
        mock_render,
        mock_uic_model,
        mock_qe_model,
        mock_bulk_update,
    ):
        """Test that notification is not created for inactive users"""
        from helpers.notifications import create_single_notification

        mock_user = Mock()
        mock_company = Mock()

        mock_uic = Mock()
        mock_uic.is_active = False
        mock_uic_model.objects.filter.return_value.first.return_value = mock_uic

        create_single_notification(
            user=mock_user,
            company=mock_company,
            context={"title": "Test"},
            template_path="test_template",
            push=False,
        )

        mock_qe_model.objects.create.assert_not_called()

    @patch("helpers.notifications.bulk_update_with_history")
    @patch("helpers.notifications.QueuedEmail")
    @patch("helpers.notifications.UserInCompany")
    @patch("helpers.notifications.render_to_string")
    @patch("helpers.notifications.settings")
    def test_create_single_notification_creates_email(
        self,
        mock_settings,
        mock_render,
        mock_uic_model,
        mock_qe_model,
        mock_bulk_update,
    ):
        """Test creating email notification"""
        from helpers.notifications import create_single_notification

        mock_settings.BACKEND_URL = "https://backend.test"
        mock_settings.FRONTEND_URL = "https://frontend.test"

        mock_user = Mock()
        mock_user.pk = "user-123"
        mock_company = Mock()

        mock_uic = Mock()
        mock_uic.is_active = True
        mock_uic_model.objects.filter.return_value.first.return_value = mock_uic

        mock_render.side_effect = ["<html>Email</html>", "Plain text email"]

        mock_queue = Mock()
        mock_qe_model.objects.create.return_value = mock_queue

        create_single_notification(
            user=mock_user,
            company=mock_company,
            context={"title": "Test Notification"},
            template_path="templates/notification",
            push=False,
        )

        mock_qe_model.objects.create.assert_called_once()
        mock_queue.send_to_users.add.assert_called_once_with(mock_user)
        assert mock_queue.cleared is True
        mock_bulk_update.assert_called_once()


class TestCreateNotifications(TestCase):
    """Tests for create_notifications function"""

    @patch("helpers.notifications.create_single_notification")
    @patch("helpers.notifications.get_disclaimer")
    def test_create_notifications_for_multiple_users(
        self, mock_get_disclaimer, mock_create_single
    ):
        """Test creating notifications for multiple users"""
        from helpers.notifications import create_notifications

        mock_get_disclaimer.return_value = ("Disclaimer text", "MobileApp")

        mock_user1 = Mock()
        mock_user2 = Mock()
        mock_company = Mock()
        mock_company.company_group = Mock()

        send_to = [mock_user1, mock_user2]
        context = {"title": "Test"}

        create_notifications(
            send_to=send_to,
            company=mock_company,
            context=context,
            template_path="test",
            push=True,
        )

        assert mock_create_single.call_count == 2

    @patch("helpers.notifications.create_single_notification")
    @patch("helpers.notifications.get_disclaimer")
    def test_create_notifications_removes_duplicates(
        self, mock_get_disclaimer, mock_create_single
    ):
        """Test that duplicate users are removed"""
        from helpers.notifications import create_notifications

        mock_get_disclaimer.return_value = ("Disclaimer", "App")

        mock_user = Mock()
        mock_company = Mock()
        mock_company.company_group = Mock()

        send_to = [mock_user, mock_user, mock_user]  # Same user 3 times

        create_notifications(
            send_to=send_to,
            company=mock_company,
            context={"title": "Test"},
            template_path="test",
        )

        assert mock_create_single.call_count == 1

    @patch("helpers.notifications.create_single_notification")
    @patch("helpers.notifications.get_disclaimer")
    def test_create_notifications_removes_none_users(
        self, mock_get_disclaimer, mock_create_single
    ):
        """Test that None values are filtered out"""
        from helpers.notifications import create_notifications

        mock_get_disclaimer.return_value = ("Disclaimer", "App")

        mock_user = Mock()
        mock_company = Mock()
        mock_company.company_group = Mock()

        send_to = [mock_user, None, None, mock_user]

        create_notifications(
            send_to=send_to,
            company=mock_company,
            context={"title": "Test"},
            template_path="test",
        )

        assert mock_create_single.call_count == 1


class TestCreatePushNotifications(TestCase):
    """Tests for create_push_notifications function"""

    @patch("helpers.notifications.UserPush")
    @patch("helpers.notifications.PushNotification")
    @patch("helpers.notifications.Device")
    def test_create_push_notifications_for_users(
        self, mock_device_model, mock_push_model, mock_user_push_model
    ):
        """Test creating push notifications for users"""
        from helpers.notifications import create_push_notifications

        mock_user1 = Mock()
        mock_user2 = Mock()
        mock_company = Mock()
        mock_instance = Mock()

        mock_device1 = Mock()
        mock_device2 = Mock()
        mock_device_model.objects.filter.side_effect = [
            [mock_device1],
            [mock_device2],
        ]

        mock_push1 = Mock()
        mock_push2 = Mock()
        mock_push_model.objects.create.side_effect = [mock_push1, mock_push2]

        create_push_notifications(
            users=[mock_user1, mock_user2],
            message="Test message",
            company=mock_company,
            instance=mock_instance,
            url="https://example.com",
            body="Test body",
        )

        assert mock_push_model.objects.create.call_count == 2
        assert mock_user_push_model.objects.create.call_count == 2

    @patch("helpers.notifications.UserPush")
    @patch("helpers.notifications.PushNotification")
    @patch("helpers.notifications.Device")
    def test_create_push_notifications_without_url(
        self, mock_device_model, mock_push_model, mock_user_push_model
    ):
        """Test creating push notification without URL"""
        from helpers.notifications import create_push_notifications

        mock_user = Mock()
        mock_company = Mock()
        mock_instance = Mock()

        mock_device_model.objects.filter.return_value = []
        mock_push = Mock()
        mock_push_model.objects.create.return_value = mock_push

        create_push_notifications(
            users=[mock_user],
            message="Test",
            company=mock_company,
            instance=mock_instance,
            url=None,
        )

        call_args = mock_push_model.objects.create.call_args
        assert "extra_payload" not in call_args[1]


class TestCreatePasswordNotifications(TestCase):
    """Tests for create_password_notifications function"""

    @patch("helpers.notifications.QueuedEmail")
    @patch("helpers.notifications.render_to_string")
    @patch("helpers.notifications.get_disclaimer")
    def test_create_password_notifications_with_disclaimer(
        self, mock_get_disclaimer, mock_render, mock_qe_model
    ):
        """Test creating password notification with disclaimer"""
        from helpers.notifications import create_password_notifications

        mock_get_disclaimer.return_value = ("Disclaimer", "App")
        mock_render.return_value = "Email content"

        mock_user = Mock()
        mock_company_group = Mock()

        mock_queue = Mock()
        mock_qe_model.objects.create.return_value = mock_queue

        create_password_notifications(
            send_to=mock_user,
            context={"title": "Password Reset"},
            template_path="templates/password",
            add_disclaimer=True,
            company_group=mock_company_group,
        )

        mock_get_disclaimer.assert_called_once_with(mock_company_group)
        mock_qe_model.objects.create.assert_called_once()
        call_args = mock_qe_model.objects.create.call_args
        assert call_args[1]["send_anyway"] is True

    @patch("helpers.notifications.QueuedEmail")
    @patch("helpers.notifications.render_to_string")
    def test_create_password_notifications_without_disclaimer(
        self, mock_render, mock_qe_model
    ):
        """Test creating password notification without disclaimer"""
        from helpers.notifications import create_password_notifications

        mock_render.return_value = "Email &amp; content"  # Has HTML entity

        mock_user = Mock()
        mock_queue = Mock()
        mock_qe_model.objects.create.return_value = mock_queue

        create_password_notifications(
            send_to=mock_user,
            context={"title": "Password Reset"},
            template_path="templates/password",
            add_disclaimer=False,
        )

        call_args = mock_qe_model.objects.create.call_args
        assert "&" in call_args[1]["content_plain_text"]

    @patch("helpers.notifications.QueuedEmail")
    @patch("helpers.notifications.render_to_string")
    def test_create_password_notifications_replaces_html_entities(
        self, mock_render, mock_qe_model
    ):
        """Test that HTML entities like &amp; are replaced"""
        from helpers.notifications import create_password_notifications

        mock_render.return_value = "Reset your password &amp; confirm"

        mock_user = Mock()
        mock_queue = Mock()
        mock_qe_model.objects.create.return_value = mock_queue

        create_password_notifications(
            send_to=mock_user,
            context={"title": "Test"},
            template_path="test",
        )

        call_args = mock_qe_model.objects.create.call_args
        assert "&amp;" not in call_args[1]["content_plain_text"]
        assert "&" in call_args[1]["content_plain_text"]
