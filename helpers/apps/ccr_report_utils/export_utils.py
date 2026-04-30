import os
import random
import re
import string
from datetime import datetime, timedelta
from uuid import UUID

import boto3
import botocore.config
import pytz
from django.conf import settings
from openpyxl.cell import Cell
from openpyxl.styles import Alignment
from openpyxl.utils import column_index_from_string
from openpyxl.worksheet.worksheet import Worksheet

from apps.companies.models import Company
from apps.occurrence_records.models import RecordPanel
from helpers.apps.occurrence_records import convert_conditions_to_query_params
from RoadLabsAPI.settings import credentials


def get_s3(max_pool_connections=None):
    s3 = None
    if max_pool_connections:
        client_config = botocore.config.Config(
            max_pool_connections=max_pool_connections,
        )
        s3 = boto3.client(
            "s3",
            aws_access_key_id=credentials.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=credentials.AWS_SECRET_ACCESS_KEY,
            aws_session_token=credentials.AWS_SESSION_TOKEN,
            config=client_config,
        )
    else:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=credentials.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=credentials.AWS_SECRET_ACCESS_KEY,
            aws_session_token=credentials.AWS_SESSION_TOKEN,
        )
    return s3


def get_s3_url(s3, object_name: str):
    empty = {"url": "", "name": ""}

    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": object_name,
        },
    )

    if not url:
        return empty

    return url


def get_random_string():
    return "".join(
        random.SystemRandom().choice(string.ascii_lowercase + string.digits)
        for _ in range(10)
    )


def upload_file(s3, path: str, name: str):
    expires = datetime.now().replace(tzinfo=pytz.UTC) + timedelta(hours=6)

    try:
        s3.upload_file(
            path,
            settings.AWS_STORAGE_BUCKET_NAME,
            name,
            ExtraArgs={"Expires": expires},
        )
    except Exception:
        return False

    # Delete file
    os.remove(path)
    return True


def format_km(km, left_padding=0, separator="+"):
    try:
        numbers = format(round(km, 3), ".3f").split(".")
        zero_left = left_padding - len(numbers[0])
        zero_left = zero_left if zero_left > 0 else 0
        return "{}{}{}{:03d}".format(
            "0" * zero_left, int(numbers[0]), separator, int(numbers[1])
        )
    except Exception:
        return ""


def formatted_m_area(area) -> str:
    if area:
        result = ("{:.2f} m²".format(area)).replace(".", ",")
        return result


def get_km_plus_meter(km: str) -> str:
    try:
        data_list = _ = str(km).split(".") if "." in str(km) else [str(km), "0"]
        _km = data_list[0].zfill(3)
        _mt = data_list[1].ljust(3, "0")
        return f"{_km}+{_mt}"
    except Exception:
        return ""


DIRECTION_LOOKUP = {
    "Sul": "S",
    "Norte": "N",
    "Canteiro Central": "CC",
    "Leste": "L",
    "Oeste": "O",
    "Norte/Sul": "NS",
    "Leste/Oeste": "LO",
    "Crescente": "C",
    "Decrescente": "D",
    "Ambos": "A",
    "Transversal": "TR",
}


def get_direction_letter(direction):
    return DIRECTION_LOOKUP[direction]


def insert_centered_value(
    worksheet: Worksheet,
    value: str,
    cell: str,
    horizontal="center",
    vertical="center",
    wrapText=None,
    bold=None,
    number_format=None,
):
    try:
        _cell: Cell = worksheet[cell]
        _cell.value = value
        alignemnt = Alignment(horizontal=horizontal, vertical=vertical)
        if wrapText is not None:
            alignemnt.wrap_text = wrapText
        if bold is not None:
            _cell.font = bold
        if number_format is not None:
            _cell.number_format = number_format
        _cell.alignment = alignemnt
    except Exception:
        pass


def worksheet_remove_columns(worksheet: Worksheet, columns_to_remove: list):
    """
    Remove colunas especificadas de uma planilha do Excel, mantendo os valores e estilos.

    Esta função remove colunas de uma planilha do Excel identificadas por letras
    (por exemplo, 'A', 'B', 'Z', 'AA') ou índices numéricos. Os valores e estilos das colunas
    não removidas são preservados e ajustados. Fusões de células são recalculadas se necessário.

    Parâmetros:
    - worksheet (Worksheet): A planilha do Excel de onde as colunas serão removidas.
    - columns_to_remove (list): Uma lista contendo as colunas a serem removidas.
    """

    # Convert letters to indices if necessary
    columns = []
    for column in columns_to_remove:
        if isinstance(column, str) and not column.isnumeric():
            columns.append(column_index_from_string(column))
        elif isinstance(column, int):
            columns.append(column)

    # Sort columns in reverse order to avoid shifting issues
    columns.sort(reverse=True)
    # Remove the columns
    for column in columns:
        worksheet.delete_cols(column)
        for mcr in worksheet.merged_cells:
            if column < mcr.min_col:
                mcr.shift(col_shift=-1)
            elif column <= mcr.max_col:
                mcr.shrink(right=1)

    clean_remove_col = worksheet.max_column + 1

    worksheet.delete_cols(idx=clean_remove_col, amount=len(columns))


def get_conditions_date(panel_uuid: str, filter: str, data_pattern: str):
    conditions = (
        RecordPanel.objects.filter(uuid=panel_uuid)
        .only("conditions")[:1]
        .get()
        .conditions
    )
    conditions_query_params = str(
        convert_conditions_to_query_params(conditions["logic"])
    )
    pattern = r"\(\'" + filter + r"\'\, \'(" + data_pattern + r")\'\)"
    match = re.search(pattern, conditions_query_params).group(1)
    return match


def get_recovery_occurrence_kinds(company_uuid: UUID, report_name: str):
    recovery_occurrence_kinds = []
    try:
        metadata = (
            Company.objects.filter(uuid=company_uuid).only("metadata")[0].metadata
        )
        options: dict = metadata["extraReportingExports"][report_name]["options"]
        recovery_occurrence_kinds = options["recovery_occurrence_kinds"]
    except Exception as e:
        print(e)
    return recovery_occurrence_kinds
