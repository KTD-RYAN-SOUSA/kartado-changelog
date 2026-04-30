import uuid
from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

from apps.reportings.views import ReportingFileFilter

pytestmark = pytest.mark.django_db


class ReportingFileFilterTestCase(TestCase):
    def setUp(self):
        self.filter = ReportingFileFilter()
        self.queryset = Mock()
        self.queryset.filter.return_value = self.queryset
        self.queryset.distinct.return_value = self.queryset
        self.queryset.none.return_value = self.queryset
        self.queryset.values_list.return_value = self.queryset
        self.filter.request = Mock()
        self.filter.data = {"company": str(uuid.uuid4())}

    def test_get_measurement_with_value(self):
        result = self.filter.get_measurement(
            self.queryset, "measurement", "123,456,789"
        )
        self.queryset.filter.assert_called_with(
            reporting__reporting_usage__measurement_id__in=["123", "456", "789"]
        )
        self.queryset.distinct.assert_called_once()
        self.assertEqual(result, self.queryset)

    def test_get_measurement_without_value(self):
        result = self.filter.get_measurement(self.queryset, "measurement", "")
        self.assertEqual(result, self.queryset)
        self.queryset.filter.assert_not_called()

    @patch("apps.reportings.views.Company.objects.get")
    @patch("apps.reportings.views.get_uuids_jobs_user_firms")
    @patch("apps.reportings.views.get_uuids_rdos_user_firms")
    def test_get_jobs_rdos_user_firms_with_both(
        self, mock_get_rdos, mock_get_jobs, mock_company_get
    ):
        mock_company = Mock()
        mock_company.uuid = uuid.uuid4()
        mock_company_get.return_value = mock_company

        mock_get_jobs.return_value = ["job1", "job2"]
        mock_get_rdos.return_value = ["rdo1", "rdo2"]

        jobs_queryset = Mock()
        jobs_queryset.values_list.return_value = ["file1", "file2"]

        files_queryset = Mock()
        files_queryset.values_list.return_value = ["file3", "file4"]

        reportings_queryset = Mock()
        reportings_queryset.values_list.return_value = ["file5", "file6"]

        self.queryset.filter.side_effect = [
            jobs_queryset,
            files_queryset,
            reportings_queryset,
            self.queryset,
        ]

        result = self.filter.get_jobs_rdos_user_firms(
            self.queryset, "jobs_rdos_user_firms", "jobs|rdos"
        )

        mock_company_get.assert_called_with(uuid=self.filter.data["company"])
        mock_get_jobs.assert_called_with("jobs", mock_company, self.filter.request.user)
        mock_get_rdos.assert_called_with("rdos", mock_company, self.filter.request.user)

        self.queryset.filter.assert_any_call(
            reporting__company_id=mock_company.uuid,
            reporting__job_id__in=["job1", "job2"],
        )
        self.queryset.filter.assert_any_call(
            reporting__company_id=mock_company.uuid,
            reporting_file_multipledailyreports__in=["rdo1", "rdo2"],
        )
        self.queryset.filter.assert_any_call(
            reporting__company_id=mock_company.uuid,
            reporting__reporting_multiple_daily_reports__in=["rdo1", "rdo2"],
        )

        expected_ids = set(["file1", "file2", "file3", "file4", "file5", "file6"])
        self.queryset.filter.assert_called_with(uuid__in=expected_ids)

        self.assertEqual(result, self.queryset)

    @patch("apps.reportings.views.Company.objects.get")
    @patch("apps.reportings.views.get_uuids_jobs_user_firms")
    @patch("apps.reportings.views.get_uuids_rdos_user_firms")
    def test_get_jobs_rdos_user_firms_no_results(
        self, mock_get_rdos, mock_get_jobs, mock_company_get
    ):
        mock_company = Mock()
        mock_company_get.return_value = mock_company

        mock_get_jobs.return_value = []
        mock_get_rdos.return_value = []

        result = self.filter.get_jobs_rdos_user_firms(
            self.queryset, "jobs_rdos_user_firms", "jobs|rdos"
        )

        self.queryset.none.assert_called_once()
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
    def test_get_num_user_firms_no_company(self, mock_company_get):
        self.filter.data = {}
        result = self.filter.get_num_user_firms(
            self.queryset, "num_user_firms", "5,firm_uuid1,firm_uuid2"
        )

        mock_company_get.assert_not_called()
        self.assertEqual(result, self.queryset)
