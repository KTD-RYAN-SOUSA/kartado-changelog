from unittest.mock import Mock, patch

import pytest
from django.test import TestCase
from rest_framework import status

from apps.notifications.models import PushNotification, UserPush
from apps.notifications.views import SQSMonitoringView, SQSTestView
from apps.users.models import User
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class SQSMonitoringViewTestCase(TestCase):
    def setUp(self):
        self.view = SQSMonitoringView()
        self.view.request = Mock()

    @patch("apps.notifications.services.sqs_notification_service.get_queue_metrics")
    @patch("apps.notifications.models.PushNotification.objects.filter")
    def test_get_success(self, mock_notification_filter, mock_get_metrics):
        """
        Tests successful GET request on SQSMonitoringView
        """
        # Mock SQS metrics
        mock_get_metrics.return_value = {
            "messages_in_queue": 5,
            "messages_in_flight": 2,
            "messages_delayed": 1,
        }

        # Mock database counts
        mock_filter_unsent = Mock()
        mock_filter_unsent.count.return_value = 3

        mock_filter_progress = Mock()
        mock_filter_progress.count.return_value = 1

        mock_filter_today = Mock()
        mock_filter_today.count.return_value = 10

        # Configure mock to return different values based on filter
        def filter_side_effect(**kwargs):
            if kwargs.get("sent") is False and kwargs.get("cleared") is True:
                return mock_filter_unsent
            elif kwargs.get("sent") is False and kwargs.get("in_progress") is True:
                return mock_filter_progress
            elif kwargs.get("created_at__date"):
                return mock_filter_today
            return Mock()

        mock_notification_filter.side_effect = filter_side_effect

        response = self.view.get(self.view.request)

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("sqs_status", response.data)
        self.assertIn("queue_metrics", response.data)
        self.assertIn("database_metrics", response.data)
        self.assertIn("timestamp", response.data)

        # Verify metrics
        self.assertEqual(response.data["queue_metrics"]["messages_in_queue"], 5)
        self.assertEqual(response.data["database_metrics"]["unsent_notifications"], 3)

    @patch("apps.notifications.services.sqs_notification_service.get_queue_metrics")
    def test_get_exception_handling(self, mock_get_metrics):
        """
        Tests exception handling in SQSMonitoringView
        """
        mock_get_metrics.side_effect = Exception("SQS Error")

        response = self.view.get(self.view.request)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"], "SQS Error")


class SQSTestViewTestCase(TestCase):
    def setUp(self):
        self.view = SQSTestView()
        self.view.request = Mock()
        self.view.request.data = {"notification_id": 123}

    @patch("apps.notifications.models.PushNotification.objects.get")
    @patch("apps.notifications.services.sqs_notification_service.publish_notification")
    def test_post_success(self, mock_publish, mock_notification_get):
        """
        Tests successful POST request on SQSTestView
        """
        # Mock notification
        mock_notification = Mock()
        mock_notification.id = 123
        mock_notification.company.id = 456
        mock_notification_get.return_value = mock_notification

        # Mock publish
        mock_publish.return_value = True

        response = self.view.post(self.view.request)

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["notification_id"], 123)
        self.assertEqual(response.data["message"], "Test publish completed")

        mock_publish.assert_called_once_with(notification_id=123, company_id=456)

    def test_post_missing_notification_id(self):
        """
        Tests POST request without notification_id
        """
        self.view.request.data = {}

        response = self.view.post(self.view.request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "notification_id is required")

    @patch("apps.notifications.models.PushNotification.objects.get")
    def test_post_notification_not_found(self, mock_notification_get):
        """
        Tests POST request with non-existent notification
        """
        from apps.notifications.models import PushNotification

        mock_notification_get.side_effect = PushNotification.DoesNotExist()

        response = self.view.post(self.view.request)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"], "PushNotification 123 not found")


class TestPushNotificationView(TestBase):
    model = "PushNotification"

    @pytest.fixture(autouse=True)
    def setup_push_notification_data(self, _initial):
        self.push_notification_cleared = PushNotification.objects.create(
            message="Test Notification Cleared",
            cleared=True,
            sent=True,
            company=self.company,
        )
        self.push_notification_not_cleared = PushNotification.objects.create(
            message="Test Notification Not Cleared",
            cleared=False,
            sent=False,
            company=self.company,
        )

        self.other_user = User.objects.create(
            username="otheruser",
            email="other@test.com",
        )
        self.push_notification_other_user = PushNotification.objects.create(
            message="Test Notification Other User",
            cleared=True,
            sent=True,
            company=self.company,
        )

        UserPush.objects.create(
            user=self.user,
            push_message=self.push_notification_cleared,
            read=False,
        )
        UserPush.objects.create(
            user=self.user,
            push_message=self.push_notification_not_cleared,
            read=False,
        )
        UserPush.objects.create(
            user=self.other_user,
            push_message=self.push_notification_other_user,
            read=False,
        )

        self.push_notification_cleared.users.add(self.user)
        self.push_notification_not_cleared.users.add(self.user)
        self.push_notification_other_user.users.add(self.other_user)

    def test_get_queryset_filters_by_user(self, client):
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["meta"]["pagination"]["count"] == 1
        assert response.data["results"][0]["id"] == self.push_notification_cleared.pk

    def test_get_queryset_filters_cleared_only(self, client):
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        notification_ids = [item["id"] for item in response.data["results"]]
        assert self.push_notification_not_cleared.pk not in notification_ids

    def test_get_queryset_excludes_other_users(self, client):
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        notification_ids = [item["id"] for item in response.data["results"]]
        assert self.push_notification_other_user.pk not in notification_ids
