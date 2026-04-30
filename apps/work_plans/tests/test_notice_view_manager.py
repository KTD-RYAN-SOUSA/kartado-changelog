import json

import pytest
from rest_framework import status

from apps.work_plans.models import NoticeViewManager, UserNoticeView
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestNoticeViewManager(TestBase):
    model = "NoticeViewManager"

    def test_list_notice_view_managers(self, client):
        """Test listing NoticeViewManagers"""

        response = client.get(
            path=f"/{self.model}/?page_size=1&company={self.company.pk}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )
        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)

        assert content["meta"]["pagination"]["count"] == 2

    def test_retrieve_notice_view_manager(self, client):
        """Test retrieving a single NoticeViewManager. This will not be found
        since we return a empty queryset"""

        notice_manager = NoticeViewManager.objects.first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(notice_manager.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
            data={},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_notice_view_manager_not_allowed(self, client):
        """Test that POST requests are not allowed"""

        data = {
            "data": {
                "type": self.model,
                "attributes": {"notice": "test_notice", "views_quantity_limit": 5},
            }
        }

        response = client.post(
            path=f"/{self.model}/?company={self.company.pk}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
            data=data,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_must_display_action(self, client):
        """Test MustDisplay action for NoticeViewManager"""

        notice_manager = NoticeViewManager.objects.first()

        response = client.get(
            path=f"/{self.model}/MustDisplay/?company={self.company.pk}&notice={notice_manager.notice}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)

        # Verify UserNoticeView was created
        user_notice = UserNoticeView.objects.get(uuid=content["data"]["userNoticeView"])
        assert user_notice.user == self.user
        assert user_notice.company == self.company
        assert user_notice.notice_view_manager == notice_manager

    def test_notice_displayed_action(self, client):
        """Test NoticeDisplayed action for NoticeViewManager"""

        # Create UserNoticeView first
        notice_manager = NoticeViewManager.objects.first()
        user_notice = UserNoticeView.objects.create(
            company=self.company,
            notice_view_manager=notice_manager,
            user=self.user,
            views_quantity=0,
        )

        response = client.get(
            path=f"/{self.model}/NoticeDisplayed/?user_notice_view={user_notice.pk}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == status.HTTP_200_OK

        # Verify views_quantity was incremented
        user_notice.refresh_from_db()
        assert user_notice.views_quantity == 1
