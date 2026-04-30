import uuid
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.test import TestCase
from rest_framework import status
from rest_framework.exceptions import ValidationError

from apps.daily_reports.permissions import MultipleDailyReportPermissions
from apps.daily_reports.views import MultipleDailyReportViewSet

pytestmark = pytest.mark.django_db


def _make_rdo(number="INT-RDO-2026.00001", approval_step_id=None, pk=None):
    rdo = Mock()
    rdo.pk = pk or uuid.uuid4()
    rdo.uuid = rdo.pk
    rdo.number = number
    rdo.approval_step_id = approval_step_id or uuid.uuid4()
    rdo.approval_step = Mock()
    rdo.approval_step.responsible_json_logic = {}
    rdo.approval_step.responsible_created_by = False
    rdo.approval_step.responsible_users.all.return_value = []
    rdo.approval_step.responsible_firms.all.return_value = []
    rdo.callback = {}
    return rdo


def _make_transition(accepted=True, callback=None):
    transition = Mock()
    transition.condition = {}
    transition.destination = Mock()
    transition.callback = callback or {}
    return transition


class TestBulkApprovalView(TestCase):
    def setUp(self):
        self.user = Mock()
        self.user.uuid = uuid.uuid4()

        self.view = MultipleDailyReportViewSet()
        self.view.format_kwarg = None
        self.view.kwargs = {}
        self.view.request = None
        self.view.permissions = Mock()
        self.view.permissions.has_permission.return_value = True

    def _build_request(self, ids, to_do=None):
        payload = {"multiple_daily_reports": [{"id": str(i)} for i in ids]}
        if to_do is not None:
            payload["to_do"] = to_do
        request = Mock()
        request.user = self.user
        request.data = payload
        return request

    def test_limit_exceeded_returns_400(self):
        ids = [uuid.uuid4() for _ in range(26)]
        request = self._build_request(ids)
        self.view.request = request

        with patch.object(self.view, "get_serializer_context", return_value={}):
            response = self.view.bulk_approval(request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("1 e 25", response.data[0]["detail"])

    def test_empty_list_returns_400(self):
        request = self._build_request([])
        self.view.request = request

        with patch.object(self.view, "get_serializer_context", return_value={}):
            response = self.view.bulk_approval(request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("apps.daily_reports.views.ApprovalTransition")
    @patch("apps.daily_reports.views.MultipleDailyReport")
    @patch("apps.daily_reports.views.apply_json_logic")
    @patch("apps.daily_reports.views.get_obj_serialized")
    def test_all_or_nothing_bad_rdo_returns_400(
        self,
        mock_get_obj_serialized,
        mock_apply_json_logic,
        mock_mdr_model,
        mock_transition_model,
    ):
        shared_step_id = uuid.uuid4()
        rdo_good = _make_rdo("INT-RDO-2026.00001", approval_step_id=shared_step_id)
        rdo_bad = _make_rdo("INT-RDO-2026.00002", approval_step_id=shared_step_id)

        mock_qs = MagicMock()
        mock_qs.__iter__.return_value = iter([rdo_good, rdo_bad])
        mock_qs.values_list.return_value.distinct.return_value = [shared_step_id]
        mock_mdr_model.objects.filter.return_value.prefetch_related.return_value = (
            mock_qs
        )

        transition = _make_transition()
        transition.origin_id = shared_step_id
        mock_transition_qs = MagicMock()
        mock_transition_qs.__iter__.return_value = iter([transition])
        mock_transition_model.objects.filter.return_value.prefetch_related.return_value = (
            mock_transition_qs
        )

        mock_apply_json_logic.side_effect = [True, False]
        mock_get_obj_serialized.return_value = {}

        ids = [rdo_good.pk, rdo_bad.pk]
        request = self._build_request(ids)
        self.view.request = request

        with patch.object(
            self.view, "get_serializer_class", return_value=Mock()
        ), patch.object(self.view, "get_serializer_context", return_value={}):
            response = self.view.bulk_approval(request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("INT-RDO-2026.00002", response.data[0]["detail"])

    @patch("apps.daily_reports.views.bulk_update_with_history")
    @patch("apps.daily_reports.views.ApprovalTransition")
    @patch("apps.daily_reports.views.MultipleDailyReport")
    @patch("apps.daily_reports.views.apply_json_logic")
    @patch("apps.daily_reports.views.get_obj_serialized")
    def test_success_approves_all_rdos(
        self,
        mock_get_obj_serialized,
        mock_apply_json_logic,
        mock_mdr_model,
        mock_transition_model,
        mock_bulk_update,
    ):
        shared_step_id = uuid.uuid4()
        rdo1 = _make_rdo("INT-RDO-2026.00001", approval_step_id=shared_step_id)
        rdo2 = _make_rdo("INT-RDO-2026.00002", approval_step_id=shared_step_id)

        mock_qs = MagicMock()
        mock_qs.__iter__.return_value = iter([rdo1, rdo2])
        mock_qs.values_list.return_value.distinct.return_value = [shared_step_id]
        mock_mdr_model.objects.filter.return_value.prefetch_related.return_value = (
            mock_qs
        )
        mock_mdr_model.history = Mock()

        transition = _make_transition(callback={})
        transition.origin_id = shared_step_id
        mock_transition_qs = MagicMock()
        mock_transition_qs.__iter__.return_value = iter([transition])
        mock_transition_model.objects.filter.return_value.prefetch_related.return_value = (
            mock_transition_qs
        )

        mock_apply_json_logic.return_value = True
        mock_get_obj_serialized.return_value = {}

        ids = [rdo1.pk, rdo2.pk]
        request = self._build_request(ids)
        self.view.request = request

        with patch.object(
            self.view, "get_serializer_class", return_value=Mock()
        ), patch.object(self.view, "get_serializer_context", return_value={}):
            response = self.view.bulk_approval(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_bulk_update.assert_called_once()
        self.assertEqual(rdo1.approval_step, transition.destination)
        self.assertEqual(rdo2.approval_step, transition.destination)

    @patch("apps.daily_reports.views.bulk_update_with_history")
    @patch("apps.daily_reports.views.ApprovalTransition")
    @patch("apps.daily_reports.views.MultipleDailyReport")
    @patch("apps.daily_reports.views.apply_json_logic")
    @patch("apps.daily_reports.views.get_obj_serialized")
    def test_to_do_updates_history_change_reason(
        self,
        mock_get_obj_serialized,
        mock_apply_json_logic,
        mock_mdr_model,
        mock_transition_model,
        mock_bulk_update,
    ):
        rdo = _make_rdo("INT-RDO-2026.00001")

        mock_qs = MagicMock()
        mock_qs.__iter__.return_value = iter([rdo])
        mock_qs.values_list.return_value.distinct.return_value = [rdo.approval_step_id]
        mock_mdr_model.objects.filter.return_value.prefetch_related.return_value = (
            mock_qs
        )

        transition = _make_transition(callback={})
        transition.origin_id = rdo.approval_step_id
        mock_transition_qs = MagicMock()
        mock_transition_qs.__iter__.return_value = iter([transition])
        mock_transition_model.objects.filter.return_value.prefetch_related.return_value = (
            mock_transition_qs
        )

        mock_apply_json_logic.return_value = True
        mock_get_obj_serialized.return_value = {}

        mock_historical = Mock()
        mock_mdr_model.history.model = mock_historical
        mock_historical.objects.filter.return_value.order_by.return_value.values.return_value.__getitem__ = Mock(
            return_value=Mock()
        )
        mock_historical.objects.filter.return_value.update = Mock()

        ids = [rdo.pk]
        request = self._build_request(ids, to_do="Aprovado em massa")
        self.view.request = request

        with patch.object(
            self.view, "get_serializer_class", return_value=Mock()
        ), patch.object(self.view, "get_serializer_context", return_value={}), patch(
            "apps.daily_reports.views.Subquery"
        ), patch(
            "apps.daily_reports.views.OuterRef"
        ):
            response = self.view.bulk_approval(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_historical.objects.filter.assert_called()

    @patch("apps.daily_reports.views.report_transition")
    @patch("apps.daily_reports.views.bulk_update_with_history")
    @patch("apps.daily_reports.views.get_nested_fields")
    @patch("apps.daily_reports.views.ApprovalTransition")
    @patch("apps.daily_reports.views.MultipleDailyReport")
    @patch("apps.daily_reports.views.apply_json_logic")
    @patch("apps.daily_reports.views.get_obj_serialized")
    def test_callbacks_change_fields_and_notifications(
        self,
        mock_get_obj_serialized,
        mock_apply_json_logic,
        mock_mdr_model,
        mock_transition_model,
        mock_get_nested_fields,
        mock_bulk_update,
        mock_report_transition,
    ):
        rdo = _make_rdo("INT-RDO-2026.00001")

        mock_qs = MagicMock()
        mock_qs.__iter__.return_value = iter([rdo])
        mock_qs.values_list.return_value.distinct.return_value = [rdo.approval_step_id]
        mock_mdr_model.objects.filter.return_value.prefetch_related.return_value = (
            mock_qs
        )
        mock_mdr_model.history = Mock()

        transition = _make_transition(
            callback={
                "change_fields": [{"name": "editable", "value": False}],
                "send_notification": ["multiple_daily_report_transition"],
                "notification_message": "RDO aprovado",
            }
        )
        transition.origin_id = rdo.approval_step_id
        mock_transition_qs = MagicMock()
        mock_transition_qs.__iter__.return_value = iter([transition])
        mock_transition_model.objects.filter.return_value.prefetch_related.return_value = (
            mock_transition_qs
        )

        mock_apply_json_logic.return_value = True
        mock_get_obj_serialized.return_value = {}
        mock_get_nested_fields.return_value = False

        ids = [rdo.pk]
        request = self._build_request(ids)
        self.view.request = request

        with patch.object(
            self.view, "get_serializer_class", return_value=Mock()
        ), patch.object(self.view, "get_serializer_context", return_value={}):
            response = self.view.bulk_approval(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get_nested_fields.assert_called_once_with(False, rdo)
        mock_report_transition.assert_called_once_with(rdo, "RDO aprovado", self.user)


class TestBulkApprovalPermissions(TestCase):
    def setUp(self):
        self.user = Mock()
        self.user.uuid = uuid.uuid4()
        self.view = Mock()
        self.view.permissions = None
        self.view.validated_objs = None
        self.permissions = MultipleDailyReportPermissions()
        self.company_id = uuid.uuid4()

    def _make_request(self, ids):
        request = Mock()
        request.user = self.user
        request.data = {"multiple_daily_reports": [{"id": str(i)} for i in ids]}
        return request

    @patch("apps.daily_reports.permissions.apply_json_logic")
    @patch("apps.daily_reports.permissions.MultipleDailyReport")
    @patch("apps.daily_reports.permissions.PermissionManager")
    def test_no_can_approve_returns_false(
        self, mock_permission_manager, mock_mdr_model, mock_apply_json_logic
    ):
        rdo_id = uuid.uuid4()
        request = self._make_request([rdo_id])
        self.view.action = "bulk_approval"

        mock_rdo = Mock()
        mock_rdo.company_id = self.company_id
        mock_rdo.approval_step.responsible_created_by = False
        mock_rdo.approval_step.responsible_users.all.return_value = []
        mock_rdo.approval_step.responsible_firms.all.return_value = []

        mock_qs = MagicMock()
        mock_qs.__iter__.return_value = iter([mock_rdo])
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.filter.return_value.exists.return_value = False

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager
        mock_manager.has_permission.return_value = False
        mock_manager.all_permissions = {}

        mock_apply_json_logic.return_value = False

        with patch.object(
            self.permissions,
            "get_company_id_from_objs",
            return_value=self.company_id,
        ):
            self.view.validated_objs = mock_qs
            result = self.permissions.has_permission(request, self.view)

        self.assertFalse(result)
        mock_manager.has_permission.assert_called_once_with(permission="can_approve")

    @patch("apps.daily_reports.permissions.apply_json_logic")
    @patch("apps.daily_reports.permissions.MultipleDailyReport")
    @patch("apps.daily_reports.permissions.PermissionManager")
    def test_not_responsible_raises_validation_error(
        self,
        mock_permission_manager,
        mock_mdr_model,
        mock_apply_json_logic,
    ):
        rdo_id = uuid.uuid4()
        request = self._make_request([rdo_id])
        self.view.action = "bulk_approval"

        other_user = Mock()
        mock_rdo = Mock()
        mock_rdo.approval_step.responsible_json_logic = {}
        mock_rdo.approval_step.responsible_created_by = False
        mock_rdo.approval_step.responsible_users.all.return_value = [other_user]
        mock_rdo.approval_step.responsible_firms.all.return_value = []

        mock_qs = MagicMock()
        mock_qs.__iter__.return_value = iter([mock_rdo])
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.filter.return_value.exists.return_value = False

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager
        mock_manager.all_permissions = {}

        mock_apply_json_logic.return_value = False

        with patch.object(
            self.permissions,
            "get_company_id_from_objs",
            return_value=self.company_id,
        ):
            self.view.validated_objs = mock_qs
            with self.assertRaises(ValidationError) as ctx:
                self.permissions.has_permission(request, self.view)

        self.assertIn("não tem permissão para aprovar", str(ctx.exception))

    @patch("apps.daily_reports.permissions.MultipleDailyReport")
    @patch("apps.daily_reports.permissions.PermissionManager")
    def test_rdo_without_approval_step_raises_validation_error(
        self, mock_permission_manager, mock_mdr_model
    ):
        rdo_id = uuid.uuid4()
        request = self._make_request([rdo_id])
        self.view.action = "bulk_approval"

        mock_qs = MagicMock()
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.filter.return_value.exists.return_value = True

        with patch.object(
            self.permissions,
            "get_company_id_from_objs",
            return_value=self.company_id,
        ):
            self.view.validated_objs = mock_qs
            with self.assertRaises(ValidationError) as ctx:
                self.permissions.has_permission(request, self.view)

        self.assertIn("não pode ser aprovado", str(ctx.exception))

    def test_rdos_from_different_companies_returns_false(self):
        request = self._make_request([uuid.uuid4(), uuid.uuid4()])
        self.view.action = "bulk_approval"

        with patch.object(
            self.permissions,
            "get_company_id_from_objs",
            return_value=False,
        ):
            result = self.permissions.has_permission(request, self.view)

        self.assertFalse(result)

    @patch("apps.daily_reports.permissions.MultipleDailyReport")
    def test_ids_not_found_in_db_returns_false(self, mock_mdr_model):
        request = self._make_request([uuid.uuid4()])
        request.user.companies.all.return_value.values_list.return_value = [
            self.company_id
        ]

        mock_qs = MagicMock()
        mock_qs.exists.return_value = False
        mock_mdr_model.objects.filter.return_value = mock_qs

        result = self.permissions.get_company_id_from_objs(
            "multiple_daily_reports", request, mock_mdr_model, self.view
        )

        self.assertFalse(result)
