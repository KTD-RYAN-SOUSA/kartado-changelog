import json
import math
import random
import re
import string
import uuid
from datetime import datetime
from typing import Any, Iterable, List, Union
from unicodedata import normalize
from urllib import parse

import pyproj
from dateutil import parser
from django.conf import settings
from django.contrib.gis.geos import LineString, Polygon
from sequences import get_next_value

from RoadLabsAPI.settings import credentials


def strtobool(val):
    """
    Convert a string representation of truth to True or False.

    This function replaces the deprecated distutils.util.strtobool
    which was removed in Python 3.12.

    True values are: 'y', 'yes', 't', 'true', 'on', '1'
    False values are: 'n', 'no', 'f', 'false', 'off', '0'

    Args:
        val: String value to convert to boolean

    Returns:
        bool: True or False

    Raises:
        ValueError: If val is not a valid boolean string
    """
    val = str(val).lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return True
    elif val in ("n", "no", "f", "false", "off", "0"):
        return False
    else:
        raise ValueError(f"invalid truth value {val!r}")


ILLEGAL_CHARACTERS = [
    "\x00",
    "\x01",
    "\x02",
    "\x03",
    "\x04",
    "\x05",
    "\x06",
    "\x07",
    "\x08",
    "\x0b",
    "\x0c",
    "\x0e",
    "\x0f",
    "\x10",
    "\x11",
    "\x12",
    "\x13",
    "\x14",
    "\x15",
    "\x16",
    "\x17",
    "\x18",
    "\x19",
    "\x1a",
    "\x1b",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x1f",
]

COMMON_IMAGE_TYPE = ["png", "jpg", "jpeg", "gif", "bmp", "svg", "ico", "webp"]
COMMON_DOC_TYPE = ["txt", "doc", "docx", "odt", "rtf", "tex", "log"]
COMMON_GEO_TYPE = ["gpx", "kml", "kmz", "shp", "geojson", "gdb"]
COMMON_SPREADSHEET_TYPE = [
    "xls",
    "xlsx",
    "csv",
    "ods",
    "numbers",
    "xlsb",
    "xlsm",
    "tsv",
]

STRING_UNIT_METRICS = {"m2": "m²", "m3": "m³", "km2": "km²", "km3": "km³"}

ZONE_MAP = {
    "18N": "EPSG:31972",
    "19N": "EPSG:31973",
    "20N": "EPSG:31974",
    "21N": "EPSG:31975",
    "22N": "EPSG:31976",
    "18S": "EPSG:31978",
    "19S": "EPSG:31979",
    "20S": "EPSG:31980",
    "21S": "EPSG:31981",
    "22S": "EPSG:31982",
    "23S": "EPSG:31983",
    "23K": "EPSG:31983",  # Zona 23 banda K (sudeste do Brasil)
    "24S": "EPSG:31984",
    "25S": "EPSG:31985",
}

UF_CODE = {
    "11": "RO",
    "12": "AC",
    "13": "AM",
    "14": "RR",
    "15": "PA",
    "16": "AP",
    "17": "TO",
    "21": "MA",
    "22": "PI",
    "23": "CE",
    "24": "RN",
    "25": "PB",
    "26": "PE",
    "27": "AL",
    "28": "SE",
    "29": "BA",
    "31": "MG",
    "32": "ES",
    "33": "RJ",
    "35": "SP",
    "41": "PR",
    "42": "SC",
    "43": "RS",
    "50": "MS",
    "51": "MT",
    "52": "GO",
    "53": "DF",
}

DAY_WEEK = [
    "Segunda-Feira",
    "Terça-Feira",
    "Quarta-Feira",
    "Quinta-Feira",
    "Sexta-Feira",
    "Sábado",
    "Domingo",
]

DAYS_PORTUGUESE = {
    "Monday": "Segunda-feira",
    "Tuesday": "Terça-feira",
    "Wednesday": "Quarta-feira",
    "Thursday": "Quinta-feira",
    "Friday": "Sexta-feira",
    "Saturday": "Sábado",
    "Sunday": "Domingo",
}

MAPS_MONTHS_ENG_TO_PT = {
    "January": "janeiro",
    "February": "fevereiro",
    "March": "março",
    "April": "abril",
    "May": "maio",
    "June": "junho",
    "July": "julho",
    "August": "agosto",
    "September": "setembro",
    "October": "outubro",
    "November": "novembro",
    "December": "dezembro",
}

MAPS_MONTHS_ENG_TO_PT_SHORT = {
    "January": "JAN",
    "February": "FEV",
    "March": "MAR",
    "April": "ABR",
    "May": "MAI",
    "June": "JUN",
    "July": "JUL",
    "August": "AGO",
    "September": "SET",
    "October": "OUT",
    "November": "NOV",
    "December": "DEZ",
}

TRANSLATE_TYPE = {
    "Point": "Ponto",
    "LineString": "Linha",
    "MultiLineString": "Linha",
    "Polygon": "Polígono",
    "MultiLinePolygon": "Polígono",
}

REMOVE_PATTERN = re.compile("[-_]")


def format_km(reporting, field, left_padding=0):
    try:
        numbers = format(round(float(getattr(reporting, field)), 3), ".3f").split(".")
        zero_left = left_padding - len(numbers[0])
        zero_left = zero_left if zero_left > 0 else 0
        return "{}{}+{:03d}".format("0" * zero_left, int(numbers[0]), int(numbers[1]))
    except Exception:
        return ""


def get_direction_name(company, direction, dir_type="name"):
    possible_path = "reporting__fields__direction__selectoptions__options"
    options = get_obj_from_path(company.custom_options, possible_path)
    try:
        dir_names = [item[dir_type] for item in options if item["value"] == direction]
    except Exception:
        dir_names = []
    return dir_names[0] if dir_names else ""


def clean_latin_string(txt):
    return normalize("NFKD", txt).encode("ASCII", "ignore").decode("ASCII")


def get_autonumber_array(company_id, name):
    today = datetime.today()
    return {
        "nome": name,
        "serial": get_next_value("{}-company-{}".format(name, company_id)),
        "serialAno": get_next_value(
            "{}-company-{}-year-{}".format(name, company_id, today.strftime("%y"))
        ),
        "anoSimples": today.strftime("%y"),
        "anoCompleto": today.strftime("%Y"),
        "mesNumero": today.strftime("%m"),
        "diaNumero": today.strftime("%d"),
        "hora24H": today.strftime("%H"),
        "hora12H": today.strftime("%I"),
        "AM-PM": today.strftime("%p"),
    }


def build_ecm_query(values, search_type):
    list_of_chars = ["<", ">", "`"]

    # Fixed elements in the query
    query = "dDocType+<contains>+`Document`++<AND>++"
    if search_type == "registro":
        query += "dSecurityGroup+<contains>+`DPSPATIMOBRO`++<AND>++"
    elif search_type == "imovel":
        query += "dSecurityGroup+<contains>+`DPSPATIMOBPP`++<AND>++"

    for i, item in enumerate(values):
        field = item.get("campo", "")
        value = item.get("valor", "").replace(" ", "+")
        operation = item.get("operacao", "")
        if field and value and operation:
            if i == len(values) - 1:
                query += "{}+<contains>+`{}`".format(field, value)
            else:
                query += "{}+<contains>+`{}`++<{}>++".format(field, value, operation)

    for item in list_of_chars:
        query = query.replace(item, parse.quote(item))

    return settings.ECM_SEARCH_URL_INITIAL + query + credentials.ECM_SEARCH_URL_FINAL


def encode_slash(input_str):
    return input_str.replace("/", "%2F")


def decode_slash(input_str):
    return input_str.replace("%2F", "/")


def path_from_dict(input_dict):
    divisor = "/"
    dates_list = []

    def get_paths(input_dict):
        for key, value in input_dict.items():
            # accept range formats
            if "from" in input_dict or "to" in input_dict:
                key = "gte" if key == "from" else key
                key = "lte" if key == "to" else key

            # accept datetimes
            if isinstance(value, str):
                # since the slash char is used as divisor, encode it before handling
                value = encode_slash(value)
                # use is_digit because parser accepts integers alone
                if not value.replace(".", "").isdigit():
                    try:
                        value = parser.parse(value)
                    except Exception:
                        pass
                    else:
                        value = value.isoformat()
                        # save value to parse again
                        dates_list.append(value)

            # accept deep dicts
            if isinstance(value, dict):
                for subkey in get_paths(value):
                    yield key + "__" + subkey
            else:
                yield key + divisor + json.dumps(value)

    paths_dict = {
        item.split(divisor)[0]: (
            # then, after splitting out the divisor, decode the slash back into its original form
            json.loads(decode_slash(item.split(divisor)[1]))
            if json.loads(item.split(divisor)[1]) not in dates_list
            else parser.parse(json.loads(item.split(divisor)[1]))
        )
        for item in get_paths(input_dict)
    }

    return paths_dict


def get_all_dict_paths(input_dict, separator="__"):
    paths_list = []

    if not isinstance(input_dict, dict):
        return paths_list

    def get_dict_paths(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                get_dict_paths(value, path + separator + key if path else key)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                get_dict_paths(item, path + separator + str(i) if path else str(i))
        else:
            paths_list.append(path + separator + str(obj))

    get_dict_paths(input_dict)

    return paths_list


def check_image_file(file_string):
    image_type = file_string.split(".")
    if image_type[-1].lower() in COMMON_IMAGE_TYPE:
        return True
    return False


def minutes_to_hour_str(minutes):
    return "{:02d}:{:02d}".format(*divmod(int(minutes), 60))


def deg_to_dms(deg, coord="lat"):
    decimals, number = math.modf(deg)
    d = int(number)
    m = int(decimals * 60)
    s = int((deg - d - m / 60) * 3600.00)
    compass = {"lat": ("N", "S"), "lon": ("E", "W")}
    compass_str = compass[coord][0 if deg >= 0 else 1]
    return """{}{}{}{}{}{}{}""".format(
        str(abs(d)), "º ", str(abs(m)), "' ", str(abs(s)), '" ', compass_str
    )


def str_hours_to_int(hours_str):
    if isinstance(hours_str, str):
        hours_list = hours_str.split(":")
        return 60 * int(hours_list[0]) + int(hours_list[1])
    return 0


def get_xyz_from_point(point):
    wgspoint = point.transform("WGS84", clone=True)
    lon = wgspoint.x
    lat = wgspoint.y
    zone = str(int(1 + (lon + 180.0) / 6.0))
    zone += "N" if lat >= 0.0 else "S"

    p1 = pyproj.Proj(proj="latlong", datum="WGS84")
    get_zone = ZONE_MAP.get(zone, False)
    if not get_zone:
        return {"x": "", "y": "", "zone": ""}
    p2 = pyproj.Proj(get_zone)
    a = pyproj.transform(p1, p2, point.x, point.y)

    point_dict = {"x": round(a[0], 2), "y": round(a[1], 2), "zone": zone}
    return point_dict


def get_str_from_xyz(point):
    point_dict = get_xyz_from_point(point)
    point_str = [str(item) for item in point_dict.values()]
    if len(point_str) == 3:
        return "X: {} Y: {} Z: {}".format(point_str[0], point_str[1], point_str[2])
    else:
        return ""


def transform_geo(geo, line=False, polygon=False):
    if line:
        build_geo = LineString(geo, srid=4326)
    elif polygon:
        build_geo = Polygon(geo, srid=4326)

    try:
        point = build_geo.centroid
        point_xyz = get_xyz_from_point(point)
        epsg = int(ZONE_MAP[point_xyz["zone"]].split(":")[-1])
    except Exception:
        epsg = 31972

    build_geo.transform(epsg)

    return build_geo


def clean_string(string):
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map symbols
        "\U0001f1e0-\U0001f1ff"  # flags (iOS)
        "\U00002702-\U000027b0"
        "\U000024c2-\U0001f251"
        "]+",
        flags=re.UNICODE,
    )

    new_string = emoji_pattern.sub(r"", string)
    if "\n" in new_string:
        new_string = "".join(new_string.split("\n", -1)[0])

    return " ".join(new_string.split())


def _unpack(data):
    if isinstance(data, dict):
        return data.items()
    return data


def to_snake_case(value):
    """
    Convert camel case string to snake case

    :param value: string
    :return: string
    """
    first_underscore = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", first_underscore).lower()


def to_camel_case(value):
    """
    Convert snake case to camel case

    :param value: string
    :return: string
    """
    content = value.split("_")
    return content[0] + "".join(
        word.title() for word in content[1:] if not word.isspace()
    )


def keys_to_snake_case(content):
    """
    Convert all keys for given dict to snake case

    :param content: dict
    :return: dict
    """
    return {to_snake_case(key): value for key, value in _unpack(content)}


def keys_to_camel_case(content):
    """
    Convert all keys for given dict to camel case

    :param content: dict
    :return: dict
    """
    return {to_camel_case(key): value for key, value in _unpack(content)}


def dict_to_casing(data, format_type="camelize"):
    """
    Changes the casing of every key in a dictionary (any depth).
    Defaults to camelCase.
    """

    # Choose function to change casing
    if format_type == "camelize":
        change_casing = to_camel_case
    elif format_type == "underscore":
        change_casing = to_snake_case
    else:
        raise NotImplementedError("format_type is not supported")

    if isinstance(data, list):
        return [
            (
                dict_to_casing(item, format_type)
                if isinstance(item, (dict, list))
                else item
            )
            for item in data
        ]
    elif isinstance(data, dict):
        return {
            change_casing(key): (
                dict_to_casing(value, format_type)
                if isinstance(value, (dict, list))
                else value
            )
            for key, value in data.items()
        }


def to_flatten_str(value):
    """
    Convert camelCase, snake_case, PascalCase, kebab-case
    to flatten lower string
    """
    removed_patterns = REMOVE_PATTERN.sub("", value)
    return removed_patterns.lower()


def get_obj_from_path(input_dict, possible_path, separator="__", default_return=[]):
    """
    This function returns any obj from a dict even if the possible_path
    is not formatted like the original path
    """
    if not isinstance(input_dict, dict) or not possible_path:
        return default_return

    for part in possible_path.split(separator):
        # Preprocess input_dict keys only once per dictionary level
        part = to_flatten_str(part)
        flat_keys_map = {to_flatten_str(k): k for k in input_dict}

        # If the part is not found, return empty
        if part not in flat_keys_map:
            return default_return

        # Move to the next nested dictionary level
        input_dict = input_dict[flat_keys_map[part]]

        # If the value is no longer a dictionary, stop
        if not isinstance(input_dict, dict):
            break

    return input_dict


def get_value_from_obj(obj, path, value):
    result = ""
    options = get_obj_from_path(obj, path)
    if options:
        try:
            result = next(item["name"] for item in options if item["value"] == value)
        except Exception:
            pass

    return result


def get_location(item, tipo):
    possible_path_dam = "occurrencerecord__fields__placeondam__selectoptions__options"
    final_str = ""
    if tipo == "occurrencerecord":
        uf = UF_CODE.get(item.uf_code, "")
        city = item.city.name if item.city else ""
        location = item.location.name if item.location else ""
        place_on_dam = get_value_from_obj(
            item.company.custom_options, possible_path_dam, item.place_on_dam
        )
        river = item.river.name if item.river else ""
    elif tipo == "serviceorder":
        uf = (
            ", ".join([UF_CODE.get(code, "") for code in item.uf_code])
            if item.uf_code
            else ""
        )

        cities = [city.name for city in item.city.all()]
        city = ", ".join(cities)

        rivers = [river.name for river in item.river.all()]
        river = ", ".join(rivers)

        locations = [location.name for location in item.location.all()]
        location = ", ".join(locations)

        place_on_dam = (
            ", ".join(
                [
                    get_value_from_obj(
                        item.company.custom_options, possible_path_dam, place
                    )
                    for place in item.place_on_dam
                ]
            )
            if item.place_on_dam
            else ""
        )
    elif tipo == "reporting":
        from helpers.apps.reportings import return_select_value

        uf = UF_CODE.get(item.form_data.get("ufs", ""), "")
        city = return_select_value("cities", item, {})
        location = return_select_value("location", item, {})
        place_on_dam = return_select_value("place_on_dam", item, {})
        river = return_select_value("hidro_body", item, {})

    else:
        return ""

    final_str += "UF: {}. ".format(uf) if uf else ""
    final_str += "Município: {}. ".format(city) if city else ""
    final_str += "Localidade: {}. ".format(location) if location else ""
    final_str += "Local: {}. ".format(place_on_dam) if place_on_dam else ""
    final_str += "Corpo Hídrico: {}. ".format(river) if river else ""
    return final_str


def is_valid_uuid(uuid_to_test, version=4):
    """
    Check if uuid_to_test is a valid UUID.

    Parameters
    ----------
    uuid_to_test : str
    version : {1, 2, 3, 4}

    Returns
    -------
    `True` if uuid_to_test is a valid UUID, otherwise `False`.

    Examples
    --------
    >>> is_valid_uuid('c9bf9e57-1685-4c89-bafb-ff5af830be8a')
    True
    >>> is_valid_uuid('c9bf9e58')
    False
    """
    try:
        uuid_obj = uuid.UUID(uuid_to_test, version=version)
    except ValueError:
        return False

    return str(uuid_obj) == uuid_to_test


def get_random_color():
    return "#{:06x}".format(random.randint(0, 256**3))


def translate_custom_options(custom_options, model_name, field_name, value):
    try:
        possible_path = "{}__fields__{}__selectoptions__options".format(
            model_name, field_name
        )
        return get_value_from_obj(custom_options, possible_path, value)
    except Exception:
        return ""


def iter_items_to_str(iterable: Iterable[Any]) -> List[str]:
    """
    Cast all items of an iterable to string

    Args:
        iterable (Iterable[Any]): Input iterable

    Returns:
        List[str]: List of the items casted to string
    """

    return [str(item) for item in iterable]


def deep_keys_to_snake_case(obj):
    """
    Converte recursivamente todas as chaves de um objeto (dicionário ou lista de dicionários)
    para o formato snake_case.

    Parâmetros:
    - obj (dict or list): O objeto a ser processado. Pode ser um dicionário
      ou uma lista de dicionários.

    Retorna:
    - dict or list: Uma cópia do objeto original com todas as chaves convertidas
      para snake_case.

    Exemplos:
    >>> original = {'camelCaseKey': 'value', 'nestedDict': {'anotherKey': 'anotherValue'}}
    >>> deep_keys_to_snake_case(original)
    {'camel_case_key': 'value', 'nested_dict': {'another_key': 'anotherValue'}}

    >>> original_list = [{'snakeCaseKey': 'value'}, {'anotherCamelCaseKey': 'anotherValue'}]
    >>> deep_keys_to_snake_case(original_list)
    [{'snake_case_key': 'value'}, {'another_camel_case_key': 'anotherValue'}]
    """
    if isinstance(obj, list):
        # Se o valor é uma lista, aplicamos a função a cada elemento da lista
        return [deep_keys_to_snake_case(item) for item in obj]
    elif isinstance(obj, dict):
        # Se o valor é um dicionário, aplicamos a função recursivamente
        new_dict = {}
        obj = keys_to_snake_case(obj)
        for sub_key, sub_obj in obj.items():
            new_dict[sub_key] = deep_keys_to_snake_case(sub_obj)
        return new_dict
    else:
        return obj


def generate_random_string(length=10):
    letters = string.ascii_letters  # Get all letters of the alphabet
    numbers = string.digits  # Get all digits from 0 to 9
    random_string = "".join(
        random.choice(letters + numbers) for _ in range(length)
    )  # Randomly choose between letters and numbers
    return random_string


def int_set_zero_prefix(value: int, min_digital: int = 3):
    if min_digital > len(str(value)) and not re.sub(r"\d", "", str(value)):
        base_value = 10
        value = int(value)
        for index in range(min_digital):
            if value < base_value:
                return "0" * (min_digital - (index + 1)) + str(value)
            base_value = base_value * base_value

    return value


def to_upper_camel_case(value):
    """
    Convert string to UpperCamelCase

    Args:
        value (string): value to be converted
    """
    content = value.split("_")
    if len(content) > 1:
        return "".join(word.title() for word in content if not word.isspace())
    else:
        return value[0].upper() + value[1:]


def dict_to_upper_camel_case(content):
    """
    Convert dict keys to UpperCamelCase

    Args:
        content (dict): dict to be converted

    Returns:
        dict: same dict with changed keys
    """
    if not isinstance(content, dict):
        return content
    return {to_upper_camel_case(k): v for k, v in content.items()}


def remove_ext_in_filename(filename) -> str:
    split_name = (filename).split(".")
    name = ".".join(split_name[:-1])
    return name


def remove_random_string_file_name_in_upload(filename) -> str:
    split_name = (filename).split("_")

    name = "_".join(split_name[:-1]) if len(split_name) > 1 else filename

    return name


def clean_invalid_characters(input: Any) -> Union[dict, list, str, tuple, set]:
    """
    Cleans invalid characters from a dictionary, list, string, tuple, or set.

    This function traverses the input and removes all characters that are
    in the defined list of illegal characters. If the input is a dictionary,
    the function will be applied recursively to each value. If the input is a
    list, tuple, or set, the function will be applied to each item in the collection.
    For strings, the function will return a new string with the invalid
    characters removed.

    Args:
        input (Union[dict, list, str, tuple, set]): The input object that can be a
        dictionary, list, string, tuple, or set.

    Returns:
        Union[dict, list, str, tuple, set]: The input object with invalid characters
        removed. The output type matches the input type.

    Examples:
    >>> clean_invalid_characters({"key1": "valid_string", "key2": "invalid\x00string"})
    {'key1': 'valid_string', 'key2': 'invalidstring'}

    >>> clean_invalid_characters(["valid_string", "invalid\x01string"])
    ['valid_string', 'invalidstring']

    >>> clean_invalid_characters("invalid\x02string")
    'invalidstring'

    >>> clean_invalid_characters((b'valid_bytes', b'invalid\x00bytes'))
    ['valid_bytes', 'invalidbytes']

    >>> clean_invalid_characters({"key1", "valid_string", b'invalid\x01bytes'})
    {'key1', 'valid_string', 'invalidbytes'}
    """

    if isinstance(input, dict):
        return {key: clean_invalid_characters(value) for key, value in input.items()}
    elif isinstance(input, list):
        return [clean_invalid_characters(item) for item in input]
    elif isinstance(input, tuple):
        return tuple(clean_invalid_characters(item) for item in input)
    elif isinstance(input, set):
        return {clean_invalid_characters(item) for item in input}
    elif isinstance(input, str):
        return "".join(c for c in input if c not in ILLEGAL_CHARACTERS)
    else:
        return input


def resolve_duplicate_name(base_name, used_names) -> str:

    if base_name not in used_names:
        used_names[base_name] = 1
        return f"{base_name}_1"
    used_names[base_name] += 1
    return f"{base_name}_{used_names[base_name]}"
