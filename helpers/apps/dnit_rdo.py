from helpers.strings import get_obj_from_path


def get_weather(daily_reporting, daily_type):
    try:
        weather_field = next(
            a
            for a in daily_type.form_fields["fields"]
            if ("api_name" in a and a["api_name"] == "weather")
            or ("apiName" in a and a["apiName"] == "weather")
        )
        weather_options = get_obj_from_path(weather_field, "selectoptions__options")
    except (Exception, StopIteration):
        return {}

    ret_data = {a["name"]: False for a in weather_options}

    try:
        weather = daily_reporting.form_data["weather"]
    except (KeyError, AttributeError):
        return ret_data

    ret_data = {
        a["name"]: (True if a["value"] == weather else False) for a in weather_options
    }

    return ret_data


def get_executed_services(daily_reporting, daily_type):
    try:
        services_field = next(
            a
            for a in daily_type.form_fields["fields"]
            if ("api_name" in a and a["api_name"] == "executedServices")
            or ("apiName" in a and a["apiName"] == "executedServices")
        )
        services_options = get_obj_from_path(services_field, "selectoptions__options")
    except (Exception, StopIteration):
        return {}

    ret_data = {a["name"]: False for a in services_options}

    try:
        executed_services = daily_reporting.form_data["executed_services"]
    except (KeyError, AttributeError):
        return ret_data

    ret_data = {
        a["name"]: (True if a["value"] in executed_services else False)
        for a in services_options
    }

    return ret_data


def get_restrictions(daily_reporting, daily_type):
    try:
        restrictions_field = next(
            a
            for a in daily_type.form_fields["fields"]
            if ("api_name" in a and a["api_name"] == "restrictions")
            or ("apiName" in a and a["apiName"] == "restrictions")
        )
        restrictions_options = get_obj_from_path(
            restrictions_field, "selectoptions__options"
        )
    except (Exception, StopIteration):
        return {}

    ret_data = {a["name"]: False for a in restrictions_options}

    try:
        restrictions = daily_reporting.form_data["restrictions"]
    except (KeyError, AttributeError):
        return ret_data

    ret_data = {
        a["name"]: (True if a["value"] in restrictions else False)
        for a in restrictions_options
    }

    return ret_data


def get_kms(reporting):
    start_km = "{:07.3f}".format(reporting.km)
    end_km = "{:07.3f}".format(reporting.end_km or 0)

    return start_km, end_km


def get_notes(daily_reporting, executed_reportings, day):
    todays_reportings = [a for a in executed_reportings if a.executed_at.day == day.day]

    strings = [
        "km {} a {} - {}".format(*get_kms(reporting), reporting.occurrence_type.name)
        for reporting in todays_reportings
    ]

    try:
        strings.append(daily_reporting.form_data["notes"])
    except (AttributeError, KeyError):
        pass

    return "\n".join(strings)


def get_occurrence_types(daily_reporting, executed_reportings, day):
    todays_reportings = [a for a in executed_reportings if a.executed_at.day == day.day]

    strings = [reporting.occurrence_type.name for reporting in todays_reportings]
    return "\n".join(set(strings))


def get_rain(daily_reporting):
    try:
        return daily_reporting.form_data["rain"]
    except Exception:
        return 0
