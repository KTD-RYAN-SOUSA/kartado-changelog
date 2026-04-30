""" SIH integration helpers built the DataSeries API calls """

from datetime import datetime, timedelta

import requests
import sentry_sdk
from django.utils import timezone
from rest_framework_json_api import serializers

from apps.occurrence_records.const.custom_table import (
    DAILY,
    DATA_HOURLY,
    HOURLY,
    MONTHLY,
)
from helpers.strings import dict_to_casing, get_obj_from_path
from RoadLabsAPI.settings import credentials


def fetch_sih_data_yesterday(postos: list, items: list) -> list:
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
    today = datetime.now().strftime("%d/%m/%Y")
    return fetch_sih_data(postos, items, DAILY, yesterday, today)


def fetch_sih_data(
    postos: list,
    items: list,
    frequency: str = DAILY,
    start_date: str = None,
    end_date: str = None,
    hour_start: str = None,
) -> list:
    """
    Fetch the SIH data for the provided API returning only
    the items without the metadata.

    Args:
        posto (str): The form_data.code from instrument_record
        item (str): The form_data.code from sih_monitoring_parameter
        start_date (str): Consider values starting from this date (ex: "11/02/1996"). Defaults to None.
        end_date (str): Consider values up to this date (ex: "11/02/1998"). Defaults to None.

    Raises:
        kartado.error.sih_integration.problem_found_while_attempting_to_call_sih_api: The helper had a problem while making the request
        kartado.error.sih_integration.sih_response_not_ok: Data was fetched successfully from the API but the returned data has a problem
        kartado.error.sih_integration.no_data_returned: The integration returned no data
        kartado.error.sih_integration.incomplete_data: Some of the mandatory data was not provided

    Returns:
        list: The data from `dados__dado`, aka the requested items, with keys converted to snake case
    """

    TIMEOUT = 20  # API call timeout (in seconds)
    ENDPOINT_URL = credentials.SIH_API_BASE_URL

    current_year = timezone.now().year

    if not start_date:
        start_date = (f"01/01/{current_year}",)  # First day is always 01/01
    if not end_date:
        end_date = (
            f"31/12/{current_year}",
        )  # Last day is always 31/12 (unless, you know... 🌎💥💀 before that)
    if frequency == MONTHLY:
        ENDPOINT_URL += "/consultaDadosMensalSIH"
    elif frequency == HOURLY:
        ENDPOINT_URL += "/consultaDadosHorarioSIH"
    else:
        ENDPOINT_URL += "/consultaDadosDiarioSIH"

    request_body = {
        "sistema": "Kartado",
        "item": ", ".join(f"'{i}'" for i in items),
        "posto": ", ".join(str(p) for p in postos),
        "dataInicio": start_date,
        "dataFim": end_date,
    }
    # Make sure the API call goes smoothly
    try:
        response = requests.post(
            ENDPOINT_URL,
            timeout=TIMEOUT,
            json=request_body,
            auth=(credentials.SIH_API_USERNAME, credentials.SIH_API_PWD),
        )
        response.raise_for_status()  # Raise exception if there's a problem
    except requests.exceptions.RequestException as e:
        sentry_sdk.capture_exception(e)
        raise serializers.ValidationError(
            "kartado.error.data_series.problem_found_while_attempting_to_call_sih_api"
        )

    response_data = response.json()  # Deserialize response

    # SIH are you okay? :(
    sih_is_not_ok = (
        str(get_obj_from_path(response_data, "dados__dsmensagem")).upper() != "OK"
    )
    if sih_is_not_ok:
        raise serializers.ValidationError(
            "kartado.error.data_series.sih_response_not_ok"
        )

    # Extract the items and convert the keys to snake case for easy handling
    items = dict_to_casing(
        get_obj_from_path(response_data, "dados__dado"), "underscore"
    )

    if frequency == HOURLY and hour_start:
        items = set_response_frequency_hourly(
            items,
            start_date,
            hour_start,
        )

    return items


def set_reading_data(
    parameter_records, form_data, vlr_dado_hidromet, name_var: str
) -> dict:
    reading_data = {}
    for parameter in parameter_records:
        try:
            resp_data = next(
                a
                for a in vlr_dado_hidromet
                if a["cod_posto_hidromet"] == str(form_data["uposto"])
                and a["cod_item_hidromet"] == parameter.form_data["uabrev"]
            )
        except Exception as e:
            print(e)
            continue

        reading_data[parameter.form_data["name"]] = {
            "value": resp_data[name_var],
            "unit": parameter.form_data["unit"],
        }
    return reading_data


def set_response_frequency_hourly(
    items: dict, start_date: str, hour_start: str = None
) -> dict:
    if not hour_start:
        now = timezone.now()
        hour_start = str(now.time())[0:5]

    for index, item in enumerate(items):
        dt, hour = str(item.get(DATA_HOURLY)[:16]).split("T")
        date_item = (datetime.strptime(dt, "%Y-%m-%d")).strftime("%d/%m/%Y")
        if date_item == start_date:
            if hour[:2] == hour_start[:2]:
                return [item, items[index + 1]]
