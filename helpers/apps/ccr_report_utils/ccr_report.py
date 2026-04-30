import json
from typing import Any, List

from django.core import serializers
from django.db.models.query import QuerySet

from helpers.apps.ccr_report_utils.export_utils import get_random_string
from helpers.apps.ccr_report_utils.image import ReportFormat, SheetTarget


class CCRReport:
    def __init__(
        self, uuids: List[str] = None, report_format: ReportFormat = ReportFormat.XLSX
    ) -> None:
        self.uuids = uuids
        self._report_format = report_format
        self._sheet_target = (
            SheetTarget.DesktopExcel
            if report_format == ReportFormat.XLSX
            else SheetTarget.GotenbergPrinter
        )

        if uuids:
            self.file_name = self.get_file_name()
            self.object_name = self.get_object_name()

    def dict(self) -> dict:
        return self.__dict__

    @classmethod
    def from_dict(cls, instance_dict: dict) -> Any:  # Self
        instance = cls()
        for k, v in instance_dict.items():
            setattr(instance, k, v)
        return instance

    def serializer_queryset(self, queryset: QuerySet):
        return serializers.serialize("json", queryset)

    def deserializer_queryset(self, json_string):
        try:
            # Verifica se a string é um JSON válido
            json.loads(json_string)
            array = []
            gen = serializers.deserialize("json", json_string)
            for obj in gen:
                obj_instance = obj.object  # Obtenha a instância do modelo Django
                # Realize o processamento necessário no obj_instance
                array.append(obj_instance)
            return array
        except json.JSONDecodeError:
            return json_string

    def report_format(self) -> ReportFormat:
        return self._report_format

    def sheet_target(self) -> SheetTarget:
        return self._sheet_target

    def get_object_name(self):
        random_string = get_random_string()
        file_name_segments = self.file_name.split(".")
        root_name = ".".join(file_name_segments[:-1])
        extension = file_name_segments[-1]

        object_name = "media/private/{}_{}.{}".format(
            root_name, random_string, extension
        )
        return object_name

    def get_file_name(self) -> str:
        raise NotImplementedError

    def export(self):
        raise NotImplementedError
