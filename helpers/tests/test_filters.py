import json
import uuid
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Q, QuerySet
from django.test import RequestFactory, TestCase
from django.utils import timezone
from rest_framework import serializers

from helpers.filters import (
    BaseModelFilterSet,
    DateFromToRangeCustomFilter,
    DateTzFilter,
    FilterSetWithInitialValues,
    JSONFieldOrderingFilter,
    KeyFilter,
    ListFilter,
    ListRangeFilter,
    UUIDListFilter,
    annotate_datetime,
    queryset_with_timezone,
    reporting_expired_filter,
)

pytestmark = pytest.mark.django_db


class MockModel(models.Model):
    """Mock model for testing"""

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    form_data = models.JSONField(default=dict)
    due_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, null=True, blank=True
    )
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, null=True, blank=True
    )

    class Meta:
        app_label = "test"


class TestUtilityFunctions(TestCase):
    """Tests for utility functions in filters"""

    def test_annotate_datetime(self):
        """Test annotate_datetime function"""
        # Create a mock queryset
        mock_qs = Mock(spec=QuerySet)
        mock_qs.annotate.return_value = mock_qs

        result = annotate_datetime(mock_qs, "form_data__date_field")

        # Verify annotate was called with correct parameters
        mock_qs.annotate.assert_called_once()
        self.assertEqual(result, mock_qs)

    def test_reporting_expired_filter_expired(self):
        """Test reporting_expired_filter with expired filter"""
        mock_queryset = Mock(spec=QuerySet)
        mock_queryset.filter.return_value.distinct.return_value = mock_queryset

        with patch("helpers.filters.timezone.now") as mock_now:
            mock_now.return_value = timezone.now()
            result = reporting_expired_filter(mock_queryset, "expired")

        # Verify filter was called
        mock_queryset.filter.assert_called_once()
        mock_queryset.filter.return_value.distinct.assert_called_once()
        self.assertEqual(result, mock_queryset)

    def test_reporting_expired_filter_invalid_values(self):
        """Test reporting_expired_filter with invalid filter values"""
        mock_queryset = Mock(spec=QuerySet)

        result = reporting_expired_filter(mock_queryset, "invalid_filter")

        # Should return original queryset unchanged
        self.assertEqual(result, mock_queryset)

    def test_reporting_expired_filter_multiple_values(self):
        """Test reporting_expired_filter with multiple valid filter values"""
        mock_queryset = Mock(spec=QuerySet)
        mock_queryset.filter.return_value.distinct.return_value = mock_queryset

        with patch("helpers.filters.timezone.now") as mock_now:
            mock_now.return_value = timezone.now()
            result = reporting_expired_filter(
                mock_queryset, "expired,expired_not_executed"
            )

        mock_queryset.filter.assert_called_once()
        self.assertEqual(result, mock_queryset)


class TestJSONFieldOrderingFilter(TestCase):
    """Tests for JSONFieldOrderingFilter class"""

    def setUp(self):
        """Set up test filter instance"""
        self.filter = JSONFieldOrderingFilter()
        self.filter.model_name = "test_model"
        self.factory = RequestFactory()

        # Mock view
        self.mock_view = Mock()
        self.mock_view.ordering_fields = ["form_data__test_field", "name"]

    def test_get_order_by_fields(self):
        """Test get_order_by_fields method"""
        request = self.factory.get("/test/?ordering=form_data__test_field")
        mock_queryset = Mock(spec=QuerySet)

        with patch.object(
            self.filter, "get_ordering", return_value=["form_data__test_field"]
        ):
            result = self.filter.get_order_by_fields(
                request, mock_queryset, self.mock_view
            )

        self.assertEqual(result, ["form_data__test_field"])

    def test_validate_fields_field_not_exists(self):
        """Test validate_fields with non-existent field"""
        mock_queryset = Mock(spec=QuerySet)
        mock_model = Mock()
        mock_model._meta.get_field.side_effect = FieldDoesNotExist()
        mock_queryset.model = mock_model

        with self.assertRaises(serializers.ValidationError):
            self.filter.validate_fields(
                ["nonexistent_field"], self.mock_view, mock_queryset
            )

    def test_get_json_fields(self):
        """Test get_json_fields method"""
        stripped_fields = ["form_data__test_field", "name", "form_data__another_field"]

        result = self.filter.get_json_fields(stripped_fields)

        expected = ["form_data__test_field", "form_data__another_field"]
        self.assertEqual(result, expected)

    def test_get_json_fields_too_nested(self):
        """Test get_json_fields with too many nested accesses"""
        stripped_fields = ["form_data__level1__level2__level3"]

        with self.assertRaises(serializers.ValidationError):
            self.filter.get_json_fields(stripped_fields)

    @patch("helpers.filters.dict_to_casing")
    def test_get_type_lookup(self, mock_dict_to_casing):
        """Test get_type_lookup method"""
        mock_queryset = Mock(spec=QuerySet)
        mock_queryset.values_list.return_value = [
            [{"api_name": "test_field", "data_type": "string"}],
            [{"api_name": "number_field", "data_type": "number"}],
        ]

        mock_dict_to_casing.return_value = [
            [{"api_name": "test_field", "data_type": "string"}],
            [{"api_name": "number_field", "data_type": "number"}],
        ]

        result = self.filter.get_type_lookup(mock_queryset)

        # Should return dict with field mappings
        self.assertIsInstance(result, dict)

    def test_get_ordered_queryset(self):
        """Test get_ordered_queryset method"""
        mock_queryset = Mock(spec=QuerySet)
        mock_queryset.order_by.return_value = mock_queryset

        order_by_fields = ["name", "-form_data__test"]

        result = self.filter.get_ordered_queryset(mock_queryset, order_by_fields)

        mock_queryset.order_by.assert_called_once()
        self.assertEqual(result, mock_queryset)


class TestKeyFilter(TestCase):
    """Tests for KeyFilter class"""

    def setUp(self):
        """Set up test filter instance"""
        self.filter = KeyFilter(field_name="form_data")

    def test_filter_empty_value(self):
        """Test filter with empty value"""
        mock_qs = Mock(spec=QuerySet)

        result = self.filter.filter(mock_qs, "")

        self.assertEqual(result, mock_qs)

    def test_filter_invalid_json(self):
        """Test filter with invalid JSON"""
        mock_qs = Mock(spec=QuerySet)

        with self.assertRaises(serializers.ValidationError):
            self.filter.filter(mock_qs, "invalid json")

    @patch("helpers.filters.path_from_dict")
    def test_filter_valid_json_string(self, mock_path_from_dict):
        """Test filter with valid JSON string value"""
        mock_qs = Mock(spec=QuerySet)
        mock_qs.filter.return_value = mock_qs
        mock_path_from_dict.return_value = {"name": "test_value"}

        json_value = '{"name": "test_value"}'

        result = self.filter.filter(mock_qs, json_value)

        mock_qs.filter.assert_called_once()
        self.assertEqual(result, mock_qs)

    @patch("helpers.filters.path_from_dict")
    def test_filter_with_datetime_value(self, mock_path_from_dict):
        """Test filter with datetime value"""
        mock_qs = Mock(spec=QuerySet)
        mock_qs.filter.return_value = mock_qs
        mock_qs.exists.return_value = True

        test_datetime = datetime.now()
        mock_path_from_dict.return_value = {"date_field__gte": test_datetime}

        with patch("helpers.filters.annotate_datetime", return_value=mock_qs):
            json_value = json.dumps({"date_field__gte": test_datetime.isoformat()})
            result = self.filter.filter(mock_qs, json_value)

        mock_qs.filter.assert_called_once()
        mock_qs.exists.assert_called_once()
        self.assertEqual(result, mock_qs)


class TestUUIDListFilter(TestCase):
    """Tests for UUIDListFilter class"""

    def setUp(self):
        """Set up test filter instance"""
        self.filter = UUIDListFilter(field_name="uuid")

    def test_filter_valid_uuids(self):
        """Test filter with valid UUIDs"""
        mock_qs = Mock(spec=QuerySet)
        mock_qs.distinct.return_value = mock_qs

        valid_uuid1 = str(uuid.uuid4())
        valid_uuid2 = str(uuid.uuid4())
        uuid_list = f"{valid_uuid1},{valid_uuid2}"

        with patch.object(ListFilter, "filter", return_value=mock_qs):
            result = self.filter.filter(mock_qs, uuid_list)

        self.assertEqual(result, mock_qs)

    def test_filter_invalid_uuids(self):
        """Test filter with invalid UUIDs"""
        mock_qs = Mock(spec=QuerySet)

        with self.assertRaises(serializers.ValidationError):
            self.filter.filter(mock_qs, "invalid-uuid,another-invalid")


class TestListRangeFilter(TestCase):
    """Tests for ListRangeFilter class"""

    def setUp(self):
        """Set up test filter instance"""
        self.filter = ListRangeFilter(field_name="value")

    def test_filter_empty_value(self):
        """Test filter with empty value"""
        mock_qs = Mock(spec=QuerySet)

        result = self.filter.filter(mock_qs, "")

        self.assertEqual(result, mock_qs)

    def test_filter_odd_number_values(self):
        """Test filter with odd number of values (should raise exception)"""
        mock_qs = Mock(spec=QuerySet)

        with self.assertRaises(Exception):
            self.filter.filter(mock_qs, "1,10,20")

    def test_filter_single_range(self):
        """Test filter with single range uses Q object"""
        mock_qs = Mock(spec=QuerySet)
        mock_filtered_qs = Mock(spec=QuerySet)
        mock_qs.filter.return_value = mock_filtered_qs

        result = self.filter.filter(mock_qs, "0,100")

        mock_qs.filter.assert_called_once()
        call_args = mock_qs.filter.call_args
        q_object = call_args[0][0]
        self.assertIsInstance(q_object, Q)
        self.assertEqual(result, mock_filtered_qs)

    def test_filter_multiple_ranges(self):
        """Test filter with multiple ranges uses Q objects with OR"""
        mock_qs = Mock(spec=QuerySet)
        mock_filtered_qs = Mock(spec=QuerySet)
        mock_qs.filter.return_value = mock_filtered_qs

        result = self.filter.filter(mock_qs, "0,100,200,300")

        mock_qs.filter.assert_called_once()
        call_args = mock_qs.filter.call_args
        q_object = call_args[0][0]
        self.assertIsInstance(q_object, Q)
        self.assertEqual(result, mock_filtered_qs)

    def test_filter_overlapping_ranges_no_union(self):
        """Test that overlapping ranges use Q with OR, not queryset union"""
        mock_qs = Mock(spec=QuerySet)
        mock_filtered_qs = Mock(spec=QuerySet)
        mock_qs.filter.return_value = mock_filtered_qs

        result = self.filter.filter(mock_qs, "0,100,0,50")

        # Should call filter once with Q object, not use queryset union (|)
        mock_qs.filter.assert_called_once()

        # Should not call distinct (removed from filter)
        mock_filtered_qs.distinct.assert_not_called()
        self.assertEqual(result, mock_filtered_qs)


class TestQuerysetWithTimezone(TestCase):
    """Tests for queryset_with_timezone function"""

    def test_queryset_with_timezone_datetime(self):
        """Test queryset_with_timezone with datetime field"""
        mock_qs = Mock(spec=QuerySet)
        mock_qs.annotate.return_value = mock_qs

        result = queryset_with_timezone(
            mock_qs, "created_at", "tz_created_at", is_date=False
        )

        mock_qs.annotate.assert_called_once()
        self.assertEqual(result, mock_qs)

    def test_queryset_with_timezone_date(self):
        """Test queryset_with_timezone with date field"""
        mock_qs = Mock(spec=QuerySet)
        mock_qs.annotate.return_value = mock_qs

        result = queryset_with_timezone(
            mock_qs, "created_at", "tz_created_at", is_date=True
        )

        mock_qs.annotate.assert_called_once()
        self.assertEqual(result, mock_qs)


class TestDateTzFilter(TestCase):
    """Tests for DateTzFilter class"""

    def setUp(self):
        """Set up test filter instance"""
        self.filter = DateTzFilter(field_name="created_at")

    def test_filter_empty_value(self):
        """Test filter with empty value"""
        mock_qs = Mock(spec=QuerySet)

        result = self.filter.filter(mock_qs, "")

        self.assertEqual(result, mock_qs)

    @patch("helpers.filters.date_tz")
    def test_filter_valid_date(self, mock_date_tz):
        """Test filter with valid date"""
        mock_qs = Mock(spec=QuerySet)
        mock_date_tz.return_value = timezone.now().date()

        with patch.object(DateTzFilter.__bases__[0], "filter", return_value=mock_qs):
            result = self.filter.filter(mock_qs, "2023-01-01")

        mock_date_tz.assert_called_once_with("2023-01-01")
        self.assertEqual(result, mock_qs)


class TestDateFromToRangeCustomFilter(TestCase):
    """Tests for DateFromToRangeCustomFilter class"""

    def setUp(self):
        """Set up test filter instance"""
        self.filter = DateFromToRangeCustomFilter(field_name="created_at")
        self.filter.parent = Mock()
        self.filter.parent.request.query_params = {}

    def test_filter_empty_value(self):
        """Test filter with empty value"""
        mock_qs = Mock(spec=QuerySet)

        result = self.filter.filter(mock_qs, None)

        self.assertEqual(result, mock_qs)

    @patch("helpers.filters.queryset_with_timezone")
    def test_filter_with_range_no_distinct(self, mock_qs_tz):
        """Test filter with start and stop does not apply distinct by default"""
        mock_qs = Mock(spec=QuerySet)
        mock_annotated_qs = Mock(spec=QuerySet)
        mock_filtered_qs = Mock(spec=QuerySet)
        mock_qs_tz.return_value = mock_annotated_qs
        mock_annotated_qs.filter.return_value = mock_filtered_qs

        mock_value = Mock()
        mock_value.start = datetime(2023, 1, 1)
        mock_value.stop = datetime(2023, 12, 31)

        result = self.filter.filter(mock_qs, mock_value)

        # Should not call distinct by default
        mock_filtered_qs.distinct.assert_not_called()
        self.assertEqual(result, mock_filtered_qs)

    @patch("helpers.filters.queryset_with_timezone")
    def test_filter_with_start_only(self, mock_qs_tz):
        """Test filter with only start date uses gte lookup"""
        mock_qs = Mock(spec=QuerySet)
        mock_annotated_qs = Mock(spec=QuerySet)
        mock_filtered_qs = Mock(spec=QuerySet)
        mock_qs_tz.return_value = mock_annotated_qs
        mock_annotated_qs.filter.return_value = mock_filtered_qs

        mock_value = Mock()
        mock_value.start = datetime(2023, 1, 1)
        mock_value.stop = None

        result = self.filter.filter(mock_qs, mock_value)

        self.assertEqual(self.filter.lookup_expr, "gte")
        self.assertEqual(result, mock_filtered_qs)

    @patch("helpers.filters.queryset_with_timezone")
    def test_filter_with_stop_only(self, mock_qs_tz):
        """Test filter with only stop date uses lte lookup"""
        mock_qs = Mock(spec=QuerySet)
        mock_annotated_qs = Mock(spec=QuerySet)
        mock_filtered_qs = Mock(spec=QuerySet)
        mock_qs_tz.return_value = mock_annotated_qs
        mock_annotated_qs.filter.return_value = mock_filtered_qs

        mock_value = Mock()
        mock_value.start = None
        mock_value.stop = datetime(2023, 12, 31)

        result = self.filter.filter(mock_qs, mock_value)

        self.assertEqual(self.filter.lookup_expr, "lte")
        self.assertEqual(result, mock_filtered_qs)


class TestFilterSetWithInitialValues(TestCase):
    """Tests for FilterSetWithInitialValues class"""

    def test_init_with_initial_values(self):
        """Test initialization with initial values"""
        # Create a mock filter with initial value
        mock_filter = Mock()
        mock_filter.extra = {"initial": "default_value"}

        # Mock data without the field
        mock_data = Mock()
        mock_data.copy.return_value = {"other_field": "value"}
        mock_data.get.return_value = None  # Field not present

        with patch.object(
            FilterSetWithInitialValues, "base_filters", {"test_field": mock_filter}
        ):
            with patch.object(FilterSetWithInitialValues.__bases__[0], "__init__"):
                FilterSetWithInitialValues(data=mock_data)

        # Verify data.copy was called
        mock_data.copy.assert_called_once()


class TestBaseModelFilterSet(TestCase):
    """Tests for BaseModelFilterSet class"""

    def test_meta_fields(self):
        """Test that BaseModelFilterSet has correct Meta fields"""
        expected_fields = ["uuid", "created_by", "company", "created_at", "updated_at"]

        self.assertEqual(BaseModelFilterSet.Meta.fields, expected_fields)


class TestListFilter:
    def setup_method(self):
        self.qs = MockQuerySet()

    def test_empty_value(self):
        filter_instance = ListFilter()
        result = filter_instance.filter(self.qs, "")
        assert result == self.qs

    def test_single_value(self):
        filter_instance = ListFilter()
        filter_instance.field_name = "test_field"
        result = filter_instance.filter(self.qs, "value1")

        assert self.qs.filtered
        assert self.qs.filter_kwargs == {"test_field__in": ["value1"]}
        assert result.distinct_called

    def test_multiple_values(self):
        filter_instance = ListFilter()
        filter_instance.field_name = "test_field"
        result = filter_instance.filter(self.qs, "value1,value2,value3")

        assert self.qs.filtered
        assert self.qs.filter_kwargs == {
            "test_field__in": ["value1", "value2", "value3"]
        }
        assert result.distinct_called

    def test_null_allowed_only_null(self):
        filter_instance = ListFilter(allow_null=True)
        filter_instance.field_name = "test_field"
        result = filter_instance.filter(self.qs, "null")

        assert self.qs.filtered
        assert self.qs.filter_kwargs == {"test_field__isnull": True}
        assert result.distinct_called

    def test_null_allowed_with_values(self):
        filter_instance = ListFilter(allow_null=True)
        filter_instance.field_name = "test_field"
        result = filter_instance.filter(self.qs, "null,value1")

        assert self.qs.filtered
        assert self.qs.q_object_used
        assert result.distinct_called

    def test_validator_valid_values(self):
        def valid_validator(values):
            return all(len(v) > 3 for v in values)

        filter_instance = ListFilter(validator=valid_validator)
        filter_instance.field_name = "test_field"
        result = filter_instance.filter(self.qs, "value1,value2")

        assert self.qs.filtered
        assert self.qs.filter_kwargs == {"test_field__in": ["value1", "value2"]}
        assert result.distinct_called

    def test_validator_invalid_values(self):
        def invalid_validator(values):
            return all(len(v) > 10 for v in values)

        filter_instance = ListFilter(validator=invalid_validator)
        filter_instance.field_name = "test_field"

        with pytest.raises(serializers.ValidationError) as exc_info:
            filter_instance.filter(self.qs, "value1,value2")

        assert (
            "kartado.error.filters.at_least_one_invalid_filter_value_was_provided"
            in str(exc_info.value)
        )

    def test_validator_with_null_allowed(self):
        def valid_validator(values):
            return all(len(v) > 3 for v in values)

        filter_instance = ListFilter(allow_null=True, validator=valid_validator)
        filter_instance.field_name = "test_field"
        result = filter_instance.filter(self.qs, "null,value1")

        assert self.qs.filtered
        assert self.qs.q_object_used
        assert result.distinct_called


# Helper class to simulate the behavior of a Django queryset
class MockQuerySet:
    def __init__(self):
        self.filtered = False
        self.filter_kwargs = {}
        self.q_object_used = False
        self.distinct_called = False

    def filter(self, *args, **kwargs):
        self.filtered = True

        if args and isinstance(args[0], Q):
            self.q_object_used = True
        else:
            self.filter_kwargs = kwargs

        result = self
        result.distinct_called = False
        return result

    def distinct(self):
        self.distinct_called = True
        return self
