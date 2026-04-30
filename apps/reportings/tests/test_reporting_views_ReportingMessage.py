import uuid
from unittest.mock import Mock, patch

import pytest
from django.db.models import Q
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.reportings.views import ReportingMessageFilter, ReportingMessageView

pytestmark = pytest.mark.django_db


class ReportingMessageFilterTestCase(TestCase):
    def setUp(self):
        self.filter = ReportingMessageFilter()
        self.queryset = Mock()
        self.queryset.filter.return_value = self.queryset
        self.queryset.distinct.return_value = self.queryset
        self.filter.request = Mock()
        self.filter.data = {"company": str(uuid.uuid4())}

    @patch("apps.reportings.views.Company.objects.get")
    @patch("apps.reportings.views.get_uuids_jobs_user_firms")
    @patch("apps.reportings.views.get_uuids_rdos_user_firms")
    def test_get_jobs_rdos_user_firms(
        self, mock_get_rdos, mock_get_jobs, mock_company_get
    ):
        mock_company = Mock()
        mock_company.uuid = uuid.uuid4()
        mock_company_get.return_value = mock_company

        mock_get_jobs.return_value = ["job1", "job2"]
        mock_get_rdos.return_value = ["rdo1", "rdo2"]

        result = self.filter.get_jobs_rdos_user_firms(
            self.queryset, "jobs_rdos_user_firms", "jobs|rdos"
        )

        mock_company_get.assert_called_with(uuid=self.filter.data["company"])
        mock_get_jobs.assert_called_with("jobs", mock_company, self.filter.request.user)
        mock_get_rdos.assert_called_with("rdos", mock_company, self.filter.request.user)

        expected_q = Q(reporting__job_id__in=["job1", "job2"]) | Q(
            reporting__reporting_multiple_daily_reports__in=["rdo1", "rdo2"]
        )
        self.queryset.filter.assert_called_with(expected_q)
        self.queryset.distinct.assert_called_once()

        self.assertEqual(result, self.queryset)

    @patch("apps.reportings.views.Company.objects.get")
    def test_get_jobs_rdos_user_firms_no_company(self, mock_company_get):
        self.filter.data = {}
        result = self.filter.get_jobs_rdos_user_firms(
            self.queryset, "jobs_rdos_user_firms", "jobs|rdos"
        )

        mock_company_get.assert_not_called()
        self.assertEqual(result, self.queryset)

    @patch("apps.reportings.views.Company.objects.get")
    @patch("apps.reportings.views.Job.objects.filter")
    def test_get_num_jobs_only_user_firms(self, mock_job_filter, mock_company_get):
        mock_company = Mock()
        mock_company.metadata = {"num_jobs": "10", "max_reportings_by_job": "300"}
        mock_company_get.return_value = mock_company

        self.filter.request.user.user_firms.all.return_value = ["firm1", "firm2"]

        mock_jobs_ordered = Mock()
        mock_jobs_sliced = Mock()
        mock_jobs_by_count = Mock()

        mock_job_filter.side_effect = None  # Remover side_effect anterior
        mock_job_filter.return_value = mock_jobs_by_count
        mock_jobs_by_count.order_by.return_value = mock_jobs_ordered
        mock_jobs_ordered.__getitem__ = Mock(return_value=mock_jobs_sliced)
        mock_jobs_sliced.values_list.return_value = ["job1", "job2"]

        mock_jobs_by_ids = Mock()
        mock_jobs_by_ids.values_list.return_value = ["job3", "job4"]

        # Configurar side_effect para as duas chamadas diferentes
        mock_job_filter.side_effect = [mock_jobs_by_count, mock_jobs_by_ids]

        with patch("apps.reportings.views.Job.objects.filter", mock_job_filter):
            result = self.filter.get_num_jobs_only_user_firms(
                self.queryset, "num_jobs_only_user_firms", "5,job_uuid1,job_uuid2"
            )

        mock_company_get.assert_called_with(uuid=self.filter.data["company"])

        mock_job_filter.assert_any_call(
            firm__in=["firm1", "firm2"],
            archived=False,
            reporting_count__lte=300,
        )
        mock_job_filter.assert_any_call(
            uuid__in=["job_uuid1", "job_uuid2"],
            archived=False,
            reporting_count__lte=300,
        )

        expected_q = Q(reporting__job_id__in=["job1", "job2"]) | Q(
            reporting__job_id__in=["job3", "job4"]
        )
        self.queryset.filter.assert_called_with(expected_q)
        self.queryset.distinct.assert_called_once()

        self.assertEqual(result, self.queryset)

    @patch("apps.reportings.views.Company.objects.get")
    def test_get_num_jobs_only_user_firms_no_company(self, mock_company_get):
        self.filter.data = {}

        result = self.filter.get_num_jobs_only_user_firms(
            self.queryset, "num_jobs_only_user_firms", "5,job_uuid1,job_uuid2"
        )

        mock_company_get.assert_not_called()
        self.assertEqual(result, self.queryset)

    @patch("apps.reportings.views.Company.objects.get")
    @patch("apps.reportings.views.Firm.objects.filter")
    def test_get_num_user_firms(self, mock_firm_filter, mock_company_get):
        mock_company = Mock()
        mock_company.metadata = {"num_firms": "10"}
        mock_company_get.return_value = mock_company

        mock_firms_ordered = Mock()
        mock_firms_sliced = Mock()
        mock_firms_by_count = Mock()

        mock_firm_filter.side_effect = None  # Remover side_effect anterior
        mock_firm_filter.return_value = mock_firms_by_count
        mock_firms_by_count.order_by.return_value = mock_firms_ordered
        mock_firms_ordered.__getitem__ = Mock(return_value=mock_firms_sliced)
        mock_firms_sliced.values_list.return_value = ["firm1", "firm2"]

        mock_firms_by_ids = Mock()
        mock_firms_by_ids.values_list.return_value = ["firm3", "firm4"]

        mock_firm_filter.side_effect = [mock_firms_by_count, mock_firms_by_ids]

        with patch("apps.reportings.views.Firm.objects.filter", mock_firm_filter):
            result = self.filter.get_num_user_firms(
                self.queryset, "num_user_firms", "5,firm_uuid1,firm_uuid2"
            )

        mock_company_get.assert_called_with(uuid=self.filter.data["company"])

        mock_firm_filter.assert_any_call(
            company=mock_company, users__in=[self.filter.request.user]
        )
        mock_firm_filter.assert_any_call(
            uuid__in=["firm_uuid1", "firm_uuid2"], company=mock_company
        )

        expected_q = Q(
            reporting__reporting_multiple_daily_reports__firm__in=["firm1", "firm2"]
        ) | Q(reporting__reporting_multiple_daily_reports__firm__in=["firm3", "firm4"])
        self.queryset.filter.assert_called_with(expected_q)
        self.queryset.distinct.assert_called_once()

        self.assertEqual(result, self.queryset)

    @patch("apps.reportings.views.Company.objects.get")
    def test_get_num_user_firms_no_company(self, mock_company_get):
        self.filter.data = {}

        result = self.filter.get_num_user_firms(
            self.queryset, "num_user_firms", "5,firm_uuid1,firm_uuid2"
        )

        mock_company_get.assert_not_called()
        self.assertEqual(result, self.queryset)


class ReportingMessageViewTestCase(TestCase):
    def setUp(self):
        self.view = ReportingMessageView()
        self.factory = APIRequestFactory()
        self.view.request = Mock()
        self.view.format_kwarg = None

    def test_perform_create(self):
        serializer = Mock()
        user = Mock()
        self.view.request.user = user

        self.view.perform_create(serializer)

        serializer.save.assert_called_with(created_by=user)

    @patch("apps.reportings.views.PermissionManager")
    @patch("apps.reportings.views.ReportingMessage.objects.filter")
    @patch("apps.reportings.views.ReportingMessage.objects.none")
    @patch("apps.reportings.views.join_queryset")
    def test_get_queryset_list_action_with_company_all_permissions(
        self, mock_join_queryset, mock_none, mock_filter, mock_permission_manager
    ):
        self.view.action = "list"
        company_id = str(uuid.uuid4())
        self.view.request.query_params = {"company": company_id}

        mock_permission_instance = Mock()
        mock_permission_manager.return_value = mock_permission_instance
        mock_permission_instance.get_allowed_queryset.return_value = ["all"]

        mock_all_queryset = Mock()
        mock_filter.return_value = mock_all_queryset

        mock_joined_queryset = Mock()
        mock_join_queryset.return_value = mock_joined_queryset

        mock_serializer_class = Mock()
        self.view.get_serializer_class = Mock(return_value=mock_serializer_class)
        mock_serializer_class.setup_eager_loading.return_value = "final_queryset"

        result = self.view.get_queryset()

        mock_permission_manager.assert_called_with(
            user=self.view.request.user,
            company_ids=uuid.UUID(company_id),
            model="ReportingMessage",
        )
        mock_permission_instance.get_allowed_queryset.assert_called_once()

        mock_filter.assert_called_with(
            reporting__company_id__in=[uuid.UUID(company_id)]
        )
        mock_join_queryset.assert_called_with(None, mock_all_queryset)

        mock_serializer_class.setup_eager_loading.assert_called_with(
            mock_joined_queryset.distinct()
        )

        self.assertEqual(result, "final_queryset")

    @patch("apps.reportings.views.PermissionManager")
    @patch("apps.reportings.views.ReportingMessage.objects.filter")
    @patch("apps.reportings.views.ReportingMessage.objects.none")
    @patch("apps.reportings.views.join_queryset")
    def test_get_queryset_list_action_with_company_self_permission(
        self, mock_join_queryset, mock_none, mock_filter, mock_permission_manager
    ):
        self.view.action = "list"
        company_id = str(uuid.uuid4())
        self.view.request.query_params = {"company": company_id}

        mock_permission_instance = Mock()
        mock_permission_manager.return_value = mock_permission_instance
        mock_permission_instance.get_allowed_queryset.return_value = ["self"]

        mock_self_queryset = Mock()
        mock_filter.return_value = mock_self_queryset

        mock_joined_queryset = Mock()
        mock_join_queryset.return_value = mock_joined_queryset

        mock_serializer_class = Mock()
        self.view.get_serializer_class = Mock(return_value=mock_serializer_class)
        mock_serializer_class.setup_eager_loading.return_value = "final_queryset"

        result = self.view.get_queryset()

        mock_permission_manager.assert_called_with(
            user=self.view.request.user,
            company_ids=uuid.UUID(company_id),
            model="ReportingMessage",
        )
        mock_permission_instance.get_allowed_queryset.assert_called_once()

        expected_q = Q(created_by=self.view.request.user) | Q(
            reporting__created_by=self.view.request.user
        )
        mock_filter.assert_called_with(expected_q)

        mock_join_queryset.assert_called_with(None, mock_self_queryset)

        mock_serializer_class.setup_eager_loading.assert_called_with(
            mock_joined_queryset.distinct()
        )

        self.assertEqual(result, "final_queryset")

    @patch("apps.reportings.views.PermissionManager")
    @patch("apps.reportings.views.ReportingMessage.objects.none")
    @patch("apps.reportings.views.join_queryset")
    def test_get_queryset_list_action_with_company_none_permission(
        self, mock_join_queryset, mock_none, mock_permission_manager
    ):
        self.view.action = "list"
        company_id = str(uuid.uuid4())
        self.view.request.query_params = {"company": company_id}

        mock_permission_instance = Mock()
        mock_permission_manager.return_value = mock_permission_instance
        mock_permission_instance.get_allowed_queryset.return_value = ["none"]

        mock_none_queryset = Mock()
        mock_none.return_value = mock_none_queryset

        mock_joined_queryset = Mock()
        mock_join_queryset.return_value = mock_joined_queryset

        mock_serializer_class = Mock()
        self.view.get_serializer_class = Mock(return_value=mock_serializer_class)
        mock_serializer_class.setup_eager_loading.return_value = "final_queryset"

        result = self.view.get_queryset()

        mock_permission_manager.assert_called_with(
            user=self.view.request.user,
            company_ids=uuid.UUID(company_id),
            model="ReportingMessage",
        )
        mock_permission_instance.get_allowed_queryset.assert_called_once()

        mock_none.assert_called_once()
        mock_join_queryset.assert_called_with(None, mock_none_queryset)

        mock_serializer_class.setup_eager_loading.assert_called_with(
            mock_joined_queryset.distinct()
        )

        self.assertEqual(result, "final_queryset")

    @patch("apps.reportings.views.ReportingMessage.objects.filter")
    def test_get_queryset_non_list_action(self, mock_filter):
        self.view.action = "retrieve"

        user_companies = ["company1", "company2"]
        self.view.request.user.companies.all.return_value = user_companies

        mock_filtered_queryset = Mock()
        mock_filter.return_value = mock_filtered_queryset

        mock_serializer_class = Mock()
        self.view.get_serializer_class = Mock(return_value=mock_serializer_class)
        mock_serializer_class.setup_eager_loading.return_value = "final_queryset"

        result = self.view.get_queryset()

        self.view.request.user.companies.all.assert_called_once()
        mock_filter.assert_called_with(reporting__company_id__in=user_companies)

        mock_serializer_class.setup_eager_loading.assert_called_with(
            mock_filtered_queryset.distinct()
        )
        self.assertEqual(result, "final_queryset")
