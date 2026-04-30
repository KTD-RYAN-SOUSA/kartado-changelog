import uuid
from unittest.mock import Mock, PropertyMock, patch

import pytest
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.reportings.permissions import (
    RecordMenuPermissions,
    ReportingFilePermissions,
    ReportingMessageReadReceiptPermissions,
    ReportingPermissions,
)

pytestmark = pytest.mark.django_db


class ReportingPermissionsTestCase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = Mock()
        self.user.uuid = uuid.uuid4()
        self.user_firms = Mock()
        self.user.user_firms = self.user_firms
        self.user_firms.filter.return_value = []
        self.view = Mock()
        self.view.permissions = None
        self.permissions = ReportingPermissions()
        self.company_id = uuid.uuid4()

    @patch("apps.reportings.permissions.PermissionManager")
    def test_has_permission_zip_pictures(self, mock_permission_manager):
        request = self.factory.get("/")
        request.user = self.user
        request.query_params = {"company": str(self.company_id)}
        self.view.action = "zip_pictures"

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager
        mock_manager.has_permission.return_value = True

        result = self.permissions.has_permission(request, self.view)

        mock_permission_manager.assert_called_once_with(
            user=self.user, company_ids=self.company_id, model="Reporting"
        )

        mock_manager.has_permission.assert_called_once_with(permission="can_create")

        self.assertTrue(result)

    @patch("apps.reportings.permissions.PermissionManager")
    def test_has_permission_spreadsheet_resource_list(self, mock_permission_manager):
        request = self.factory.get("/")
        request.user = self.user
        request.query_params = {"company": str(self.company_id)}
        self.view.action = "spreadsheet_resource_list"

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager
        mock_manager.has_permission.side_effect = [True, True]

        result = self.permissions.has_permission(request, self.view)

        self.assertEqual(mock_manager.has_permission.call_count, 2)
        mock_manager.has_permission.assert_any_call(permission="can_create")
        mock_manager.has_permission.assert_any_call(permission="can_view_money")

        self.assertTrue(result)

    @patch("apps.reportings.permissions.Reporting.objects.get")
    @patch("apps.reportings.permissions.PermissionManager")
    def test_has_permission_bulk(self, mock_permission_manager, mock_reporting_get):
        reporting_id = uuid.uuid4()
        request = self.factory.post("/")
        request.user = self.user
        request.data = {"reportings": [{"id": str(reporting_id)}]}
        self.view.action = "bulk"

        mock_reporting = Mock()
        mock_reporting.company_id = self.company_id
        mock_reporting_get.return_value = mock_reporting

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager
        mock_manager.has_permission.return_value = True

        result = self.permissions.has_permission(request, self.view)

        mock_permission_manager.assert_called_once_with(
            user=self.user, company_ids=self.company_id, model="Reporting"
        )

        mock_manager.has_permission.assert_called_once_with(permission="can_create")

        self.assertTrue(result)

    @patch("apps.reportings.permissions.Reporting.objects.get")
    def test_has_permission_bulk_validation_error(self, mock_reporting_get):
        """Testa se ValidationError é lançado quando não há reportings na ação bulk"""
        request = self.factory.post("/", {"reportings": []})
        request.user = self.user
        self.view.action = "bulk"

        mock_reporting_get.side_effect = Exception("Reporting não encontrado")

        with self.assertRaises(ValidationError):
            self.permissions.has_permission(request, self.view)

    @patch("apps.reportings.permissions.Reporting.objects.get")
    @patch("apps.reportings.permissions.Reporting.objects.filter")
    @patch("apps.reportings.permissions.ApprovalStep.objects.filter")
    @patch("apps.reportings.permissions.apply_json_logic")
    @patch("apps.reportings.permissions.PermissionManager")
    def test_has_permission_bulk_approval(
        self,
        mock_permission_manager,
        mock_apply_json_logic,
        mock_approval_step_filter,
        mock_reporting_filter,
        mock_reporting_get,
    ):
        reporting_id = uuid.uuid4()
        request = self.factory.post("/")
        request.user = self.user
        request.data = {"reportings": [{"id": str(reporting_id)}]}
        self.view.action = "bulk_approval"

        mock_reporting = Mock()
        mock_reporting.company_id = self.company_id
        mock_reporting_get.return_value = mock_reporting

        mock_queryset = Mock()
        mock_reporting_filter.return_value = mock_queryset
        mock_queryset.prefetch_related.return_value = mock_queryset
        mock_queryset.distinct.return_value = mock_queryset
        mock_queryset.filter.return_value.exists.return_value = False
        mock_queryset.filter.return_value.values_list.return_value = []

        mock_approval_steps = Mock()
        mock_approval_step_filter.return_value = mock_approval_steps
        mock_approval_steps.prefetch_related.return_value = mock_approval_steps
        mock_approval_steps.distinct.return_value = []

        mock_apply_json_logic.return_value = True

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager
        mock_manager.has_permission.return_value = True

        result = self.permissions.has_permission(request, self.view)

        mock_manager.has_permission.assert_called_once_with(permission="can_approve")

        self.assertTrue(result)

    @patch("apps.reportings.permissions.PermissionManager")
    def test_has_object_permission_approval(self, mock_permission_manager):
        request = self.factory.post("/")
        request.user = self.user
        self.view.action = "approval"

        obj = Mock()
        obj.company_id = self.company_id
        obj.approval_step = Mock()
        obj.approval_step.responsible_json_logic = {}
        obj.approval_step.responsible_created_by = False
        obj.approval_step.responsible_users.all.return_value = []
        obj.approval_step.responsible_firms.all.return_value = []
        obj.created_by = Mock()

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager
        mock_manager.has_permission.return_value = True
        mock_manager.all_permissions = {}

        with patch("apps.reportings.permissions.apply_json_logic", return_value=True):
            result = self.permissions.has_object_permission(request, self.view, obj)

        mock_manager.has_permission.assert_called_once_with(permission="can_approve")

        self.assertTrue(result)

    @patch("apps.reportings.permissions.PermissionManager")
    def test_has_object_permission_update(self, mock_permission_manager):
        request = self.factory.put("/")
        request.user = self.user
        self.view.action = "update"

        obj = Mock()
        obj.company_id = self.company_id
        obj.editable = True

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager
        mock_manager.has_permission.return_value = True

        result = self.permissions.has_object_permission(request, self.view, obj)

        mock_manager.has_permission.assert_called_once_with(permission="can_edit")

        self.assertTrue(result)

    @patch("apps.reportings.permissions.PermissionManager")
    def test_has_object_permission_update_not_editable(self, mock_permission_manager):
        """Testa se ValidationError é lançado quando o reporting não é editável"""
        request = self.factory.put("/")
        request.user = self.user
        self.view.action = "update"

        obj = Mock()
        obj.company_id = self.company_id
        obj.editable = False

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager

        with self.assertRaises(ValidationError):
            self.permissions.has_object_permission(request, self.view, obj)


class ReportingFilePermissionsTestCase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = Mock()
        self.view = Mock()
        self.view.permissions = None
        self.permissions = ReportingFilePermissions()
        self.company_id = uuid.uuid4()

    @patch("apps.reportings.permissions.ReportingFile.objects.get")
    @patch("apps.reportings.permissions.PermissionManager")
    def test_has_permission_bulk(
        self, mock_permission_manager, mock_reporting_file_get
    ):
        reporting_file_id = uuid.uuid4()
        request = self.factory.post("/")
        request.user = self.user
        request.data = {"reporting_files": [{"id": str(reporting_file_id)}]}
        self.view.action = "bulk"

        mock_reporting_file = Mock()
        mock_reporting = Mock()
        mock_reporting.company_id = self.company_id
        mock_reporting_file.reporting = mock_reporting
        mock_reporting_file_get.return_value = mock_reporting_file

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager
        mock_manager.has_permission.return_value = True

        result = self.permissions.has_permission(request, self.view)

        mock_manager.has_permission.assert_called_once_with(permission="can_create")

        self.assertTrue(result)

    @patch(
        "apps.reportings.permissions.ReportingChildPermissions.has_object_permission",
        return_value=True,
    )
    def test_has_object_permission_check(self, mock_super):
        raw_request = self.factory.get("/")
        request = Request(raw_request)
        request.user = self.user
        self.view.action = "check"

        obj = Mock()
        obj.reporting = Mock(company_id=self.company_id)

        result = self.permissions.has_object_permission(request, self.view, obj)

        self.assertTrue(result)
        mock_super.assert_called_once_with(request, self.view, obj)

    def test_has_object_permission_is_shared_with_agency(self):
        raw_request = self.factory.get("/")
        request = Request(raw_request)
        request.user = self.user
        self.view.action = "IsSharedWithAgency"

        obj = Mock()
        obj.reporting = Mock(company_id=self.company_id)

        with patch.object(
            self.permissions.__class__.__bases__[0],
            "has_object_permission",
            return_value=True,
        ) as mock_super:
            result = self.permissions.has_object_permission(request, self.view, obj)

        self.assertTrue(result)
        mock_super.assert_called_once_with(request, self.view, obj)


class RecordMenuPermissionsTestCase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = Mock()
        self.view = Mock()
        self.view.permissions = None
        self.permissions = RecordMenuPermissions()
        self.company_id = uuid.uuid4()

    @patch("apps.reportings.permissions.PermissionManager")
    def test_has_object_permission_destroy_system_default(
        self, mock_permission_manager
    ):
        """Testa se ValidationError é lançado ao tentar excluir menu padrão do sistema"""
        request = self.factory.delete("/")
        request.user = self.user
        self.view.action = "destroy"

        obj = Mock()
        obj.company_id = self.company_id
        obj.system_default = True

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager

        with self.assertRaises(ValidationError):
            self.permissions.has_object_permission(request, self.view, obj)

    @patch("apps.reportings.permissions.RecordMenu.objects.filter")
    @patch("apps.reportings.permissions.PermissionManager")
    def test_has_object_permission_destroy_last_menu(
        self, mock_permission_manager, mock_record_menu_filter
    ):
        """Testa se ValidationError é lançado ao tentar excluir o último menu personalizado"""
        request = self.factory.delete("/")
        request.user = self.user
        self.view.action = "destroy"

        obj = Mock()
        obj.company_id = self.company_id
        obj.system_default = False
        obj.created_by = self.user
        obj.record_menu_reportings = Mock()
        obj.record_menu_reportings.exists.return_value = False
        obj.company = Mock()

        mock_queryset = Mock()
        mock_record_menu_filter.return_value = mock_queryset
        mock_queryset.count.return_value = 1

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager
        mock_manager.has_permission.return_value = True

        with self.assertRaises(ValidationError):
            self.permissions.has_object_permission(request, self.view, obj)

    def test_get_company_id_list(self):
        request = self.factory.get("/")
        request.query_params = {"company": str(self.company_id)}

        result = self.permissions.get_company_id("list", request)

        self.assertEqual(result, self.company_id)

    def test_get_company_id_list_missing_param(self):
        request = self.factory.get("/")
        request.query_params = {}

        result = self.permissions.get_company_id("list", request)

        self.assertFalse(result)

    def test_get_company_id_update_not_editable(self):
        """Testa se permite edição mesmo quando o reporting não é editável (caso especial para mensagens)"""
        request = self.factory.put("/")

        obj = Mock()
        obj.company_id = self.company_id

        result = self.permissions.get_company_id("update", request, obj)

        self.assertEqual(result, self.company_id)

    def test_get_company_id_invalid_action(self):
        """Testa se retorna False para ações não suportadas"""
        request = self.factory.post("/")

        result = self.permissions.get_company_id("invalid_action", request)

        self.assertFalse(result)

    def test_get_company_id_move_down_menu(self):
        """Testa obtenção do company_id para ação move_down_menu"""
        obj = Mock()
        obj.company_id = self.company_id

        result = self.permissions.get_company_id("move_down_menu", None, obj)

        self.assertEqual(result, self.company_id)

    def test_get_company_id_move_up_menu(self):
        """Testa obtenção do company_id para ação move_up_menu"""
        obj = Mock()
        obj.company_id = self.company_id

        result = self.permissions.get_company_id("move_up_menu", None, obj)

        self.assertEqual(result, self.company_id)


class ReportingMessageReadReceiptPermissionsTestCase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = Mock()
        self.user.uuid = uuid.uuid4()
        self.view = Mock()
        self.view.permissions = None
        self.permissions = ReportingMessageReadReceiptPermissions()
        self.company_id = uuid.uuid4()

    def test_get_company_id_list(self):
        request = self.factory.get("/")
        request.query_params = {"company": str(self.company_id)}

        result = self.permissions.get_company_id("list", request)

        self.assertEqual(result, self.company_id)

    def test_get_company_id_retrieve(self):
        request = self.factory.get("/")
        request.query_params = {"company": str(self.company_id)}

        result = self.permissions.get_company_id("retrieve", request)

        self.assertEqual(result, self.company_id)

    def test_get_company_id_list_missing_param(self):
        request = self.factory.get("/")
        request.query_params = {}

        result = self.permissions.get_company_id("list", request)

        self.assertFalse(result)

    def test_get_company_id_list_invalid_uuid(self):
        request = self.factory.get("/")
        request.query_params = {"company": "invalid-uuid"}

        result = self.permissions.get_company_id("list", request)

        self.assertFalse(result)

    @patch("apps.reportings.permissions.ReportingMessage.objects.get")
    def test_get_company_id_create(self, mock_reporting_message_get):
        reporting_message_id = uuid.uuid4()
        request = self.factory.post("/")
        request.data = {"reporting_message": {"id": str(reporting_message_id)}}

        mock_reporting_message = Mock()
        mock_reporting = Mock()
        mock_reporting.company_id = self.company_id
        mock_reporting_message.reporting = mock_reporting
        mock_reporting_message_get.return_value = mock_reporting_message

        result = self.permissions.get_company_id("create", request)

        self.assertEqual(result, self.company_id)
        mock_reporting_message_get.assert_called_once_with(pk=reporting_message_id)

    @patch("apps.reportings.permissions.ReportingMessage.objects.get")
    def test_get_company_id_create_message_not_found(self, mock_reporting_message_get):
        """Testa se retorna False quando a mensagem não é encontrada"""
        reporting_message_id = uuid.uuid4()
        request = self.factory.post("/")
        request.data = {"reporting_message": {"id": str(reporting_message_id)}}

        mock_reporting_message_get.side_effect = Exception("Mensagem não encontrada")

        result = self.permissions.get_company_id("create", request)

        self.assertFalse(result)

    def test_get_company_id_update(self):
        request = self.factory.put("/")

        obj = Mock()
        reporting_message = Mock()
        reporting = Mock()
        reporting.company_id = self.company_id
        reporting_message.reporting = reporting
        obj.reporting_message = reporting_message

        result = self.permissions.get_company_id("update", request, obj)

        self.assertEqual(result, self.company_id)

    def test_get_company_id_partial_update(self):
        request = self.factory.patch("/")

        obj = Mock()
        reporting_message = Mock()
        reporting = Mock()
        reporting.company_id = self.company_id
        reporting_message.reporting = reporting
        obj.reporting_message = reporting_message

        result = self.permissions.get_company_id("partial_update", request, obj)

        self.assertEqual(result, self.company_id)

    def test_get_company_id_destroy(self):
        request = self.factory.delete("/")

        obj = Mock()
        reporting_message = Mock()
        reporting = Mock()
        reporting.company_id = self.company_id
        reporting_message.reporting = reporting
        obj.reporting_message = reporting_message

        result = self.permissions.get_company_id("destroy", request, obj)

        self.assertEqual(result, self.company_id)

    def test_get_company_id_update_exception(self):
        """Testa se retorna False quando ocorre exceção ao acessar company_id no update"""
        request = self.factory.put("/")

        obj = Mock()
        reporting_message = Mock()
        type(reporting_message).reporting = PropertyMock(
            side_effect=Exception("Erro ao acessar reporting")
        )
        obj.reporting_message = reporting_message

        result = self.permissions.get_company_id("update", request, obj)

        self.assertFalse(result)

    def test_get_company_id_invalid_action(self):
        """Testa se retorna False para ações não suportadas"""
        request = self.factory.post("/")

        result = self.permissions.get_company_id("invalid_action", request)

        self.assertFalse(result)
