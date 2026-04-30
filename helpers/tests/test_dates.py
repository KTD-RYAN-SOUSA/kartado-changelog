from datetime import datetime, timezone

import pytest
from django.test import TestCase, override_settings
from rest_framework.serializers import ValidationError

from helpers.dates import (
    convent_creation_date_to_datetime,
    date_tz,
    format_date,
    get_date_before,
    get_dates_by_frequency,
    get_first_and_last_day_of_month,
    is_first_work_day_month,
    parse_dict_dates,
    parse_dict_dates_tz,
    to_datetime_str,
    to_utc_string,
    utc_to_local,
)

pytestmark = pytest.mark.django_db


class TestDateTz(TestCase):
    """Tests for date_tz function"""

    def test_date_tz_valid_date_string(self):
        """Test conversion of valid date string to timezone-aware datetime"""
        result = date_tz("2023-08-22 15:30:00")
        assert result is not None
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_date_tz_invalid_date_string(self):
        """Test that invalid date string raises ValidationError"""
        with pytest.raises(ValidationError, match="Data inválida"):
            date_tz("invalid date")

    def test_date_tz_end_of_day(self):
        """Test that end_of_the_day=True sets time to 23:59:59"""
        result = date_tz("2023-08-22", end_of_the_day=True)
        assert result.hour == 23
        assert result.minute == 59
        assert result.second == 59

    def test_date_tz_without_end_of_day(self):
        """Test that end_of_the_day=False preserves original time"""
        result = date_tz("2023-08-22 10:30:00", end_of_the_day=False)
        assert result.hour == 10
        assert result.minute == 30

    @override_settings(TIME_ZONE="America/Sao_Paulo")
    def test_date_tz_with_timezone(self):
        """Test that timezone is properly applied"""
        result = date_tz("2023-08-22 15:30:00")
        assert result.tzinfo is not None


class TestFormatDate(TestCase):
    """Tests for format_date function"""

    def test_format_date_valid_string(self):
        """Test formatting of valid date string"""
        result = format_date("2023-08-22 14:30:00")
        assert result == "2023-08-22T14:30"

    def test_format_date_invalid_string(self):
        """Test that invalid date string returns empty string"""
        result = format_date("invalid date")
        assert result == ""

    def test_format_date_with_milliseconds(self):
        """Test formatting date with milliseconds"""
        result = format_date("2023-08-22 14:30:45.123456")
        assert result == "2023-08-22T14:30"

    def test_format_date_iso_format(self):
        """Test formatting ISO format date"""
        result = format_date("2023-08-22T14:30:00")
        assert result == "2023-08-22T14:30"


class TestGetDateBefore(TestCase):
    """Tests for get_date_before function"""

    def test_get_date_before_single_hour(self):
        """Test with single hour in hours_list"""
        time_now = datetime(2023, 8, 22, 15, 30)
        result = get_date_before([10], time_now)
        assert result.hour == 10
        assert result.day == time_now.day

    def test_get_date_before_current_before_first_hour(self):
        """Test when current hour is before first hour in list"""
        time_now = datetime(2023, 8, 22, 8, 30)
        result = get_date_before([10, 14, 18], time_now)
        assert result.hour == 18
        assert result.day == 21  # Previous day

    def test_get_date_before_current_after_last_hour(self):
        """Test when current hour is after last hour in list"""
        time_now = datetime(2023, 8, 22, 20, 30)
        result = get_date_before([10, 14, 18], time_now)
        assert result.hour == 18
        assert result.day == 22  # Same day

    def test_get_date_before_current_between_hours(self):
        """Test when current hour is between hours in list"""
        time_now = datetime(2023, 8, 22, 12, 30)
        result = get_date_before([10, 14, 18], time_now)
        assert result.hour == 10
        assert result.day == 22

    def test_get_date_before_invalid_input(self):
        """Test with invalid input (not datetime)"""
        result = get_date_before([10, 14, 18], "not a datetime")
        assert result is False


class TestUtcToLocal(TestCase):
    """Tests for utc_to_local function"""

    def test_utc_to_local_conversion(self):
        """Test UTC to local timezone conversion"""
        utc_time = datetime(2023, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        result = utc_to_local(utc_time)
        assert result is not None
        assert isinstance(result, datetime)
        # The result should be in local timezone
        assert result.tzinfo is not None

    def test_utc_to_local_preserves_moment(self):
        """Test that conversion preserves the same moment in time"""
        utc_time = datetime(2023, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        result = utc_to_local(utc_time)
        # Both should represent the same moment
        assert utc_time.timestamp() == result.timestamp()


class TestToUtcString(TestCase):
    """Tests for to_utc_string function"""

    def test_to_utc_string_valid_datetime(self):
        """Test conversion of datetime to UTC string"""
        dt = datetime(2023, 8, 22, 15, 30, 0)
        result = to_utc_string(dt)
        assert isinstance(result, str)
        assert "/" in result
        assert "," in result

    def test_to_utc_string_with_timezone(self):
        """Test conversion of timezone-aware datetime"""
        dt = datetime(2023, 8, 22, 15, 30, 0, tzinfo=timezone.utc)
        result = to_utc_string(dt)
        assert result == "22/08/2023, 15:30:00"


class TestToDatetimeStr(TestCase):
    """Tests for to_datetime_str function"""

    def test_to_datetime_str_valid_format(self):
        """Test conversion of valid string to datetime"""
        result = to_datetime_str("22/08/2023, 15:30:00")
        assert result is not None
        assert isinstance(result, datetime)
        assert result.day == 22
        assert result.month == 8
        assert result.year == 2023
        assert result.hour == 15
        assert result.minute == 30

    def test_to_datetime_str_invalid_format(self):
        """Test that invalid format returns None"""
        result = to_datetime_str("invalid date")
        assert result is None

    def test_to_datetime_str_wrong_format(self):
        """Test that wrong format returns None"""
        result = to_datetime_str("2023-08-22 15:30:00")
        assert result is None


class TestParseDictDates(TestCase):
    """Tests for parse_dict_dates function"""

    def test_parse_dict_dates_top_level_fields(self):
        """Test parsing of top-level date fields"""
        item = {
            "created_at": "22/08/2023, 15:30:00",
            "updated_at": "23/08/2023, 10:00:00",
        }
        result = parse_dict_dates(item, ["created_at", "updated_at"])
        assert isinstance(result["created_at"], datetime)
        assert isinstance(result["updated_at"], datetime)

    def test_parse_dict_dates_form_data_fields(self):
        """Test parsing of form_data date fields"""
        item = {
            "form_data": {
                "inspection_date": "22/08/2023, 15:30:00",
                "completion_date": "23/08/2023, 10:00:00",
            }
        }
        result = parse_dict_dates(
            item, [], form_data_date_fields=["inspection_date", "completion_date"]
        )
        assert isinstance(result["form_data"]["inspection_date"], datetime)
        assert isinstance(result["form_data"]["completion_date"], datetime)

    def test_parse_dict_dates_mixed_fields(self):
        """Test parsing of both top-level and form_data fields"""
        item = {
            "created_at": "22/08/2023, 15:30:00",
            "form_data": {"inspection_date": "23/08/2023, 10:00:00"},
        }
        result = parse_dict_dates(
            item, ["created_at"], form_data_date_fields=["inspection_date"]
        )
        assert isinstance(result["created_at"], datetime)
        assert isinstance(result["form_data"]["inspection_date"], datetime)

    def test_parse_dict_dates_missing_fields(self):
        """Test that missing fields are handled gracefully"""
        item = {"other_field": "value"}
        result = parse_dict_dates(item, ["created_at", "updated_at"])
        assert "other_field" in result
        assert "created_at" not in result

    def test_parse_dict_dates_none_values(self):
        """Test that None values are handled gracefully"""
        item = {"created_at": None}
        result = parse_dict_dates(item, ["created_at"])
        assert result["created_at"] is None


class TestParseDictDatesTz(TestCase):
    """Tests for parse_dict_dates_tz function"""

    def test_parse_dict_dates_tz_top_level_fields(self):
        """Test parsing of top-level date fields with timezone"""
        item = {
            "created_at": "2023-08-22 15:30:00",
            "updated_at": "2023-08-23 10:00:00",
        }
        result = parse_dict_dates_tz(item, ["created_at", "updated_at"])
        assert isinstance(result["created_at"], datetime)
        assert isinstance(result["updated_at"], datetime)
        assert result["created_at"].tzinfo is not None

    def test_parse_dict_dates_tz_form_data_fields(self):
        """Test parsing of form_data date fields with timezone"""
        item = {
            "form_data": {
                "inspection_date": "2023-08-22 15:30:00",
                "completion_date": "2023-08-23 10:00:00",
            }
        }
        result = parse_dict_dates_tz(
            item, [], form_data_date_fields=["inspection_date", "completion_date"]
        )
        assert isinstance(result["form_data"]["inspection_date"], datetime)
        assert result["form_data"]["inspection_date"].tzinfo is not None


class TestGetFirstAndLastDayOfMonth(TestCase):
    """Tests for get_first_and_last_day_of_month function"""

    def test_get_first_and_last_day_regular_month(self):
        """Test first and last day of a regular month"""
        first_day, last_day = get_first_and_last_day_of_month(8, 2023)
        assert first_day.day == 1
        assert first_day.month == 8
        assert first_day.year == 2023
        assert last_day.day == 31
        assert last_day.month == 8
        assert last_day.year == 2023

    def test_get_first_and_last_day_february_non_leap(self):
        """Test February in non-leap year"""
        first_day, last_day = get_first_and_last_day_of_month(2, 2023)
        assert first_day.day == 1
        assert last_day.day == 28

    def test_get_first_and_last_day_february_leap(self):
        """Test February in leap year"""
        first_day, last_day = get_first_and_last_day_of_month(2, 2024)
        assert first_day.day == 1
        assert last_day.day == 29

    def test_get_first_and_last_day_december(self):
        """Test December (edge case)"""
        first_day, last_day = get_first_and_last_day_of_month(12, 2023)
        assert first_day.day == 1
        assert first_day.month == 12
        assert last_day.day == 31
        assert last_day.month == 12


class TestIsFirstWorkDayMonth(TestCase):
    """Tests for is_first_work_day_month function"""

    def test_is_first_work_day_month_true(self):
        """Test when date is the first work day of month"""
        # First Monday of August 2023 is the 7th (after weekend)
        # But first weekday is actually Tuesday Aug 1st
        date = datetime(2023, 8, 1)  # Tuesday
        result = is_first_work_day_month(date)
        assert result is True

    def test_is_first_work_day_month_false(self):
        """Test when date is not the first work day"""
        date = datetime(2023, 8, 2)  # Wednesday, not first work day
        result = is_first_work_day_month(date)
        assert result is False

    def test_is_first_work_day_month_weekend(self):
        """Test with weekend date"""
        date = datetime(2023, 8, 5)  # Saturday
        result = is_first_work_day_month(date)
        assert result is False


class TestGetDatesByFrequency(TestCase):
    """Tests for get_dates_by_frequency function"""

    def test_get_dates_by_frequency_day(self):
        """Test daily frequency"""
        start = datetime(2023, 8, 1)
        end = datetime(2023, 8, 5)
        result = get_dates_by_frequency("day", start, end)
        assert len(result) > 0
        assert isinstance(result, list)

    def test_get_dates_by_frequency_week(self):
        """Test weekly frequency"""
        start = datetime(2023, 8, 1)
        end = datetime(2023, 8, 31)
        result = get_dates_by_frequency("week", start, end)
        assert len(result) > 0

    def test_get_dates_by_frequency_month(self):
        """Test monthly frequency"""
        start = datetime(2023, 1, 1)
        end = datetime(2023, 12, 31)
        result = get_dates_by_frequency("month", start, end)
        assert len(result) == 12

    def test_get_dates_by_frequency_invalid(self):
        """Test with invalid frequency"""
        start = datetime(2023, 8, 1)
        end = datetime(2023, 8, 31)
        with pytest.raises(ValidationError, match="Frequência inválida"):
            get_dates_by_frequency("invalid_frequency", start, end)

    def test_get_dates_by_frequency_bimester(self):
        """Test bimester frequency (every 2 months)"""
        start = datetime(2023, 1, 1)
        end = datetime(2023, 12, 31)
        result = get_dates_by_frequency("bimester", start, end)
        assert len(result) > 0

    def test_get_dates_by_frequency_semester(self):
        """Test semester frequency (every 6 months)"""
        start = datetime(2023, 1, 1)
        end = datetime(2023, 12, 31)
        result = get_dates_by_frequency("semester", start, end)
        assert len(result) > 0


class TestConventCreationDateToDatetime(TestCase):
    """Tests for convent_creation_date_to_datetime function"""

    def test_convent_creation_date_to_datetime_valid(self):
        """Test conversion of valid date string"""
        date_str = "2023-08-22T14:30:45.123456Z"
        result = convent_creation_date_to_datetime(date_str)
        assert isinstance(result, datetime)
        assert result.year == 2023
        assert result.month == 8
        assert result.day == 22
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 45
        assert result.tzinfo == timezone.utc

    def test_convent_creation_date_to_datetime_no_microseconds(self):
        """Test conversion without microseconds"""
        date_str = "2023-08-22T14:30:45.000000Z"
        result = convent_creation_date_to_datetime(date_str)
        assert result.microsecond == 0
