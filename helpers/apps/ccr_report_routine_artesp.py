import re
import shutil
import tempfile
from datetime import datetime
from os.path import isfile
from pathlib import Path
from typing import Dict, List, Tuple
from zipfile import ZipFile

from django.db.models import Prefetch
from openpyxl.drawing.image import Image
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from apps.reportings.models import Reporting, ReportingFile
from helpers.apps.ccr_report_utils.artesp_road_names import get_artesp_full_road_name
from helpers.apps.ccr_report_utils.ccr_report import CCRReport
from helpers.apps.ccr_report_utils.export_utils import format_km, get_s3, upload_file
from helpers.apps.ccr_report_utils.form_data import (
    get_form_array_iterator,
    new_get_form_data,
)
from helpers.apps.ccr_report_utils.image import (
    ReportFormat,
    ResizeMethod,
    SheetTarget,
    get_image,
    get_logo_file,
    get_provider_logo_file,
    get_subcompany_logo_file,
    insert_picture_2,
)
from helpers.apps.ccr_report_utils.pdf import convert_files_to_pdf
from helpers.apps.ccr_report_utils.reporting_utils import get_custom_option
from helpers.apps.ccr_report_utils.workbook_utils import set_active_cell, set_zoom
from helpers.kartado_excel.workbook import load_workbook
from helpers.strings import clean_latin_string


class XlsxHandler(object):
    _EXPORT_NAME = ""
    _TEMPLATE_FILE = ""
    _LOGO_CELL = ""  # Cell or cell range like string. Ex "A1"; "A1:B2"
    _PROVIDER_LOGO_CELL = ""  # Cell or cell range like string. Ex "A1"; "A1:B2"
    _SUBCOMPANY_LOGO_CELL = ""  # Cell or cell range like string. Ex "A1"; "A1:B2"
    _FILE_NAME_CODE = "R"

    _EXPORT_CLASS: type = (
        None  # Corresponding export super class (RoutineARTESP, or InitialARTESP, ...)"
    )

    _PICTURE_CODE_PATTERN = re.compile(
        r"R(\d{7})k(\d{6})F(\d{3})([A-Z]{1,2})"
    )  # Regex to check picture code
    _PICTURE_NUM_INDEX = 2  # Group of picture index in code

    _PICTURE_TEMPLATE_TITLE = "FOTO 1"  # Title of picture sheet template

    _PICTURE_PROVIDER_LOGO_CELL = ""  # Cell or cell range like string. Ex "A1"; "A1:B2"
    _PICTURE_TEAM_LOGO_CELL = ""  # Cell or cell range like string. Ex "A1"; "A1:B2"

    _OAE_NUM_CELL = "N1"  # Cell like string. Ex "A1"
    _EXECTUTED_AT_CELL = ""  # Cell like string. Ex "A1"
    _COMPANY_CELL = ""  # Cell like string. Ex "A1"
    _ROAD_NAME_CELL = ""  # Cell like string. Ex "A1"
    _DIRECTION_CELL = ""  # Cell like string. Ex "A1"
    _KM_CELL = ""  # Cell like string. Ex "A1"

    _SIMPLE_PIC_FORM_DATA_FIELDS: Dict[
        str, str
    ] = {}  # Dict of form field api name to cell. EX: "oaeNumeroCodigoObra": "Q1"
    _PIC_OAE_NUM_CELL = "Q1"  # Cell like string. Ex "A1"
    _PIC_EXECTUTED_AT_CELL = ""  # Cell like string. Ex "A1"

    _MONTH = [
        "jan",
        "fev",
        "mar",
        "abr",
        "mai",
        "jun",
        "jul",
        "ago",
        "set",
        "out",
        "nov",
        "dez",
    ]

    _SIMPLE_FORM_DATA_FIELDS: Dict[
        str, str
    ] = {}  # Dict of form field api name to cell. EX: "oaeNumeroCodigoObra": "Q1"

    _DATE_FORM_DATA_FIELDS: Dict[
        str, str
    ] = {}  # Dict of form field api name to cell. EX: "oaeNumeroCodigoObra": "Q1"

    _THERAPY_DESC_CELL = ""  # Cell like string. Ex "A1"

    _PICTURE_RANGES: List[
        str
    ] = []  # List of cell or cell range like strings. Ex ["A1:B1", "C1:D2"]
    _PICTURE_CODE_CELLS: List[str] = []  # List of cell like strings. Ex ["A1", "B2"]
    _PICTURE_DESCRIPTION_CELLS: List[
        str
    ] = []  # List of cell like strings. Ex ["A1", "B2"]

    @classmethod
    def _get_direction_acronym(cls, reporting: Reporting) -> str:
        acronym = ""
        try:
            words = re.split("[^a-zA-Z]", get_custom_option(reporting, "direction"))
            for word in words:
                acronym += word[0]
        except Exception:
            pass
        return acronym

    @classmethod
    def _get_therapy_descriptions(cls, reporting: Reporting) -> str:
        count = 1
        therapy_description = ""

        it = get_form_array_iterator(reporting, "therapy")
        try:
            while True:
                description = it.get("description")
                if description is not None:
                    description_str = str(description).strip()
                    if description_str != "":
                        therapy_description += f"{count} - {description_str}"
                        count += 1
                it.inc()
                if description is not None:
                    therapy_description += ";\n"
        except Exception as e:
            print(e)

        if count > 1:
            therapy_description += "."
        else:
            therapy_description = "Por ora, não há recomendações de terapia."

        return therapy_description

    @classmethod
    def _get_picture_sorting_key(
        cls, reporting_file: ReportingFile
    ) -> Tuple[int, int, datetime, datetime]:
        sorting_key = None

        proper_name = False
        num = 0
        try:
            file_name = reporting_file.upload.name.split("_")[0]
            file_name = file_name.split(".")[0]
            match = cls._PICTURE_CODE_PATTERN.fullmatch(file_name)
            if match is not None:
                num = int(match.group(cls._PICTURE_NUM_INDEX + 1))
                proper_name = True
        except Exception:
            pass

        if proper_name:
            _ = datetime.now()
            sorting_key = (0, num, _, _)
        else:
            date = reporting_file.datetime
            uploaded_at = reporting_file.uploaded_at
            sorting_key = (1, num, date, uploaded_at)

        return sorting_key

    @classmethod
    def __get_reportings(cls, uuids: List[str]) -> List[Reporting]:
        return (
            Reporting.objects.filter(uuid__in=uuids)
            .prefetch_related(
                "occurrence_type",
                "company",
                "firm",
                "firm__subcompany",
                "road",
                Prefetch(
                    lookup="reporting_files",
                    queryset=ReportingFile.objects.filter(is_shared=True).only(
                        "uuid",
                        "reporting__uuid",
                        "upload",
                        "uploaded_at",
                        "datetime",
                        "description",
                    ),
                ),
            )
            .only(
                "uuid",
                "occurrence_type__uuid",
                "road_name",
                "road_id",
                "direction",
                "km",
                "form_data",
                "executed_at",
                "company",
                "firm",
                "firm__subcompany",
            )
        )

    @classmethod
    def _get_worksheet_title(cls, reporting: Reporting) -> str:
        km = format_km(reporting.km, 3)
        direction = get_custom_option(reporting, "direction")
        dir_acronym = cls._EXPORT_CLASS.DIRECTION_ACRONYM.get(direction.lower(), "")
        return f"OAE {km}{dir_acronym}"

    @classmethod
    def _get_company_display_name(cls, company_name: str) -> str:
        mapping = {
            "CCR - SPVIAS": "SPVIAS - Rodovias Integradas do Oeste S.A.",
            "CCR - AUTOBAN": "AUTOBAN - Concessionária do Sistema Anhanguera-Bandeirante S.A.",
            "CCR - RODOANEL": "RODOANEL - Concessionária do Rodoanel Oeste S.A.",
        }
        key_company_name = company_name.strip().upper()
        return mapping.get(key_company_name, company_name)

    def __init__(
        self,
        uuids: List[str],
        s3,
        sheet_target: SheetTarget = SheetTarget.DesktopExcel,
        report_format: ReportFormat = ReportFormat.XLSX,
    ):
        self.__report_format = report_format
        self.__sheet_target = sheet_target
        self.s3 = s3
        self.__temp_dir = tempfile.mkdtemp()

        self.uuids: List[str] = uuids

    def clean_files(self):
        shutil.rmtree(self.__temp_dir, ignore_errors=True)

    def __del__(self):
        self.clean_files()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.clean_files()

    @classmethod
    def _insert_logos(
        cls,
        s3,
        temp_dir: str,
        sheet_target: SheetTarget,
        workbook: Workbook,
        reporting: Reporting,
        picture_sheets: List[Worksheet],
    ) -> None:
        logo = get_logo_file(s3, temp_dir, reporting)
        provider_logo = get_provider_logo_file(s3, temp_dir, reporting)
        subcompany_logo = get_subcompany_logo_file(s3, temp_dir, reporting)

        normal_sheets = [ws for ws in workbook.worksheets if ws not in picture_sheets]
        for worksheet in normal_sheets:
            try:
                insert_picture_2(
                    worksheet,
                    cls._LOGO_CELL,
                    Image(logo),
                    sheet_target,
                    border_width=(2, 2, 2, 2),
                    resize_method=ResizeMethod.ProportionalCentered,
                )
            except Exception:
                pass
            try:
                insert_picture_2(
                    worksheet,
                    cls._SUBCOMPANY_LOGO_CELL,
                    Image(subcompany_logo),
                    sheet_target,
                    border_width=(2, 2, 2, 2),
                    resize_method=ResizeMethod.ProportionalCentered,
                )
            except Exception:
                pass
            try:
                insert_picture_2(
                    worksheet,
                    cls._PROVIDER_LOGO_CELL,
                    Image(provider_logo),
                    sheet_target,
                    border_width=(2, 2, 2, 2),
                    resize_method=ResizeMethod.ProportionalCentered,
                )
            except Exception:
                pass

        for pic_worksheet in picture_sheets:

            try:
                insert_picture_2(
                    pic_worksheet,
                    cls._LOGO_CELL,
                    Image(logo),
                    sheet_target,
                    border_width=(2, 2, 2, 2),
                    resize_method=ResizeMethod.ProportionalCentered,
                )
            except Exception:
                pass
            try:
                insert_picture_2(
                    pic_worksheet,
                    cls._PICTURE_TEAM_LOGO_CELL,
                    Image(subcompany_logo),
                    sheet_target,
                    border_width=(2, 2, 2, 2),
                    resize_method=ResizeMethod.ProportionalCentered,
                )
            except Exception:
                pass
            try:
                insert_picture_2(
                    pic_worksheet,
                    cls._PICTURE_PROVIDER_LOGO_CELL,
                    Image(provider_logo),
                    sheet_target,
                    border_width=(2, 2, 2, 2),
                    resize_method=ResizeMethod.ProportionalCentered,
                )
            except Exception:
                pass

    @classmethod
    def _get_pic_reporting_files(cls, reporting: Reporting) -> List[ReportingFile]:
        rfs: Dict[str, ReportingFile] = {
            str(rf.uuid): rf for rf in reporting.reporting_files.all()
        }
        rf_uuids: List[str] = []

        it = get_form_array_iterator(reporting, "relatorio")
        try:
            while True:
                report_pictures = it.get("fotosRelatorio")
                if isinstance(report_pictures, list):
                    rf_uuids.extend(report_pictures)
                it.inc()
        except Exception as e:
            print(e)

        return [rfs[uuid] for uuid in rf_uuids if uuid in rfs]

    @classmethod
    def _get_picture_code(cls, reporting: Reporting, picture_index: int) -> str:
        year = cls._EXPORT_CLASS.get_padded_inspection_campaing_year(reporting)
        road_km = ""
        nums = re.findall(r"\d{3}", reporting.road_name)
        if len(nums) > 0:
            road_km = nums[0]
        km = format_km(reporting.km, 3, "")
        direction = get_custom_option(reporting, "direction")
        dir_acronym = cls._EXPORT_CLASS.DIRECTION_ACRONYM.get(direction.lower(), "")
        return f"{cls._FILE_NAME_CODE}{year}{road_km}k{km}F{(picture_index+1):03}{dir_acronym}"

    def _fill_picture_sheets(
        self, pic_temp_dir: str, workbook: Workbook, reporting: Reporting
    ) -> List[Worksheet]:
        cls = type(self)
        reporting_files = cls._get_pic_reporting_files(reporting)
        reporting_files = sorted(reporting_files, key=cls._get_picture_sorting_key)

        template_sheet = workbook[cls._PICTURE_TEMPLATE_TITLE]
        worksheet: Worksheet = workbook.copy_worksheet(template_sheet)
        pic_count = 0

        pic_sheets: List[Worksheet] = [template_sheet, worksheet]

        last_sheet_is_empty = True
        for rf in reporting_files:
            try:
                image = get_image(
                    self.s3,
                    pic_temp_dir,
                    "temp-" + str(rf.uuid),
                    rf,
                )
                range_index = pic_count % 4
                try:
                    code = cls._get_picture_code(reporting, pic_count)
                    description = rf.description if rf.description is not None else ""
                    worksheet[cls._PICTURE_CODE_CELLS[range_index]] = code + ":"
                    worksheet[cls._PICTURE_DESCRIPTION_CELLS[range_index]] = description
                    insert_picture_2(
                        worksheet,
                        cls._PICTURE_RANGES[range_index],
                        image,
                        self.__sheet_target,
                        border_width=(2, 2, 2, 2),
                        resize_method=ResizeMethod.ProportionalCentered,
                    )
                    last_sheet_is_empty = False
                except Exception as e:
                    worksheet[cls._PICTURE_CODE_CELLS[range_index]] = ""
                    worksheet[cls._PICTURE_DESCRIPTION_CELLS[range_index]] = ""
                    raise e

                pic_count = pic_count + 1
                if pic_count == 60:
                    break
                if range_index == 3:
                    worksheet = workbook.copy_worksheet(template_sheet)
                    pic_sheets.append(worksheet)
                    last_sheet_is_empty = True
            except Exception:
                pass

        if pic_count > 0:
            pic_sheets.remove(template_sheet)
            workbook.remove(template_sheet)
        if last_sheet_is_empty:
            pic_sheets.remove(worksheet)
            workbook.remove(worksheet)

        sheet_count = 0
        for worksheet in pic_sheets:
            sheet_count += 1
            worksheet.title = f"FOTOS {sheet_count}"
            executed_at = (
                reporting.executed_at.strftime("%d/%m/%Y")
                if reporting.executed_at
                else "-"
            )

            worksheet[cls._PIC_OAE_NUM_CELL] = cls._EXPORT_CLASS.get_padded_oae_num(
                reporting, "-"
            )
            worksheet[cls._COMPANY_CELL] = cls._get_company_display_name(
                reporting.company.name
            )
            worksheet[cls._PIC_EXECTUTED_AT_CELL] = executed_at

            for field, cell in cls._SIMPLE_PIC_FORM_DATA_FIELDS.items():
                worksheet[cell] = new_get_form_data(reporting, field, default="-")

        return pic_sheets

    @classmethod
    def _fill_text_sheet(cls, worksheet: Worksheet, reporting: Reporting) -> None:
        worksheet.title = cls._get_worksheet_title(reporting)
        executed_at = (
            reporting.executed_at.strftime("%d/%m/%Y") if reporting.executed_at else "-"
        )
        direction = (
            get_custom_option(reporting, "direction") if reporting.direction else "-"
        )

        worksheet[cls._OAE_NUM_CELL] = cls._EXPORT_CLASS.get_padded_oae_num(
            reporting, "-"
        )
        worksheet[cls._COMPANY_CELL] = cls._get_company_display_name(
            reporting.company.name
        )
        worksheet[cls._EXECTUTED_AT_CELL] = executed_at
        worksheet[cls._ROAD_NAME_CELL] = get_artesp_full_road_name(
            reporting, reporting.company
        )
        worksheet[cls._DIRECTION_CELL] = direction
        worksheet[cls._KM_CELL] = format_km(reporting.km, 3)

        for field, cell in cls._SIMPLE_FORM_DATA_FIELDS.items():
            value: str = new_get_form_data(reporting, field)
            value_str = "-"
            try:
                if value is not None:
                    value_str = str(value).strip()
                    if value_str == "":
                        value_str = "-"
            except Exception:
                value_str = "-"
            worksheet[cell] = value_str

        for field, cell in cls._DATE_FORM_DATA_FIELDS.items():
            date_str = new_get_form_data(reporting, field, default=None)
            if date_str is None:
                worksheet[cell] = "-"
            else:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                month = cls._MONTH[date.month - 1]
                year = str(date.year)[-2:]
                worksheet[cell] = f"{month}/{year}"

        therapy_desc = cls._get_therapy_descriptions(reporting)
        worksheet[cls._THERAPY_DESC_CELL] = therapy_desc

    def _fill_sheets(self, workbook: Workbook, reporting: Reporting, pic_temp_dir: str):
        cls = type(self)
        text_sheet = workbook.worksheets[0]
        cls._fill_text_sheet(text_sheet, reporting)
        pic_sheets = self._fill_picture_sheets(pic_temp_dir, workbook, reporting)

        cls._insert_logos(
            self.s3, pic_temp_dir, self.__sheet_target, workbook, reporting, pic_sheets
        )

        set_zoom(workbook, 50, "pageBreakPreview")
        set_active_cell(workbook, "A1")
        workbook.active = text_sheet

    def _create_workbook_file(self, reporting: Reporting) -> str:
        cls = type(self)
        pic_temp_dir = tempfile.mkdtemp()
        workbook: Workbook = load_workbook(cls._TEMPLATE_FILE)
        self._fill_sheets(workbook, reporting, pic_temp_dir)

        clean_road_name = clean_latin_string(
            reporting.road_name.replace(".", "").replace("/", "")
        )
        folder = f"{clean_road_name} - {cls._EXPORT_NAME}"
        file_name = cls._EXPORT_CLASS.get_file_code(reporting)

        file_name = clean_latin_string(file_name.replace(".", "").replace("/", ""))
        file_path = f"{self.__temp_dir}/{folder}/{file_name}.xlsx"
        file_count = 1
        while isfile(file_path):
            file_path = f"{self.__temp_dir}/{folder}/{file_name} ({file_count}).xlsx"
            file_count += 1

        Path(f"{self.__temp_dir}/{folder}").mkdir(parents=True, exist_ok=True)
        workbook.save(file_path)

        shutil.rmtree(pic_temp_dir, ignore_errors=True)

        return file_path

    def execute(self) -> List[str]:
        cls = type(self)
        workbook_files: List[str] = []

        reportings = cls.__get_reportings(self.uuids)
        for r in reportings:
            workbook_files.append(self._create_workbook_file(r))

        return workbook_files


class RoutineARTESP(CCRReport):
    _XLSX_HANDLER: type = XlsxHandler
    _EXPORT_NAME = ""
    _FILE_NAME_CODE = "R"

    DIRECTION_ACRONYM = {
        "norte": "N",
        "sul": "S",
        "leste": "L",
        "oeste": "O",
        "norte/sul": "NS",
        "leste/oeste": "LO",
        "crescente": "C",
        "decrescente": "D",
        "transversal": "T",
        "externa": "E",
        "interna": "I",
        "interna/externa": "IE",
        "externa/interna": "IE",
        "marginal oeste": "MO",
        "via marginal": "VM",
        "via lateral": "VL",
        "marginal norte": "MN",
        "marginal sul": "MS",
        "marginal leste": "ML",
        "marginal interna": "MI",
        "marginal externa": "ME",
        "lateral norte": "LN",
        "lateral sul": "LS",
    }

    def __init__(
        self,
        uuids: List[str] = None,
        report_format: ReportFormat = ReportFormat.XLSX,
    ) -> None:
        super().__init__(uuids, report_format)

    @classmethod
    def __get_road_names(cls, uuids: List[str]) -> List[str]:
        return list(
            Reporting.objects.filter(uuid__in=uuids)
            .only("uuid", "road_name")
            .order_by("road_name")
            .distinct("road_name")
            .values_list("road_name", flat=True)
        )

    @classmethod
    def get_padded_number_field(
        cls, reporting: Reporting, api_name: str, padding: int, default: str = ""
    ) -> str:
        value = new_get_form_data(reporting, api_name, default=None)
        value_str = default
        try:
            if value is not None:
                value_str = str(int(value))
                value_str = value_str.zfill(padding)
        except Exception:
            value_str = default
        return value_str

    @classmethod
    def get_padded_oae_num(cls, reporting: Reporting, default: str = "") -> str:
        return cls.get_padded_number_field(reporting, "oaeNumeroCodigoObra", 3, default)

    @classmethod
    def get_padded_inspection_campaing_year(
        cls, reporting: Reporting, default: str = ""
    ) -> str:
        return cls.get_padded_number_field(
            reporting, "inspectionCampaignYear", 4, default
        )

    @classmethod
    def get_file_code(cls, reporting: Reporting) -> str:
        oae_num = cls.get_padded_oae_num(reporting)

        year = cls.get_padded_inspection_campaing_year(reporting)
        road_km = ""
        nums = re.findall(r"\d{3}", reporting.road_name)
        if len(nums) > 0:
            road_km = nums[0]
        km = format_km(reporting.km, 3, "")
        direction = get_custom_option(reporting, "direction")
        dir_acronym = cls.DIRECTION_ACRONYM.get(direction.lower(), "")
        return f"{oae_num}_{cls._FILE_NAME_CODE}{year}{road_km}k{km}{dir_acronym}"

    def get_file_name(self) -> str:
        cls = type(self)
        file_name: str = ""
        extension = ""

        if len(self.uuids) > 1:
            extension = "zip"
            road_names = cls.__get_road_names(self.uuids)
            file_name = f"{'_'.join(road_names)} - {self._EXPORT_NAME}"
        else:
            reporting = (
                Reporting.objects.filter(uuid=self.uuids[0])
                .only("uuid", "km", "form_data", "direction", "company", "firm")
                .select_related("company", "firm")
            )[0]
            file_name = cls.get_file_code(reporting)
            extension = "xlsx" if self.report_format() == ReportFormat.XLSX else "pdf"
        file_name = clean_latin_string(file_name.replace(".", "").replace("/", ""))
        file_name = f"{file_name}.{extension}"

        return file_name

    def export(self):
        s3 = get_s3()
        with self._XLSX_HANDLER(
            uuids=self.uuids,
            s3=s3,
            sheet_target=self.sheet_target(),
            report_format=self.report_format(),
        ) as xlsx_handler:
            files = xlsx_handler.execute()

            if self.report_format() == ReportFormat.PDF:
                files = convert_files_to_pdf(files)

            result_file = ""
            if len(files) == 1:
                result_file = files[0]
            elif len(files) > 1:
                result_file = f"/tmp/{self.file_name}"
                with ZipFile(result_file, "w") as zipObj:
                    for file in files:
                        zipObj.write(file, "/".join(file.split("/")[-2:]))
            upload_file(s3, result_file, self.object_name)

        return True
