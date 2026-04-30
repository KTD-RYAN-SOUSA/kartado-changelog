import re
from typing import Dict, List

from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from apps.reportings.models import Reporting, ReportingFile
from helpers.apps.ccr_report_routine_artesp import RoutineARTESP
from helpers.apps.ccr_report_routine_artesp import XlsxHandler as RoutineXlsxHandler
from helpers.apps.ccr_report_utils.form_data import (
    get_form_array_iterator,
    new_get_form_data,
)
from helpers.apps.ccr_report_utils.image import (
    ResizeMethod,
    get_image,
    insert_picture_2,
)
from helpers.apps.ccr_report_utils.workbook_utils import set_active_cell, set_zoom


class XlsxHandler(RoutineXlsxHandler):
    _FILE_NAME_CODE = "I"

    _PICTURE_CODE_PATTERN = re.compile(
        r"I(\d{7})k(\d{6})F(\d{3})([A-Z]{1,2})"
    )  # Regex to check picture code

    _CROQUI_TEMPLATE_TITLE = "CROQUI 1"  # Title of picture sheet template
    _PICTURE_TEMPLATE_TITLE = "FOTO 1"  # Title of picture sheet template

    _SIMPLE_CROQUI_FORM_DATA_FIELDS: Dict[
        str, str
    ] = {}  # Dict of form field api name to cell. EX: "oaeNumeroCodigoObra": "Q1"

    _GEOELEMENT_FIELDS: Dict[
        str, str
    ] = {}  # Dict of form field api name to cell. EX: "oaeNumeroCodigoObra": "Q1"

    _TWO_DECIMAL_PLACES: Dict[
        str, str
    ] = {}  # Dict of form field api name to cell. EX: "oaeNumeroCodigoObra": "Q1"

    _CROQUI_PICTURE_RANGE = "A5:N53"  # Cell or cell range like string. Ex "A1"; "A1:B2"

    @classmethod
    def _get_croqui_reporting_files(cls, reporting: Reporting) -> List[ReportingFile]:
        rfs: Dict[str, ReportingFile] = {
            str(rf.uuid): rf for rf in reporting.reporting_files.all()
        }
        croqui_uuids: List[str] = []

        it = get_form_array_iterator(reporting, "croqui")
        try:
            while True:
                report_pictures = it.get("croquiImage")
                if isinstance(report_pictures, list):
                    croqui_uuids.extend(report_pictures)
                it.inc()
        except Exception as e:
            print(e)

        croqui_rfs = [rfs[uuid] for uuid in croqui_uuids if uuid in rfs]
        return sorted(croqui_rfs, key=lambda rf: (rf.datetime, rf.uploaded_at))

    def _fill_croqui_sheets(
        self, pic_temp_dir: str, workbook: Workbook, reporting: Reporting
    ) -> None:
        cls = type(self)
        reporting_files = cls._get_croqui_reporting_files(reporting)

        template_sheet = workbook[cls._CROQUI_TEMPLATE_TITLE]
        worksheet: Worksheet = None
        pic_count = 0

        croqui_sheets: List[Worksheet] = [template_sheet]

        for rf in reporting_files:
            worksheet = workbook.copy_worksheet(template_sheet)
            try:
                image = get_image(
                    self.s3,
                    pic_temp_dir,
                    "temp-" + str(rf.uuid),
                    rf,
                )
                insert_picture_2(
                    worksheet,
                    cls._CROQUI_PICTURE_RANGE,
                    image,
                    self.__sheet_target,
                    border_width=(2, 2, 2, 2),
                    resize_method=ResizeMethod.ProportionalCentered,
                )
                pic_count = pic_count + 1
                if pic_count == 10:
                    break
                croqui_sheets.append(worksheet)
            except Exception:
                workbook.remove(worksheet)

        if pic_count > 0:
            croqui_sheets.remove(template_sheet)
            workbook.remove(template_sheet)

        sheet_count = 0
        for worksheet in croqui_sheets:
            sheet_count += 1
            worksheet.title = f"CROQUI {sheet_count}"
            executed_at = (
                reporting.executed_at.strftime("%d/%m/%Y")
                if reporting.executed_at
                else "-"
            )

            worksheet[cls._OAE_NUM_CELL] = cls._EXPORT_CLASS.get_padded_oae_num(
                reporting, "-"
            )
            worksheet[cls._COMPANY_CELL] = cls._get_company_display_name(
                reporting.company.name
            )
            worksheet[cls._EXECTUTED_AT_CELL] = executed_at

            for field, cell in cls._SIMPLE_CROQUI_FORM_DATA_FIELDS.items():
                worksheet[cell] = new_get_form_data(reporting, field, default="-")

    @classmethod
    def _fill_geo_elements(
        cls, text_worksheet: Worksheet, reporting: Reporting
    ) -> None:
        for field, cell in cls._GEOELEMENT_FIELDS.items():
            value = new_get_form_data(reporting, field, default="")
            value_str = "-"
            try:
                if value is not None:
                    value_str = str(int(value))
                    value_str = value_str.zfill(2)
            except Exception:
                value_str = "-"
            text_worksheet[cell] = value_str

    @classmethod
    def _fill_decimal_places(
        cls, text_worksheet: Worksheet, reporting: Reporting, decimal_places: int
    ) -> None:
        for field, cell in cls._TWO_DECIMAL_PLACES.items():
            value = new_get_form_data(reporting, field, default="")
            value_str = "-"
            try:
                if value is not None:
                    value_str = f"{float(value):.2f}".replace(".", ",")
            except Exception:
                value_str = "-"
            text_worksheet[cell] = value_str

    @classmethod
    def _sort_worksheets(cls, workbook: Workbook, pic_sheets: List[Worksheet]) -> None:
        for worksheet in pic_sheets:
            workbook.move_sheet(worksheet, len(workbook.worksheets))

    def _fill_sheets(self, workbook: Workbook, reporting: Reporting, pic_temp_dir: str):
        cls = type(self)
        text_sheet = workbook.worksheets[0]
        cls._fill_text_sheet(text_sheet, reporting)
        cls._fill_geo_elements(text_sheet, reporting)
        cls._fill_decimal_places(text_sheet, reporting, 2)
        self._fill_croqui_sheets(pic_temp_dir, workbook, reporting)
        pic_sheets = self._fill_picture_sheets(pic_temp_dir, workbook, reporting)

        cls._insert_logos(
            self.s3, pic_temp_dir, self.__sheet_target, workbook, reporting, pic_sheets
        )

        cls._sort_worksheets(workbook, pic_sheets)

        set_zoom(workbook, 50, "pageBreakPreview")
        set_active_cell(workbook, "A1")
        workbook.active = text_sheet


class InitialARTESP(RoutineARTESP):
    _XLSX_HANDLER: type = XlsxHandler
    _EXPORT_NAME = ""
    _FILE_NAME_CODE = "I"
