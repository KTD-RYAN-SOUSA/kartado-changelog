from datetime import time as time_type

from helpers.dates import format_minutes, format_minutes_decimal

# Night period boundaries (CLT standard)
NIGHT_START_MINUTES = 22 * 60  # 22:00
NIGHT_END_MINUTES = 5 * 60  # 05:00

PERIOD_NAMES = ["morning", "afternoon", "night"]


def parse_time_to_minutes(time_str):
    """Converts 'HH:MM' string or datetime.time to total minutes since midnight."""
    if not time_str:
        return None
    try:
        if isinstance(time_str, time_type):
            return time_str.hour * 60 + time_str.minute
        hours, mins = map(int, time_str.split(":"))
        return hours * 60 + mins
    except (ValueError, AttributeError):
        return None


def _is_night_minute(minute):
    """Checks if a normalized minute (0-1439) falls in the night period (22:00-05:00)."""
    norm = minute % (24 * 60)
    return norm >= NIGHT_START_MINUTES or norm < NIGHT_END_MINUTES


def _split_day_night_minutes(start_mins, end_mins):
    """Splits a time range into day and night minutes."""
    if start_mins is None or end_mins is None:
        return 0, 0

    if end_mins <= start_mins:
        end_mins += 24 * 60

    day_mins = 0
    night_mins = 0
    for m in range(start_mins, end_mins):
        if _is_night_minute(m):
            night_mins += 1
        else:
            day_mins += 1

    return day_mins, night_mins


def _period_minutes(start_mins, end_mins):
    """Calculates total minutes for a period, handling midnight crossing."""
    delta = end_mins - start_mins
    if delta < 0:
        delta += 24 * 60
    return delta


def _calc_overlap(w_start, w_end, p_start, p_end):
    """
    Calculate overlap minutes between a worked interval and a planned interval.
    Handles midnight-crossing intervals by trying the worked interval shifted
    by -24h, 0, and +24h, returning the maximum overlap found.
    """
    if w_end <= w_start:
        w_end += 24 * 60
    if p_end <= p_start:
        p_end += 24 * 60

    day = 24 * 60
    best = 0
    for shift in (-day, 0, day):
        ws = w_start + shift
        we = w_end + shift
        overlap = max(0, min(we, p_end) - max(ws, p_start))
        best = max(best, overlap)

    return best


def _get_item_value(item, camel_key, snake_key):
    """Gets a value from dict, trying camelCase first then snake_case."""
    val = item.get(camel_key)
    if val is None:
        val = item.get(snake_key)
    return val


def _extract_worked_by_period(extra_hours_item, default_hours=None):
    """
    Extracts worked periods grouped by period name.
    Returns dict: {period_name: (start_minutes, end_minutes)}
    Handles both camelCase and snake_case keys (JSON:API parser).

    If default_hours is provided, it is used to fill a missing start or end
    when the other value is present in extra_hours_item.
    """
    result = {}
    for period_name in PERIOD_NAMES:
        start_str = _get_item_value(
            extra_hours_item,
            f"{period_name}Start",
            f"{period_name}_start",
        )
        end_str = _get_item_value(
            extra_hours_item,
            f"{period_name}End",
            f"{period_name}_end",
        )
        is_deleted = _get_item_value(
            extra_hours_item,
            f"{period_name}StartIsDeleted",
            f"{period_name}_start_is_deleted",
        )

        if is_deleted:
            continue

        if default_hours:
            if not start_str:
                start_str = _get_item_value(
                    default_hours,
                    f"{period_name}Start",
                    f"{period_name}_start",
                )
            if not end_str:
                end_str = _get_item_value(
                    default_hours,
                    f"{period_name}End",
                    f"{period_name}_end",
                )

        if not start_str or not end_str:
            continue

        start_mins = parse_time_to_minutes(start_str)
        end_mins = parse_time_to_minutes(end_str)

        if start_mins is not None and end_mins is not None:
            result[period_name] = (start_mins, end_mins)

    return result


def _extract_planned_by_period(working_schedules, day_of_week):
    """
    Extracts planned intervals grouped by period name for a specific day.
    Supports multiple schedules with the same period.
    Returns dict: {period_name: [(start_minutes, end_minutes), ...]}
    """
    result = {}
    for schedule in working_schedules:
        days = schedule.get("days_of_week", [])
        if day_of_week not in days:
            continue

        period_name = schedule.get("period")
        if period_name not in PERIOD_NAMES:
            continue

        start_mins = parse_time_to_minutes(schedule.get("start_time"))
        end_mins = parse_time_to_minutes(schedule.get("end_time"))

        if start_mins is not None and end_mins is not None:
            if period_name not in result:
                result[period_name] = []
            result[period_name].append((start_mins, end_mins))

    return result


def _has_night_schedule(working_schedules):
    """Checks if any working schedule covers the night period (22:00-05:00)."""
    for schedule in working_schedules:
        start_mins = parse_time_to_minutes(schedule.get("start_time"))
        end_mins = parse_time_to_minutes(schedule.get("end_time"))
        if start_mins is None or end_mins is None:
            continue

        if end_mins <= start_mins:
            end_mins += 24 * 60

        for m in range(start_mins, end_mins):
            if _is_night_minute(m):
                return True

    return False


def _overlap_interval(w_s, w_e, p_s, p_e):
    """
    Returns the actual overlap interval (start, end) between a worked and a planned
    interval, handling midnight crossing via the same shift strategy as _calc_overlap.
    Returns None if there is no overlap.
    """
    if w_e <= w_s:
        w_e += 24 * 60
    if p_e <= p_s:
        p_e += 24 * 60

    day = 24 * 60
    best_ov = 0
    best_interval = None
    for shift in (-day, 0, day):
        ws = w_s + shift
        we = w_e + shift
        ov_start = max(ws, p_s)
        ov_end = min(we, p_e)
        ov = max(0, ov_end - ov_start)
        if ov > best_ov:
            best_ov = ov
            best_interval = (ov_start, ov_end)

    return best_interval


def _split_extra_day_night(worked_interval, planned_intervals):
    """
    For a single period (morning/afternoon/night), computes extra day/night minutes
    and absence minutes using exact interval arithmetic.

    Returns (extra_day_mins, extra_night_mins, absence_mins).
    """
    if not worked_interval:
        total_planned = sum(_period_minutes(s, e) for s, e in planned_intervals)
        return 0, 0, total_planned

    w_s, w_e = worked_interval
    if w_e <= w_s:
        w_e += 24 * 60

    worked_day, worked_night = _split_day_night_minutes(w_s, w_e)

    if not planned_intervals:
        return worked_day, worked_night, 0

    total_planned = sum(_period_minutes(s, e) for s, e in planned_intervals)
    overlap_day = 0
    overlap_night = 0
    total_overlap = 0

    for p_s, p_e in planned_intervals:
        interval = _overlap_interval(w_s, w_e, p_s, p_e)
        if interval:
            ov_d, ov_n = _split_day_night_minutes(*interval)
            overlap_day += ov_d
            overlap_night += ov_n
            total_overlap += ov_d + ov_n

    extra_day = max(0, worked_day - overlap_day)
    extra_night = max(0, worked_night - overlap_night)
    absence = max(0, total_planned - total_overlap)

    return extra_day, extra_night, absence


def _compare_period(worked_interval, planned_intervals):
    """
    Compares a single worked interval against a list of planned intervals
    using overlap-based logic. Extra hours NEVER compensate absence.

    Returns (extra_minutes, absence_minutes).
    """
    worked_mins = 0
    if worked_interval:
        s, e = worked_interval
        worked_mins = _period_minutes(s, e)

    total_planned = sum(_period_minutes(s, e) for s, e in planned_intervals)

    total_overlap = 0
    if worked_interval:
        w_s, w_e = worked_interval
        for p_s, p_e in planned_intervals:
            total_overlap += _calc_overlap(w_s, w_e, p_s, p_e)

    extra_mins = worked_mins - total_overlap
    absence_mins = total_planned - total_overlap

    return max(0, extra_mins), max(0, absence_mins)


def calculate_extra_hours(
    worked_periods_item, working_schedules, day_of_week, is_holiday, is_compensation
):
    """
    Calculates extra hours classification for a single resource.
    Comparison is done period-by-period (morning vs morning, afternoon vs afternoon,
    night vs night) matching by the 'period' field in working_schedules.
    Uses interval overlap so that extra hours never compensate absence.

    Args:
        worked_periods_item: dict from extra_hours payload (one resource)
        working_schedules: list of working schedules from ContractPeriod
        day_of_week: int, ISO weekday (1=Monday, 7=Sunday)
        is_holiday: bool
        is_compensation: bool

    Returns:
        dict with extra_hours_50, extra_hours_100, extra_hours_night, absence
    """
    result = {
        "extra_hours_50": "00:00",
        "extra_hours_100": "00:00",
        "extra_hours_night": "00:00",
        "absence": "00:00",
    }

    if is_compensation:
        return result

    worked_by_period = _extract_worked_by_period(worked_periods_item)
    planned_by_period = _extract_planned_by_period(working_schedules, day_of_week)

    is_sunday = day_of_week == 7
    night_schedule = _has_night_schedule(working_schedules)

    # No worked hours: check for absence on planned days
    if not worked_by_period:
        if not is_sunday and not is_holiday and planned_by_period:
            total_planned = sum(
                _period_minutes(s, e)
                for intervals in planned_by_period.values()
                for s, e in intervals
            )
            result["absence"] = format_minutes(total_planned)
        return result

    # Calculate total worked and night hours
    total_worked = 0
    total_worked_night = 0
    for start_mins, end_mins in worked_by_period.values():
        day_m, night_m = _split_day_night_minutes(start_mins, end_mins)
        total_worked += day_m + night_m
        total_worked_night += night_m

    # Night hours (22h-5h) if contract has no night schedule
    if not night_schedule and total_worked_night > 0:
        result["extra_hours_night"] = format_minutes(total_worked_night)

    # Case A: Sunday or Holiday -> all worked hours are 100%
    if is_sunday or is_holiday:
        result["extra_hours_100"] = format_minutes(total_worked)
        return result

    # Case B: Weekday, contract doesn't plan work today -> all worked = 50%
    if not planned_by_period:
        result["extra_hours_50"] = format_minutes(total_worked)
        return result

    # Case C: Planned day -> compare period-by-period using interval overlap
    all_periods = set(list(worked_by_period.keys()) + list(planned_by_period.keys()))

    total_extra_50 = 0
    total_absence = 0

    for period_name in all_periods:
        worked_interval = worked_by_period.get(period_name)
        planned_intervals = planned_by_period.get(period_name, [])

        extra_mins, absence_mins = _compare_period(worked_interval, planned_intervals)

        # Night clock-time hours already classified as extra_hours_night
        # should not be double-counted as extra_hours_50
        if period_name == "night" and not night_schedule and total_worked_night > 0:
            extra_mins = max(0, extra_mins - total_worked_night)

        total_extra_50 += extra_mins
        total_absence += absence_mins

    if total_extra_50 > 0:
        result["extra_hours_50"] = format_minutes(total_extra_50)
    if total_absence > 0:
        result["absence"] = format_minutes(total_absence)

    return result


def calculate_extra_hours_worker(
    worked_periods_item,
    working_schedules,
    day_of_week,
    is_holiday,
    is_compensation,
    default_hours=None,
):
    """
    Calculates extra hours for a worker (employee), splitting every extra minute
    into day (5:01–21:59) and night (22:00–5:00) categories.

    Args:
        worked_periods_item: dict from extra_hours payload (one resource)
        working_schedules: list of working schedules from ContractPeriod
        default_hours: optional dict with default start/end times used to fill
            missing start or end when the counterpart is present in worked_periods_item
        day_of_week: int, ISO weekday (1=Monday, 7=Sunday)
        is_holiday: bool
        is_compensation: bool

    Returns:
        dict with extra_hours_50_day, extra_hours_50_night, extra_hours_100_day,
        extra_hours_100_night, absence, compensation (all HH:MM strings)
    """
    result = {
        "extra_hours_50_day": "00:00",
        "extra_hours_50_night": "00:00",
        "extra_hours_100_day": "00:00",
        "extra_hours_100_night": "00:00",
        "absence": "00:00",
        "compensation": "00:00",
    }

    worked_by_period = _extract_worked_by_period(worked_periods_item, default_hours)
    planned_by_period = _extract_planned_by_period(working_schedules, day_of_week)

    is_sunday = day_of_week == 7

    # RN32 — Compensation mode: zero all extras, return time worked beyond planned
    if is_compensation:
        all_periods = set(
            list(worked_by_period.keys()) + list(planned_by_period.keys())
        )
        total_comp = 0
        for period_name in all_periods:
            worked_interval = worked_by_period.get(period_name)
            planned_intervals = (
                [] if is_holiday else planned_by_period.get(period_name, [])
            )
            extra_day, extra_night, _ = _split_extra_day_night(
                worked_interval, planned_intervals
            )
            total_comp += extra_day + extra_night
        if total_comp > 0:
            result["compensation"] = format_minutes(total_comp)
        return result

    # RN41 — No worked hours: absence on planned days (sunday included, holiday excluded)
    if not worked_by_period:
        if planned_by_period and not is_holiday:
            total_planned = sum(
                _period_minutes(s, e)
                for intervals in planned_by_period.values()
                for s, e in intervals
            )
            result["absence"] = format_minutes(total_planned)
        return result

    # Period-by-period comparison (RN30)
    all_periods = set(list(worked_by_period.keys()) + list(planned_by_period.keys()))

    total_50_day = 0
    total_50_night = 0
    total_100_day = 0
    total_100_night = 0
    total_absence = 0

    for period_name in all_periods:
        worked_interval = worked_by_period.get(period_name)

        if is_holiday:
            # RN35/RN36: on holidays ALL worked hours are 100%, ignoring planned
            # schedule (labour law: holiday cancels normal workday obligations).
            # No absence on holidays.
            extra_day, extra_night, _ = _split_extra_day_night(worked_interval, [])
            total_100_day += extra_day
            total_100_night += extra_night
        elif is_sunday:
            # RN35/RN36 + RN37: on sundays, planned work (if any) is treated as
            # normal; only the excess beyond planned goes to 100%.
            # Absence still applies if there is planned work and worker didn't show.
            planned_intervals = planned_by_period.get(period_name, [])
            extra_day, extra_night, absence_mins = _split_extra_day_night(
                worked_interval, planned_intervals
            )
            total_100_day += extra_day
            total_100_night += extra_night
            total_absence += absence_mins
        else:
            # RN33/RN34: extra on weekday/saturday goes to 50%
            planned_intervals = planned_by_period.get(period_name, [])
            extra_day, extra_night, absence_mins = _split_extra_day_night(
                worked_interval, planned_intervals
            )
            total_50_day += extra_day
            total_50_night += extra_night
            total_absence += absence_mins

    if total_50_day > 0:
        result["extra_hours_50_day"] = format_minutes(total_50_day)
    if total_50_night > 0:
        result["extra_hours_50_night"] = format_minutes(total_50_night)
    if total_100_day > 0:
        result["extra_hours_100_day"] = format_minutes(total_100_day)
    if total_100_night > 0:
        result["extra_hours_100_night"] = format_minutes(total_100_night)
    if total_absence > 0:
        result["absence"] = format_minutes(total_absence)

    return result


def _worker_result_to_decimal_cols(result, is_worker):
    """Converts a calculate_extra_hours_worker result into 7 decimal values.

    Order: [50d, 50n, 100d, 100n, additional_hours, absence, compensation]
    For workers: additional_hours=0. For equipment/vehicles: 50/100 cols=0.
    """

    def to_dec(key):
        return format_minutes_decimal(parse_time_to_minutes(result[key]) or 0)

    absence = to_dec("absence")
    compensation = to_dec("compensation")

    if is_worker:
        return [
            to_dec("extra_hours_50_day"),
            to_dec("extra_hours_50_night"),
            to_dec("extra_hours_100_day"),
            to_dec("extra_hours_100_night"),
            0,
            absence,
            compensation,
        ]
    else:
        additional_hours = format_minutes_decimal(
            sum(
                parse_time_to_minutes(result[k]) or 0
                for k in (
                    "extra_hours_50_day",
                    "extra_hours_50_night",
                    "extra_hours_100_day",
                    "extra_hours_100_night",
                )
            )
        )
        return [0, 0, 0, 0, additional_hours, absence, compensation]
