import json
from typing import List

import requests

from apps.companies.models import Company
from apps.occurrence_records.helpers.apis.tessadem.config import TESSADEM_BASE_URL
from apps.occurrence_records.helpers.get.coordinates import (
    get_list_coordinates_in_properties,
)
from apps.users.models import User
from helpers.apps.templates import log_api_usage
from helpers.arrays import is_matrix

BASE_URL = TESSADEM_BASE_URL


def get_elevation(
    list_longitudes_latitudes: List[List[float]],
    company: Company,
    user: User,
    reverse,
) -> List:
    """
    Returns the minimum elevation of a list of latitudes and longitudes.

    :param list_longitudes_latitudes: List of lists of latitudes and longitudes.
    :return: Minimum elevation.
    """

    parm = ""

    logs_lats_origin = []

    for log_lat in list_longitudes_latitudes:
        logs_lats_origin.append(log_lat)
        result = get_list_coordinates_in_properties(log_lat, reverse)

        if result:
            if len(result) == 2 and isinstance(result[0], (float, int)):
                if parm != "":
                    parm += "|"
                parm += (",").join([str(x) for x in result])
            elif len(result) > 2:
                for x in result:
                    if parm != "":
                        parm += "|"
                    parm += (",").join([str(_) for _ in x])

    if not parm:
        return

    params_list = parm.split("|")
    consolidated_data = {"results": []}

    for single_parm in params_list:
        response = requests.get(BASE_URL + single_parm)
        log_api_usage("TESSADEM", company, user, response)

        if response.status_code != 200:
            print(
                f"Error {response.status_code} for parameter {single_parm}: {response.text}"
            )
            return

        data = json.loads(response.content.decode())
        if "results" in data:
            consolidated_data["results"].extend(data["results"])

    elevations = [round(x.get("elevation")) for x in consolidated_data["results"]]

    count = 0
    while elevations:
        if is_matrix(logs_lats_origin[count]):
            for i in range(len(logs_lats_origin[count])):
                if not is_matrix(logs_lats_origin[count][i]):
                    logs_lats_origin[count][i].append(elevations.pop(0))

        else:
            logs_lats_origin[count].append(elevations.pop(0))

        count += 1

    return logs_lats_origin
