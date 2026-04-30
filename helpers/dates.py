import calendar
import multiprocessing
from datetime import datetime, time, timedelta, timezone
from typing import Union

import pytz
from arrow import Arrow
from dateutil import parser
from django.conf import settings
from django.utils.timezone import make_aware
from rest_framework.serializers import ValidationError


def request_with_timeout(func, url, data, headers, kwargs, timeout):
    manager = multiprocessing.Manager()
    return_dict = manager.dict()

    # define a wrapper of `return_dict` to store the result.
    def function(return_dict):
        return_dict["value"] = func(url, data=data, headers=headers, **kwargs)

    p = multiprocessing.Process(target=function, args=(return_dict,))
    p.start()

    # Force a max. `timeout` or wait for the process to finish
    p.join(timeout)

    # If thread is still active, it didn't finish: raise TimeoutError
    if p.is_alive():
        p.terminate()
        p.join()
        raise TimeoutError
    else:
        return return_dict["value"]


def date_tz(value, end_of_the_day=False):
    """
    Add timezone to string date format and fix errors
    for Daylight Savings Time. Returns a datetime format
    """

    try:
        value = parser.parse(value)
    except Exception:
        raise ValidationError("Data inválida")

    if end_of_the_day:
        # set time to 23:59:59.9...
        value = datetime.combine(value, time.max)

    try:
        date = make_aware(value, timezone=pytz.timezone(settings.TIME_ZONE))
    except (pytz.NonExistentTimeError, pytz.AmbiguousTimeError):
        timezone = pytz.UTC
        date = timezone.localize(value, is_dst=False)
    except ValueError:
        date = value

    return date


def format_date(date_str: str) -> str:
    """
    Formats a date string into a consistent datetime format.

    Args:
        date_str (str): The date string to format

    Returns:
        str: The formatted date string in "YYYY-MM-DDThh:mm" format,
             or empty string if parsing fails

    Example:
        >>> format_date("2023-08-22 14:30:00")
        "2023-08-22T14:30"
        >>> format_date("invalid date")
        ""
    """

    try:
        value = parser.parse(date_str)
        value = value.strftime("%Y-%m-%dT%H:%M")
    except Exception:
        value = ""

    return value


def get_date_before(hours_list, time_now):
    if not isinstance(time_now, datetime):
        return False

    if len(hours_list) == 1:
        return time_now.replace(hour=hours_list[0])

    hour = time_now.hour
    if hour <= hours_list[0]:
        return time_now.replace(hour=hours_list[-1], day=time_now.day - 1)

    if hour > hours_list[-1]:
        return time_now.replace(hour=hours_list[-1])

    for i in range(len(hours_list) - 1):
        if (hour > hours_list[i]) and (hour <= hours_list[i + 1]):
            return time_now.replace(hour=hours_list[i])


def utc_to_local(utc_dt: datetime) -> datetime:
    """
    Converts a UTC datetime to the local timezone.

    Takes a datetime object in UTC and converts it to the system's local timezone
    while preserving the same point in time.

    Args:
        utc_dt (datetime): A datetime object in UTC timezone

    Returns:
        datetime: The same datetime converted to local timezone

    Example:
        >>> utc_time = datetime(2025, 8, 22, 12, 0, tzinfo=timezone.utc)
        >>> local_time = utc_to_local(utc_time)
        >>> print(local_time)  # Shows time in local timezone
        2025-08-22 09:00:00-03:00  # If in America/Sao_Paulo
    """

    utc_dt = utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)
    return utc_dt


def to_utc_string(value: datetime) -> str:
    """
    Converts a datetime object to a UTC-based string format.

    Takes a datetime object and converts it to UTC timezone if needed,
    then formats it as a string.

    Args:
        value (datetime): The datetime object to convert

    Returns:
        str: Formatted date string in "dd/mm/yyyy, HH:MM:SS" format in UTC

    Example:
        >>> dt = datetime(2023, 8, 22, 15, 30)
        >>> to_utc_string(dt)
        "22/08/2023, 15:30:00"
    """

    try:
        value_utc = make_aware(value, timezone=pytz.UTC)
    except Exception:
        value_utc = value
    return value_utc.strftime("%d/%m/%Y, %H:%M:%S")


def to_datetime_str(value: str) -> Union[datetime, None]:
    """
    Converts a string in specific format to a timezone-aware datetime.

    Parses a string in "dd/mm/yyyy, HH:MM:SS" format and converts it to
    a datetime with settings.TIME_ZONE timezone.

    Args:
        value (str): Date string in format "dd/mm/yyyy, HH:MM:SS"

    Returns:
        datetime: Timezone-aware datetime object using settings.TIME_ZONE,
                 or None if parsing fails

    Example:
        >>> dt = to_datetime_str("22/08/2023, 15:30:00")
        >>> print(dt)
        2023-08-22 15:30:00-03:00  # If TIME_ZONE is America/Sao_Paulo
        >>> dt = to_datetime_str("invalid")
        >>> print(dt)
        None
    """

    try:
        date_parsed = datetime.strptime(value, "%d/%m/%Y, %H:%M:%S")
        value_utc = make_aware(date_parsed, timezone=pytz.timezone(settings.TIME_ZONE))
    except Exception:
        value_utc = None
    return value_utc


def parse_dict_dates(
    item: dict, date_fields: list, form_data_date_fields: list = []
) -> dict:
    """
    Parses date strings in a dictionary and converts them to timezone-aware datetime objects.

    Processes date strings in both top-level dictionary fields and nested form_data fields.
    Uses to_datetime_str() to convert strings in "dd/mm/yyyy, HH:MM:SS" format.

    Args:
        item (dict): Dictionary containing date strings to parse
        date_fields (list): List of top-level field names containing dates
        form_data_date_fields (list, optional): List of field names in item["form_data"]
                                               containing dates. Defaults to [].

    Returns:
        dict: The input dictionary with date strings converted to datetime objects

    """

    for field in date_fields:
        if field in item and item[field]:
            item[field] = to_datetime_str(item[field])

    if "form_data" in item and item["form_data"]:
        for field in form_data_date_fields:
            if field in item["form_data"] and item["form_data"][field]:
                item["form_data"][field] = to_datetime_str(item["form_data"][field])

    return item


def parse_dict_dates_tz(item, date_fields, form_data_date_fields=[]):
    for field in date_fields:
        if field in item and item[field]:
            item[field] = date_tz(item[field])

    if "form_data" in item and item["form_data"]:
        for field in form_data_date_fields:
            if field in item["form_data"] and item["form_data"][field]:
                item["form_data"][field] = date_tz(item["form_data"][field])

    return item


def get_first_and_last_day_of_month(month, year):
    next_month = datetime(int(year), int(month), 1).replace(day=28) + timedelta(days=4)
    last_day_temp = next_month - timedelta(days=next_month.day)
    first_day_temp = last_day_temp.replace(day=1)
    last_day = datetime.combine(last_day_temp, time.max).replace(tzinfo=timezone.utc)
    first_day = datetime.combine(first_day_temp, time.min).replace(tzinfo=timezone.utc)
    return first_day, last_day


def is_first_work_day_month(date):
    cal = calendar.Calendar()
    month_range = list(cal.itermonthdays2(date.year, date.month))
    for item in month_range:
        if item[1] < 5 and item[0] > 0 and item[0] < date.day:
            return False
        if item[0] == date.day and item[1] < 5:
            return True

    return False


def get_dates_by_frequency(frequency, start, end):
    allowed_freq = [
        "day",
        "week",
        "fortnight",
        "month",
        "bimester",
        "quarter",
        "tertile",
        "semester",
        "year",
        "biennial",
    ]

    if frequency not in allowed_freq:
        raise ValidationError("Frequência inválida")

    if frequency in ["day", "week", "month", "quarter", "year"]:
        steps = list(Arrow.span_range(frequency, start, end, tz="America/Sao_Paulo"))
    if frequency in ["bimester", "tertile", "semester"]:
        mid_steps = list(Arrow.span_range("month", start, end, tz="America/Sao_Paulo"))
        if frequency == "bimester":
            steps = [
                (mid_steps[i - 1][0], dates[1])
                for i, dates in enumerate(mid_steps)
                if i % 2
            ]
        if frequency == "tertile":
            steps = [
                (mid_steps[i - 3][0], dates[1])
                for i, dates in enumerate(mid_steps)
                if not ((i + 1) % 4)
            ]
        if frequency == "semester":
            steps = [
                (mid_steps[i - 5][0], dates[1])
                for i, dates in enumerate(mid_steps)
                if not ((i + 1) % 6)
            ]
    if frequency == "biennial":
        mid_steps = list(Arrow.span_range("year", start, end, tz="America/Sao_Paulo"))
        steps = [
            (mid_steps[i - 1][0], dates[1])
            for i, dates in enumerate(mid_steps)
            if i % 2
        ]
    if frequency == "fortnight":
        steps = []
        mid_steps = list(Arrow.span_range("month", start, end, tz="America/Sao_Paulo"))
        for dates in mid_steps:
            steps.append((dates[0], dates[1].replace(day=15)))
            steps.append((dates[0].replace(day=16), dates[1]))

    return steps


def convent_creation_date_to_datetime(date_context):
    dt = datetime.strptime(date_context, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )
    return dt


def format_minutes(minutes):
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def format_minutes_decimal(minutes):
    hours = minutes // 60
    mins = (minutes % 60) / 60
    final_value = hours + mins
    return round(final_value, 2)


def minutes_between(start, end):
    """Calculate minutes in day and night periods between two times."""
    day_mins = 0
    night_mins = 0

    # Convert to datetime for easier calculation
    base_date = datetime.now().date()
    dt_start = datetime.combine(base_date, start)
    dt_end = datetime.combine(base_date, end)

    if dt_end <= dt_start:
        dt_end += timedelta(days=1)

    # Convert to minutes since midnight
    start_mins = start.hour * 60 + start.minute
    end_mins = (
        end.hour * 60 + end.minute + (24 * 60 if dt_end.date() > dt_start.date() else 0)
    )

    # Night period boundaries in minutes
    night_start = 22 * 60  # 22:00
    night_end = 5 * 60  # 05:00

    for minute in range(start_mins, end_mins):
        # Normalize to 24-hour period
        norm_minute = minute % (24 * 60)
        if norm_minute >= night_start or norm_minute < night_end:
            night_mins += 1
        else:
            day_mins += 1

    return day_mins, night_mins
