import uuid
from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

from apps.templates.models import Template
from apps.templates.signals import post_delete_action, post_save_action, user_logged_in

pytestmark = pytest.mark.django_db


class UserLoggedInSignalTestCase(TestCase):
    def setUp(self):
        self.user = Mock()
        self.user.company_group = Mock()
        self.request = Mock()

    @patch("apps.templates.signals.ActionLog.objects.create")
    def test_user_logged_in_creates_action_log(self, mock_create):
        user_logged_in(sender=None, request=self.request, user=self.user)

        mock_create.assert_called_once()

    @patch("apps.templates.signals.ActionLog.objects.create")
    def test_user_logged_in_handles_exception(self, mock_create):
        mock_create.side_effect = Exception("Database error")

        user_logged_in(sender=None, request=self.request, user=self.user)

        mock_create.assert_called_once()


class PostSaveActionSignalTestCase(TestCase):
    def setUp(self):
        self.company_id = uuid.uuid4()
        self.user = Mock()
        self.user.company_group = Mock()
        self.user.is_anonymous = False

        self.instance = Mock()
        self.instance.pk = uuid.uuid4()
        self.instance.get_company_id = self.company_id

        self.request = Mock()
        self.request.method = "POST"

    @patch("apps.templates.signals.get_current_user")
    @patch("apps.templates.signals.get_current_request")
    @patch("apps.templates.signals.ActionLog.objects.create")
    @patch("apps.templates.signals.apps.get_models")
    def test_post_save_action_creates_action_log_on_create(
        self, mock_get_models, mock_create, mock_get_request, mock_get_user
    ):
        mock_get_request.return_value = self.request
        mock_get_user.return_value = self.user
        mock_get_models.return_value = [Template]

        post_save_action(
            sender=Template,
            instance=self.instance,
            created=True,
            raw=False,
            using=None,
            update_fields=None,
        )

        mock_create.assert_called_once()

    @patch("apps.templates.signals.get_current_user")
    @patch("apps.templates.signals.get_current_request")
    @patch("apps.templates.signals.ActionLog.objects.create")
    @patch("apps.templates.signals.apps.get_models")
    def test_post_save_action_creates_action_log_on_update(
        self, mock_get_models, mock_create, mock_get_request, mock_get_user
    ):
        mock_get_request.return_value = self.request
        self.request.method = "PATCH"
        mock_get_user.return_value = self.user
        mock_get_models.return_value = [Template]

        post_save_action(
            sender=Template,
            instance=self.instance,
            created=False,
            raw=False,
            using=None,
            update_fields=None,
        )

        mock_create.assert_called_once()

    @patch("apps.templates.signals.get_current_user")
    @patch("apps.templates.signals.get_current_request")
    @patch("apps.templates.signals.ActionLog.objects.create")
    def test_post_save_action_skips_on_raw(
        self, mock_create, mock_get_request, mock_get_user
    ):
        mock_get_request.return_value = self.request
        mock_get_user.return_value = self.user

        post_save_action(
            sender=Template,
            instance=self.instance,
            created=True,
            raw=True,
            using=None,
            update_fields=None,
        )

        mock_create.assert_not_called()

    @patch("apps.templates.signals.get_current_user")
    @patch("apps.templates.signals.get_current_request")
    @patch("apps.templates.signals.ActionLog.objects.create")
    @patch("apps.templates.signals.apps.get_models")
    def test_post_save_action_skips_with_python_user_agent(
        self, mock_get_models, mock_create, mock_get_request, mock_get_user
    ):
        self.request.META = {"HTTP_USER_AGENT": "python-requests/2.28.0"}
        mock_get_request.return_value = self.request
        mock_get_user.return_value = self.user
        mock_get_models.return_value = [Template]

        post_save_action(
            sender=Template,
            instance=self.instance,
            created=True,
            raw=False,
            using=None,
            update_fields=None,
        )

        mock_create.assert_not_called()


class PostDeleteActionSignalTestCase(TestCase):
    def setUp(self):
        self.company_id = uuid.uuid4()
        self.user = Mock()
        self.user.company_group = Mock()
        self.user.is_anonymous = False

        self.instance = Mock()
        self.instance.pk = uuid.uuid4()
        self.instance.get_company_id = self.company_id

        self.request = Mock()
        self.request.method = "DELETE"

    @patch("apps.templates.signals.get_current_user")
    @patch("apps.templates.signals.get_current_request")
    @patch("apps.templates.signals.ActionLog.objects.create")
    @patch("apps.templates.signals.apps.get_models")
    def test_post_delete_action_creates_action_log(
        self, mock_get_models, mock_create, mock_get_request, mock_get_user
    ):
        mock_get_request.return_value = self.request
        mock_get_user.return_value = self.user
        mock_get_models.return_value = [Template]

        post_delete_action(sender=Template, instance=self.instance, using=None)

        mock_create.assert_called_once()
