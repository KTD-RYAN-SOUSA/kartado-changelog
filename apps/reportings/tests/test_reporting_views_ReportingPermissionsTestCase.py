import functools
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.db.models import Q
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.reportings.views import ReportingFilter

pytestmark = pytest.mark.django_db


class ReportingFilterTestCase(TestCase):
    def setUp(self):
        self.filter = ReportingFilter()
        self.queryset = Mock()
        self.queryset.filter.return_value = self.queryset
        self.queryset.exclude.return_value = self.queryset
        self.queryset.annotate.return_value = self.queryset
        self.queryset.distinct.return_value = self.queryset
        self.filter.request = Mock()
        self.filter.data = {}

    def test_get_number_list(self):
        value = "123, 456, 789"
        self.filter.get_number_list(self.queryset, "number_list", value)

        expected_q = functools.reduce(
            lambda acc, x: acc | Q(number__icontains=x), ["123", "456", "789"], Q()
        )
        self.queryset.filter.assert_called_with(expected_q)
        self.queryset.distinct.assert_called_once()

        self.queryset.reset_mock()
        self.filter.get_number_list(self.queryset, "number_list", "")
        self.queryset.filter.assert_called_with(Q())

    def test_get_has_artesp_code(self):
        self.filter.get_has_artesp_code(self.queryset, "has_artesp_code", True)
        self.queryset.filter.assert_called_with(form_data__artesp_code__isnull=False)
        self.queryset.exclude.assert_called_with(form_data__artesp_code__exact="")

        self.queryset.reset_mock()
        self.filter.get_has_artesp_code(self.queryset, "has_artesp_code", False)
        self.queryset.filter.assert_called_with(form_data__artesp_code__isnull=True)

        self.queryset.reset_mock()
        result = self.filter.get_has_artesp_code(self.queryset, "has_artesp_code", None)
        self.assertEqual(result, self.queryset)
        self.queryset.filter.assert_not_called()

    def test_get_found_at_within_last_days(self):
        with patch("django.utils.timezone.now") as mock_now:
            now = timezone.now()
            mock_now.return_value = now

            self.filter.get_found_at_within_last_days(
                self.queryset, "found_at_within_last_days", "7"
            )

            self.queryset.filter.assert_called_with(
                found_at__gte=now - timedelta(days=7), found_at__lte=now
            )

        with self.assertRaises(ValidationError):
            self.filter.get_found_at_within_last_days(
                self.queryset, "found_at_within_last_days", "invalid"
            )

    def test_get_found_at_within_current_month(self):
        with patch("django.utils.timezone.now") as mock_now:
            now = timezone.now()
            mock_now.return_value = now

            self.filter.get_found_at_within_current_month(
                self.queryset, "found_at_within_current_month", True
            )

            self.queryset.filter.assert_called_with(
                found_at__month=now.month, found_at__year=now.year
            )

        self.queryset.reset_mock()
        with patch("django.utils.timezone.now") as mock_now:
            now = timezone.now()
            mock_now.return_value = now

            self.filter.get_found_at_within_current_month(
                self.queryset, "found_at_within_current_month", False
            )

            self.queryset.exclude.assert_called_with(
                found_at__month=now.month, found_at__year=now.year
            )

    def test_get_artesp_code(self):
        value = "Parcial 21/15 - SP 330, ABC 123, DEF456"
        self.filter.get_artesp_code(self.queryset, "artesp_code", value)

        expected_q = functools.reduce(
            lambda acc, x: acc | Q(form_data__artesp_code__icontains=x),
            ["Parcial 21/15 - SP 330", "ABC 123", "DEF456"],
            Q(),
        )
        self.queryset.filter.assert_called_with(expected_q)
        self.queryset.distinct.assert_called_once()

        self.queryset.reset_mock()
        self.filter.get_artesp_code(self.queryset, "artesp_code", "")
        self.queryset.filter.assert_called_with(Q())

    def test_get_any_km_exact(self):
        self.filter.get_any_km_exact(self.queryset, "any_km_exact", "123.45")

        expected_q = Q(km=123.45) | Q(end_km=123.45)
        self.queryset.filter.assert_called_with(expected_q)
        self.queryset.distinct.assert_called_once()

        with self.assertRaises(ValidationError):
            self.filter.get_any_km_exact(self.queryset, "any_km_exact", "invalid")

        self.queryset.reset_mock()
        result = self.filter.get_any_km_exact(self.queryset, "any_km_exact", "")
        self.assertEqual(result, self.queryset)
