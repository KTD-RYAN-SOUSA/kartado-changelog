from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

from apps.reportings.notifications import (
    reporting_approval_step_report_email,
    reporting_job_email,
    reporting_message_created,
)

pytestmark = pytest.mark.django_db


class TestReportingMessageCreated:
    def setup_method(self):
        # Salvar configurações originais
        self.original_frontend_url = getattr(settings, "FRONTEND_URL", None)

    def teardown_method(self):
        # Restaurar configurações originais
        if hasattr(self, "original_frontend_url"):
            settings.FRONTEND_URL = self.original_frontend_url

    def test_reporting_message_created(self):
        # Usar context managers para garantir que os patches sejam limpos corretamente
        with patch(
            "apps.reportings.notifications.create_notifications", autospec=True
        ) as mock_create_notifications, patch(
            "apps.reportings.notifications.User.objects.filter", autospec=True
        ) as mock_user_filter, patch(
            "apps.reportings.notifications.Firm.objects.filter", autospec=True
        ) as mock_firm_filter:

            # Configurar mocks
            instance = MagicMock()
            instance.reporting.company.pk = "company-uuid"
            instance.reporting.uuid = "reporting-uuid"
            instance.reporting.number = "REP-123"

            mock_reporting_messages = MagicMock()
            mock_reporting_messages.values_list.return_value = [
                "message-1",
                "message-2",
            ]
            instance.reporting.reporting_messages = mock_reporting_messages

            mock_firms_queryset = MagicMock()
            mock_firms_queryset.values_list.return_value = ["firm-1", "firm-2"]
            mock_firm_filter.return_value = mock_firms_queryset

            mock_user1 = MagicMock()
            mock_user1.uuid = "user-1"
            mock_user2 = MagicMock()
            mock_user2.uuid = "user-2"
            mock_users_queryset = MagicMock()
            mock_users_queryset.distinct.return_value = mock_users_queryset
            mock_users_queryset.only.return_value = [mock_user1, mock_user2]
            mock_user_filter.return_value = mock_users_queryset

            # Modificar configuração dentro do contexto do teste
            try:
                settings.FRONTEND_URL = "https://example.com"

                # Executar a função sendo testada
                reporting_message_created(instance)

                # Verificações
                mock_reporting_messages.values_list.assert_called_once_with(
                    "uuid", flat=True
                )
                mock_firm_filter.assert_called_once_with(
                    mentioned_firm_in_messages__in=["message-1", "message-2"]
                )
                mock_firms_queryset.values_list.assert_called_once_with(
                    "uuid", flat=True
                )
                mock_user_filter.assert_called_once()
                mock_users_queryset.distinct.assert_called_once()
                mock_users_queryset.only.assert_called_once_with("uuid")

                expected_url = "https://example.com/#/SharedLink/Reporting/reporting-uuid/messages?company=company-uuid"
                expected_context = {
                    "title": "Nova mensagem no apontamento REP-123",
                    "number": "REP-123",
                    "url": expected_url,
                }
                mock_create_notifications.assert_called_once_with(
                    [mock_user1, mock_user2],
                    instance.reporting.company,
                    expected_context,
                    "reportings/email/reporting_message_created",
                    instance=instance,
                    url=expected_url,
                )
            finally:
                # Garantir que a configuração seja restaurada mesmo se o teste falhar
                settings.FRONTEND_URL = self.original_frontend_url


class TestReportingApprovalStepReportEmail:
    def setup_method(self):
        # Salvar configurações originais
        self.original_time_zone = getattr(settings, "TIME_ZONE", None)

    def teardown_method(self):
        # Restaurar configurações originais
        if hasattr(self, "original_time_zone"):
            settings.TIME_ZONE = self.original_time_zone

    def test_reporting_approval_step_report_email(self):
        # Usar context managers para todos os patches
        with patch(
            "apps.reportings.notifications.create_single_notification", autospec=True
        ) as mock_create_single_notification, patch(
            "apps.reportings.notifications.filter_history", autospec=True
        ) as mock_filter_history, patch(
            "apps.reportings.notifications.get_disclaimer", autospec=True
        ) as mock_get_disclaimer, patch(
            "apps.reportings.notifications.Company.objects.all", autospec=True
        ) as mock_company_all, patch(
            "apps.reportings.notifications.User.objects.filter", autospec=True
        ) as mock_user_filter, patch(
            "apps.reportings.notifications.HistoricalReporting.objects.filter",
            autospec=True,
        ) as mock_historical_filter, patch(
            "apps.reportings.notifications.Reporting.objects.filter", autospec=True
        ) as mock_reporting_filter, patch(
            "apps.reportings.views.ReportingFilter", autospec=True
        ) as mock_reporting_filter_class:

            # Configurar mocks
            mock_company = MagicMock()
            mock_company.company_group = "group-1"
            mock_company.uuid = "company-uuid"
            mock_company_all.return_value = [mock_company]

            mock_get_disclaimer.return_value = ("Disclaimer message", "app-type")

            mock_reporting_queryset = MagicMock()
            mock_reporting_filter.return_value = mock_reporting_queryset
            mock_reporting_queryset.select_related.return_value = (
                mock_reporting_queryset
            )
            mock_reporting_queryset.prefetch_related.return_value = (
                mock_reporting_queryset
            )

            mock_filtered_reportings = [MagicMock(), MagicMock()]
            for i, rep in enumerate(mock_filtered_reportings):
                rep.number = f"REP-{i+1}"
                rep.status = MagicMock()
                rep.status.name = f"Status {i+1}"
                rep.approval_step = MagicMock()
                rep.approval_step.name = f"Step {i+1}"
                rep.form_data = {"notes": f"Notes {i+1}"}

            mock_filter_history.return_value = mock_filtered_reportings

            mock_user = MagicMock()
            mock_user.pk = "user-uuid"

            mock_users_queryset1 = MagicMock()
            mock_users_queryset1.values_list.return_value = ["user-1", "user-2"]

            mock_historical_queryset = MagicMock()
            mock_historical_queryset.values_list.return_value = [
                "history-1",
                "history-2",
            ]
            mock_historical_filter.return_value = mock_historical_queryset

            mock_users_queryset2 = MagicMock()
            mock_users_queryset2.distinct.return_value = [mock_user]

            mock_user_filter.side_effect = [mock_users_queryset1, mock_users_queryset2]

            mock_reporting_filter_instance = MagicMock()
            mock_reporting_filter_instance.get_only_related_to.return_value = (
                mock_filtered_reportings
            )
            mock_reporting_filter_class.return_value = mock_reporting_filter_instance

            # Modificar configuração dentro do contexto do teste
            try:
                settings.TIME_ZONE = "UTC"

                # Executar a função sendo testada
                reporting_approval_step_report_email()

                # Verificações
                mock_get_disclaimer.assert_called_once_with("group-1")
                mock_reporting_filter.assert_called_once_with(company=mock_company)
                mock_reporting_queryset.select_related.assert_called_once_with("status")
                mock_reporting_queryset.prefetch_related.assert_called_once_with(
                    "historicalreporting__history_user"
                )

                assert mock_filter_history.call_count == 1
                assert mock_user_filter.call_count == 2
                assert (
                    mock_reporting_filter_instance.get_only_related_to.call_count == 1
                )
                assert mock_create_single_notification.call_count >= 1

                args, kwargs = mock_create_single_notification.call_args_list[0]
                assert args[0] == mock_user
                assert args[1] == mock_company
                assert "title" in args[2]
                assert "message" in args[2]
                assert "disclaimer" in args[2]
                assert args[3] == "reportings/email/reporting_approval_step"
                assert kwargs.get("push") is False
            finally:
                # Garantir que a configuração seja restaurada mesmo se o teste falhar
                settings.TIME_ZONE = self.original_time_zone


class TestReportingJobEmail:
    def setup_method(self):
        # Salvar configurações originais que possam ser modificadas
        pass

    def teardown_method(self):
        # Restaurar configurações originais
        pass

    def test_reporting_job_email(self):
        # Usar context managers para todos os patches
        with patch(
            "apps.reportings.notifications.create_single_notification", autospec=True
        ) as mock_create_single_notification, patch(
            "apps.reportings.notifications.get_disclaimer", autospec=True
        ) as mock_get_disclaimer, patch(
            "apps.reportings.notifications.Company.objects.all", autospec=True
        ) as mock_company_all, patch(
            "apps.reportings.notifications.Reporting.objects.filter", autospec=True
        ) as mock_reporting_filter:

            # Configurar mocks
            mock_company = MagicMock()
            mock_company.company_group = "group-1"
            mock_company.uuid = "company-uuid"
            mock_company_all.return_value = [mock_company]

            mock_get_disclaimer.return_value = ("Disclaimer message", "app-type")

            mock_reporting1 = MagicMock()
            mock_reporting1.number = "REP-1"
            mock_reporting1.status = MagicMock()
            mock_reporting1.status.name = "Status 1"
            mock_reporting1.form_data = {"notes": "Notes 1"}

            mock_reporting2 = MagicMock()
            mock_reporting2.number = "REP-2"
            mock_reporting2.status = MagicMock()
            mock_reporting2.status.name = "Status 2"
            mock_reporting2.form_data = {"notes": "Notes 2"}

            mock_job1 = MagicMock()
            mock_job1.uuid = "job-1"
            mock_job1.title = "Job 1"
            mock_job1.created_by = MagicMock()
            mock_job1.worker = MagicMock()
            mock_job1.firm = MagicMock()
            mock_job1.firm.users.all.return_value = []
            mock_job1.watcher_users.all.return_value = []
            mock_job1.watcher_firms.all.return_value = []
            mock_job1.watcher_subcompanies.all.return_value = []

            mock_reporting1.job = mock_job1
            mock_reporting2.job = mock_job1

            mock_reportings_queryset = MagicMock()
            mock_reportings_queryset.prefetch_related.return_value = (
                mock_reportings_queryset
            )
            mock_reportings_queryset.exists.return_value = True
            mock_reportings_queryset.__iter__.return_value = iter(
                [mock_reporting1, mock_reporting2]
            )
            mock_reporting_filter.return_value = mock_reportings_queryset

            # Executar a função sendo testada
            reporting_job_email()

            # Verificações
            mock_get_disclaimer.assert_called_once_with("group-1")
            mock_reportings_queryset.prefetch_related.assert_called_once()

            assert mock_create_single_notification.call_count >= 1

            for call_args in mock_create_single_notification.call_args_list:
                args, kwargs = call_args
                assert args[1] == mock_company
                assert "title" in args[2]
                assert "message" in args[2]
                assert "disclaimer" in args[2]
                assert args[3] == "reportings/email/reporting_job_email"
                assert kwargs.get("push") is False
