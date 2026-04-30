import json

import pytest
from rest_framework import status

from apps.notifications.models import PushNotification, UserPush
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestPushNotificationSerializer(TestBase):
    model = "PushNotification"

    @pytest.fixture(autouse=True)
    def setup_serializer_data(self, _initial):
        self.push_notification = PushNotification.objects.create(
            message="Test Notification for Serializer",
            cleared=True,
            sent=True,
            company=self.company,
        )

        self.user_push_read = UserPush.objects.create(
            user=self.user,
            push_message=self.push_notification,
            read=True,
        )

        self.push_notification.users.add(self.user)

        self.push_notification_no_userpush = PushNotification.objects.create(
            message="Test Notification No UserPush",
            cleared=True,
            sent=True,
            company=self.company,
        )
        self.push_notification_no_userpush.users.add(self.user)

    def test_get_read_returns_true_when_user_has_read(self, client):
        response = client.get(
            path="/{}/{}/".format(self.model, str(self.push_notification.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["read"] is True

    def test_get_read_returns_false_when_user_has_not_read(self, client):
        self.user_push_read.read = False
        self.user_push_read.save()

        response = client.get(
            path="/{}/{}/".format(self.model, str(self.push_notification.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["read"] is False

    def test_get_read_returns_false_when_no_userpush_exists(self, client):
        response = client.get(
            path="/{}/{}/".format(
                self.model, str(self.push_notification_no_userpush.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["read"] is False

    def test_update_read_status(self, client):
        data = {
            "data": {
                "type": "PushNotification",
                "id": str(self.push_notification.pk),
                "attributes": {"read": True},
            }
        }
        response = client.patch(
            path="/{}/{}/".format(self.model, str(self.push_notification.pk)),
            data=json.dumps(data),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        user_push = UserPush.objects.get(
            user=self.user, push_message=self.push_notification
        )
        assert user_push.read is True
