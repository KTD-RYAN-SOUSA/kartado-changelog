import itertools
import os
from datetime import datetime, timedelta

import boto3
import pytz
from arrow import Arrow
from django.conf import settings
from openpyxl import Workbook
from rest_framework_json_api import serializers

from apps.occurrence_records.const.custom_table import (
    CUSTOM_TABLE_COLUMN_BREAKS,
    CUSTOM_TABLE_TYPES,
    DAILY,
    DATA_DAILY,
    DATA_HOURLY,
    DATA_MONTHLY,
    HOURLY,
    MONTHLY,
    VLR_DAILY,
    VLR_HOURLY,
    VLR_MONTHLY,
)
from apps.occurrence_records.const.sih_frequencies import SIH_FREQUENCIES
from apps.occurrence_records.models import TableDataSeries
from helpers.dates import utc_to_local
from helpers.sih_integration import fetch_sih_data
from RoadLabsAPI.settings import credentials


def uniq_with(in_list, extractor):
    b_list = [extractor(a) for a in in_list]
    return [a for i, a in enumerate(in_list) if b_list.index(extractor(a)) == i]


class SihTable:
    """
    Essa classe tem como objetivo gerar dados para representação de uma tabela para utilização com o plotly,
    a partir de algumas definições de entrada, e dados obtidos através de integração com o SIH
    """

    row_range_dict = {
        "HOURLY": "hour",
        "DAILY": "day",
        "MONTHLY": "month",
    }

    row_uniq_extractor_dict = {
        "DAY": {
            "HOURLY": lambda x: x.hour,
        },
        "MONTH": {
            "DAILY": lambda x: x.day,
            "HOURLY": lambda x: x.strftime("%d %H"),
        },
        "YEAR": {
            "MONTHLY": lambda x: x.month,
            "DAILY": lambda x: x.strftime("%m %d"),
            "HOURLY": lambda x: x.strftime("%m %d %H"),
        },
    }

    row_sort_extractor_dict = {
        "DAY": {"HOURLY": lambda x: x.hour},
        "MONTH": {
            "DAILY": lambda x: x.day,
            "HOURLY": lambda x: x.day * 100 + x.hour,
        },
        "YEAR": {
            "DAILY": lambda x: x.month * 100 + x.day,
            "HOURLY": lambda x: x.month * 10000 + x.day * 100 + x.hour,
            "MONTHLY": lambda x: x.month,
        },
    }

    row_freq_translations = {
        "MONTHLY": "Mês",
        "DAILY": "Dia",
        "HOURLY": "Horário",
    }

    columns_break_strf_dict = {
        "DAY": "%Y-%m-%d",
        "MONTH": "%Y-%m",
        "YEAR": "%Y",
    }

    line_frequency_strf_dict = {
        "DAY": {
            "HOURLY": "%H:%M:%S",
        },
        "MONTH": {
            "HOURLY": "%d %H:%M:%S",
            "DAILY": "%d",
        },
        "YEAR": {
            "HOURLY": "%d/%m %H:%M:%S",
            "DAILY": "%d/%m",
            "MONTHLY": "%m",
        },
    }

    sih_response_date_key_dict = {
        "HOURLY": DATA_HOURLY,
        "DAILY": DATA_DAILY,
        "MONTHLY": DATA_MONTHLY,
    }

    sih_response_value_key_dict = {
        "HOURLY": VLR_HOURLY,
        "DAILY": VLR_DAILY,
        "MONTHLY": VLR_MONTHLY,
    }

    additional_options = {
        "SUM": "Soma",
        "AVG": "Média",
        "MAX": "Máximo",
        "REFMAX": "Referência do máximo",
        "MIN": "Mínimo",
        "REFMIN": "Referência do mínimo",
    }

    def compute_ref(self, values, position, operation_name):
        operation = self.common_operations[operation_name]
        operation_result = operation(values)
        if type(operation_result) is int or type(operation_result) is float:
            found_index = values.index(operation_result)
            if position == "column":
                return self.get_header()["values"][found_index + 1]
            elif position == "line":
                return self.get_first_column_values()[found_index]
        return ""

    common_operations = {
        "SUM": lambda x: sum(x) if len(x) else "",
        "AVG": lambda x: sum(x) / len(x) if len(x) else "",
        "MAX": lambda x: max(x) if len(x) else "",
        "MIN": lambda x: min(x) if len(x) else "",
    }

    def execute_operation(self, operation, values, position):
        if position == "column":
            operations = {
                **self.common_operations,
                "REFMAX": lambda x: self.compute_ref(x, "column", "MAX"),
                "REFMIN": lambda x: self.compute_ref(x, "column", "MIN"),
            }
        else:
            operations = {
                **self.common_operations,
                "REFMAX": lambda x: self.compute_ref(x, "line", "MAX"),
                "REFMIN": lambda x: self.compute_ref(x, "line", "MIN"),
            }
        result = operations[operation]([a for a in values if a is not None])
        if type(result) in [int, float]:
            return round(result, 2)
        return result

    def __init__(self, table=None, raw_data=None):
        if table:
            self.init_from_table(table)
        elif raw_data:
            self.init_from_raw_data(raw_data)
        else:
            raise Exception("You need to provide table object or raw_data")

        if self.table_type == "COMPARISON":
            self.infer_comparison_columns_break()

        if self.table_type == "ANALYSIS":
            self.get_column_datetimes()

        self.get_row_datetimes()
        self.get_postos()
        self.get_itens()

    def infer_comparison_columns_break(self):
        # Although comparison tables don't have a columns_break parameter,
        # lets infer it from the start and end period to make some operations easier later
        columns_break = "DAY"
        if self.end_period.strftime("%d/%m/%Y") != self.start_period.strftime(
            "%d/%m/%Y"
        ):
            columns_break = "MONTH"
        if self.end_period.strftime("%m/%Y") != self.start_period.strftime("%m/%Y"):
            columns_break = "YEAR"
        self.columns_break = columns_break

    def init_from_table(self, table):
        self.columns_break = table.columns_break
        self.line_frequency = table.line_frequency
        self.start_period = table.start_period
        self.end_period = table.end_period
        self.data_series = table.table_data_series.order_by("name")
        self.table_type = table.table_type
        self.additional_columns = table.additional_columns
        self.additional_lines = table.additional_lines
        self.name = table.name

    def init_from_raw_data(self, raw_data):
        if raw_data["line_frequency"] not in [a[0] for a in SIH_FREQUENCIES]:
            raise serializers.ValidationError(
                "kartado.custom_table_preview.invalid_line_frequency"
            )
        self.line_frequency = raw_data["line_frequency"]

        if raw_data["table_type"] not in [a[0] for a in CUSTOM_TABLE_TYPES]:
            raise serializers.ValidationError(
                "kartado.custom_table_preview.invalid_table_type"
            )
        self.table_type = raw_data["table_type"]

        if self.table_type == "ANALYSIS":
            if raw_data["columns_break"] not in [
                a[0] for a in CUSTOM_TABLE_COLUMN_BREAKS
            ]:
                raise serializers.ValidationError(
                    "kartado.custom_table_preview.invalid_columns_break"
                )
            self.columns_break = raw_data["columns_break"]

        try:
            self.start_period = datetime.strptime(raw_data["start_period"], "%Y-%m-%d")
        except Exception:
            raise serializers.ValidationError(
                "kartado.custom_table_preview.invalid_start_period"
            )

        try:
            self.end_period = datetime.strptime(raw_data["end_period"], "%Y-%m-%d")
        except Exception:
            raise serializers.ValidationError(
                "kartado.custom_table_preview.invalid_end_period"
            )

        try:
            self.data_series = TableDataSeries.objects.filter(
                uuid__in=raw_data["table_data_series"].split(",")
            ).order_by("name")
        except Exception:
            raise serializers.ValidationError(
                "kartado.custom_table_preview.invalid_table_data_series"
            )

        if "additional_columns" in raw_data:
            self.additional_columns = raw_data["additional_columns"].split(",")
            if not all([a in self.additional_options for a in self.additional_columns]):
                raise serializers.ValidationError(
                    "kartado.custom_table_preview.invalid_aditional_columns"
                )
        else:
            self.additional_columns = []

        if "additional_lines" in raw_data:
            self.additional_lines = raw_data["additional_lines"].split(",")
            if not all([a in self.additional_options for a in self.additional_lines]):
                raise serializers.ValidationError(
                    "kartado.custom_table_preview.invalid_aditional_lines"
                )
        else:
            self.additional_lines = []

    def get_column_datetimes(self):
        column_range_start = self.start_period
        column_range_end = self.end_period
        if self.columns_break == "MONTH":
            column_range_start = column_range_start.replace(day=1)
            next_month = column_range_end.replace(day=28) + timedelta(days=4)
            column_range_end = next_month - timedelta(days=next_month.day)
        if self.columns_break == "YEAR":
            column_range_start = column_range_start.replace(day=1, month=1)
            column_range_end = column_range_end.replace(day=31, month=12)

        column_datetimes = [
            a.datetime
            for a in Arrow.range(
                self.columns_break.lower(),
                datetime(
                    column_range_start.year,
                    column_range_start.month,
                    column_range_start.day,
                ),
                datetime(
                    column_range_end.year,
                    column_range_end.month,
                    column_range_end.day,
                ),
            )
        ]
        self.column_datetimes = column_datetimes

    def get_row_datetimes(self):
        # TODO: Deal with cases when column_break is YEAR and line_frequency is DAY, for example
        sort_extractor = self.row_sort_extractor_dict[self.columns_break][
            self.line_frequency
        ]
        uniq_extractor = self.row_uniq_extractor_dict[self.columns_break][
            self.line_frequency
        ]
        row_datetimes = uniq_with(
            sorted(
                [
                    a.datetime
                    for a in Arrow.range(
                        self.row_range_dict[self.line_frequency],
                        datetime(
                            self.start_period.year,
                            self.start_period.month,
                            self.start_period.day,
                        ),
                        datetime(
                            self.end_period.year,
                            self.end_period.month,
                            self.end_period.day,
                        ),
                    )
                ],
                key=sort_extractor,
            ),
            uniq_extractor,
        )
        self.row_datetimes = row_datetimes

    def get_postos(self):
        self.postos = list(
            self.data_series.values_list(
                "instrument_record__form_data__uposto", flat=True
            )
        )

    def get_itens(self):
        self.itens = list(
            self.data_series.values_list(
                "sih_monitoring_parameter__form_data__uabrev", flat=True
            )
        )

    def get_header(self):
        header = {"values": []}

        if self.table_type == "ANALYSIS":
            header = self.get_analysis_header()
        elif self.table_type == "COMPARISON":
            header = self.get_comparison_header()

        for additional_column in self.additional_columns:
            header["values"].append(self.additional_options[additional_column])

        return header

    def get_comparison_header(self):
        return {
            "values": [
                self.row_freq_translations[self.line_frequency],
                *self.data_series.values_list("name", flat=True),
            ],
        }

    def get_analysis_header(self):
        date_format = self.columns_break_strf_dict[self.columns_break]

        date_range = [a.strftime(date_format) for a in self.column_datetimes]

        return {
            "values": [
                self.row_freq_translations[self.line_frequency],
                *date_range,
            ],
        }

    def get_first_column_values(self):
        # [columns_break][line_frequency]
        date_format = self.line_frequency_strf_dict[self.columns_break][
            self.line_frequency
        ]

        first_column_values = [a.strftime(date_format) for a in self.row_datetimes]

        for additional_line in self.additional_lines:
            first_column_values.append(self.additional_options[additional_line])

        return first_column_values

    def get_sih_values(self):
        if self.table_type == "ANALYSIS":
            return self.get_analysis_sih_values()
        elif self.table_type == "COMPARISON":
            return self.get_comparison_sih_values()
        else:
            return []

    def parse_sih_datetime(self, value):
        parsed_datetime = datetime.strptime(
            value[:-10],
            "%Y-%m-%dT%H:%M:%S",
        )
        # SIH returns the last value of the day as 23:59. Convert it to 00:00 of the following day
        if parsed_datetime.hour == 23 and parsed_datetime.minute == 59:
            parsed_datetime += timedelta(minutes=1)

        return parsed_datetime

    def parse_value(self, value):
        if value == "":
            return None
        try:
            return float(value)
        except Exception:
            return 0

    def get_row_data(self, value_columns, index):
        return [
            self.parse_value(a[index] if len(a) > index + 1 else "")
            for a in value_columns
        ]

    def get_analysis_sih_values(self):
        start_date = (self.start_period - timedelta(days=1)).strftime("%d/%m/%Y")
        end_date = (self.end_period + timedelta(days=1)).strftime("%d/%m/%Y")
        sih_data = fetch_sih_data(
            self.postos, self.itens, self.line_frequency, start_date, end_date
        )
        parsed_sih_data = [
            {
                "datetime": self.parse_sih_datetime(
                    a[self.sih_response_date_key_dict[self.line_frequency]]
                ),
                "value": a[self.sih_response_value_key_dict[self.line_frequency]],
            }
            for a in sih_data
        ]

        match_functions = {
            "DAY": {
                HOURLY: lambda a, row, column: a.day == column.day
                and a.hour == row.hour
            },
            "MONTH": {
                HOURLY: lambda a, row, column: a.month == column.month
                and a.day == row.day
                and a.hour == row.hour,
                DAILY: lambda a, row, column: a.month == column.month
                and a.day == row.day,
            },
            "YEAR": {
                HOURLY: lambda a, row, column: a.year == column.year
                and a.month == row.month
                and a.day == row.day
                and a.hour == row.hour,
                DAILY: lambda a, row, column: a.year == column.year
                and a.month == row.month
                and a.day == row.day,
                MONTHLY: lambda a, row, column: a.year == column.year
                and a.month == row.month,
            },
        }

        value_columns = []
        for column in self.column_datetimes:
            column_data = []
            for row in self.row_datetimes:
                try:
                    value = next(
                        a["value"]
                        for a in parsed_sih_data
                        if match_functions[self.columns_break][self.line_frequency](
                            a["datetime"], row, column
                        )
                    )
                except Exception:
                    value = ""
                column_data.append(value)
            value_columns.append(column_data)

        additional_columns = []
        for column in self.additional_columns:
            column_data = []
            for index, row in enumerate(self.row_datetimes):
                source_data = self.get_row_data(value_columns, index)
                column_data.append(
                    self.execute_operation(column, source_data, "column")
                )
            additional_columns.append(column_data)

        additional_lines = []
        for line in self.additional_lines:
            line_data = []
            for column in value_columns:
                line_data.append(
                    self.execute_operation(
                        line, [self.parse_value(a) for a in column], "line"
                    )
                )
            additional_lines.append(line_data)

        for line in additional_lines:
            for index, column in enumerate(value_columns):
                column.append(line[index])

        return value_columns + additional_columns

    def get_comparison_sih_values(self):
        start_date = self.start_period.strftime("%d/%m/%Y")
        end_date = self.end_period.strftime("%d/%m/%Y")
        sih_data = fetch_sih_data(
            self.postos, self.itens, self.line_frequency, start_date, end_date
        )
        parsed_sih_data = [
            {
                "datetime": self.parse_sih_datetime(
                    a[self.sih_response_date_key_dict[self.line_frequency]]
                ),
                "value": a[self.sih_response_value_key_dict[self.line_frequency]],
                "posto": a["cod_posto_hidromet"],
                "item": a["cod_item_hidromet"],
            }
            for a in sih_data
        ]

        match_functions = {
            HOURLY: lambda a, row: a.year == row.year
            and a.month == row.month
            and a.day == row.day
            and a.hour == row.hour,
            DAILY: lambda a, row: a.year == row.year
            and a.month == row.month
            and a.day == row.day,
            MONTHLY: lambda a, row: a.year == row.year and a.month == row.month,
        }

        value_columns = []

        for data_series in self.data_series:
            data_series_values = [
                a
                for a in parsed_sih_data
                if a["posto"] == str(data_series.instrument_record.form_data["uposto"])
                and a["item"]
                == str(data_series.sih_monitoring_parameter.form_data["uabrev"])
            ]
            column_data = []
            for row in self.row_datetimes:
                try:
                    value = next(
                        a["value"]
                        for a in data_series_values
                        if match_functions[self.line_frequency](a["datetime"], row)
                    )
                except Exception:
                    value = ""
                column_data.append(value)
            value_columns.append(column_data)

        additional_columns = []
        for column in self.additional_columns:
            column_data = []
            for index, row in enumerate(self.row_datetimes):
                source_data = self.get_row_data(value_columns, index)
                column_data.append(
                    self.execute_operation(column, source_data, "column")
                )
            additional_columns.append(column_data)

        additional_lines = []
        for line in self.additional_lines:
            line_data = []
            for column in value_columns:
                line_data.append(
                    self.execute_operation(
                        line, [self.parse_value(a) for a in column], "line"
                    )
                )
            additional_lines.append(line_data)

        for line in additional_lines:
            for index, column in enumerate(value_columns):
                column.append(line[index])

        return value_columns + additional_columns

    def get_cells(self):
        return {
            "values": [self.get_first_column_values(), *self.get_sih_values()],
        }

    def get_table_description(self):
        return [
            {
                "type": "table",
                "mode": "markers",
                "header": self.get_header(),
                "cells": self.get_cells(),
            },
        ]

    def upload_file(self, path, name):
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        expires = datetime.now().replace(tzinfo=pytz.UTC) + timedelta(hours=6)
        object_name = "media/private/{}".format(name)

        s3 = boto3.client(
            "s3",
            aws_access_key_id=credentials.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=credentials.AWS_SECRET_ACCESS_KEY,
            aws_session_token=credentials.AWS_SESSION_TOKEN,
        )

        try:
            s3.upload_file(
                path, bucket_name, object_name, ExtraArgs={"Expires": expires}
            )
        except Exception as e:
            print(e)
            return False

        # Delete file
        os.remove(path)

        url_s3 = s3.generate_presigned_url(
            "get_object", Params={"Bucket": bucket_name, "Key": object_name}
        )
        return url_s3

    def get_url(excel_name):
        empty = {"url": "", "name": ""}

        s3 = boto3.client(
            "s3",
            aws_access_key_id=credentials.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=credentials.AWS_SECRET_ACCESS_KEY,
            aws_session_token=credentials.AWS_SESSION_TOKEN,
        )

        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        object_name = "media/private/{}".format(excel_name + ".xlsx")

        url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": bucket_name, "Key": object_name}
        )

        if not url:
            return empty

        return {"url": url, "name": excel_name + ".xlsx"}

    def get_excel_name(self):
        now = utc_to_local(datetime.now())
        return "Tabela_{}_{}_{}_{}_{}_{}.xlsx".format(
            self.name, now.day, now.month, now.year, now.hour, now.minute
        )

    def get_excel(self):
        header = self.get_header()
        cells = self.get_cells()
        transposed_cells = list(
            map(list, itertools.zip_longest(*cells["values"], fillvalue=None))
        )

        wb = Workbook()
        ws = wb.active
        ws.append(header["values"])
        for row in transposed_cells:
            ws.append(row)

        excel_name = self.get_excel_name()
        print(excel_name)

        wb.save("/tmp/" + excel_name)
        url = self.upload_file("/tmp/" + excel_name, excel_name)

        return url
