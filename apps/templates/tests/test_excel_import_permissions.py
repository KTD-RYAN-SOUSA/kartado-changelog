import uuid
from unittest.mock import Mock, patch

import pytest
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.templates.permissions import ExcelImportPermissions

pytestmark = pytest.mark.django_db


class ExcelImportPermissionsTestCase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = Mock()
        self.view = Mock()
        self.view.permissions = None
        self.permissions = ExcelImportPermissions()
        self.company_id = uuid.uuid4()

    @patch(
        "apps.templates.permissions.BaseModelAccessPermissions.has_object_permission"
    )
    def test_has_object_permission_upload_zip_images_maps_to_retrieve(self, mock_super):
        request = self.factory.post("/")
        request.user = self.user
        self.view.action = "upload_zip_images"

        obj = Mock()
        obj.company_id = self.company_id

        mock_super.return_value = True

        result = self.permissions.has_object_permission(request, self.view, obj)

        self.assertEqual(self.view.action, "retrieve")
        mock_super.assert_called_once_with(request, self.view, obj)
        self.assertTrue(result)

    @patch(
        "apps.templates.permissions.BaseModelAccessPermissions.has_object_permission"
    )
    def test_has_object_permission_generate_preview_maps_to_retrieve(self, mock_super):
        request = self.factory.post("/")
        request.user = self.user
        self.view.action = "generate_preview"

        obj = Mock()

        mock_super.return_value = True

        result = self.permissions.has_object_permission(request, self.view, obj)

        self.assertEqual(self.view.action, "retrieve")
        mock_super.assert_called_once_with(request, self.view, obj)
        self.assertTrue(result)

    @patch(
        "apps.templates.permissions.BaseModelAccessPermissions.has_object_permission"
    )
    def test_has_object_permission_execute_maps_to_retrieve(self, mock_super):
        request = self.factory.post("/")
        request.user = self.user
        self.view.action = "execute"

        obj = Mock()

        mock_super.return_value = True

        result = self.permissions.has_object_permission(request, self.view, obj)

        self.assertEqual(self.view.action, "retrieve")
        mock_super.assert_called_once_with(request, self.view, obj)
        self.assertTrue(result)

    @patch(
        "apps.templates.permissions.BaseModelAccessPermissions.has_object_permission"
    )
    def test_has_object_permission_check_maps_to_retrieve(self, mock_super):
        request = self.factory.post("/")
        request.user = self.user
        self.view.action = "check"

        obj = Mock()

        mock_super.return_value = True

        result = self.permissions.has_object_permission(request, self.view, obj)

        self.assertEqual(self.view.action, "retrieve")
        mock_super.assert_called_once_with(request, self.view, obj)
        self.assertTrue(result)

    @patch(
        "apps.templates.permissions.BaseModelAccessPermissions.has_object_permission"
    )
    def test_has_object_permission_other_actions_not_mapped(self, mock_super):
        request = self.factory.put("/")
        request.user = self.user
        self.view.action = "update"

        obj = Mock()

        mock_super.return_value = True

        result = self.permissions.has_object_permission(request, self.view, obj)

        self.assertEqual(self.view.action, "update")
        mock_super.assert_called_once_with(request, self.view, obj)
        self.assertTrue(result)

    @patch(
        "apps.templates.permissions.BaseModelAccessPermissions.has_object_permission"
    )
    def test_has_object_permission_returns_false_when_super_returns_false(
        self, mock_super
    ):
        request = self.factory.post("/")
        request.user = self.user
        self.view.action = "execute"

        obj = Mock()

        mock_super.return_value = False

        result = self.permissions.has_object_permission(request, self.view, obj)

        self.assertEqual(self.view.action, "retrieve")
        mock_super.assert_called_once_with(request, self.view, obj)
        self.assertFalse(result)
