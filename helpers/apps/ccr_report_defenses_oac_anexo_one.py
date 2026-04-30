import tempfile
from typing import Dict, List, Tuple
from zipfile import ZipFile

from openpyxl import load_workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from zappa.asynchronous import task

from apps.reportings.models import Reporting
from helpers.apps.ccr_report_utils.ccr_report import CCRReport
from helpers.apps.ccr_report_utils.export_utils import get_s3, upload_file
from helpers.apps.ccr_report_utils.form_data import new_get_form_data
from helpers.apps.ccr_report_utils.image import (
    ReportFormat,
    ResizeMethod,
    SheetTarget,
    get_logo_file,
    get_provider_logo_file,
    insert_logo_and_provider_logo,
    insert_picture,
    result_photos,
)
from helpers.apps.ccr_report_utils.pdf import ThreadExecutor, synchronized_request_pdf
from helpers.apps.ccr_report_utils.reporting_utils import get_custom_option
from helpers.strings import clean_latin_string, format_km


class XlsxHandlerReportOACAnnexOne(object):
    def __init__(
        self,
        s3,
        list_uuids: List[str],
        sheet_target: SheetTarget = SheetTarget.DesktopExcel,
        report_format: ReportFormat = ReportFormat.XLSX,
    ) -> None:
        self.s3 = s3
        self.__sheet_target = sheet_target
        self.__report_format = report_format
        self.photo_panorama = None
        self.photo_detail = None
        self.filename = None
        self.wb: Workbook = None
        self.list_uuids = list_uuids
        self.uuid = self.list_uuids[0]
        self._worksheet: Worksheet = None
        self.__init_wb()
        self.reportings = Reporting.objects.filter(uuid=self.uuid).prefetch_related(
            "company"
        )

        self.logo_config: dict = dict(
            range_string="H1:I3",
            resize_method=ResizeMethod.ProportionalRight,
        )

        self.provider_logo_config: dict = dict(
            range_string="B1:C3",
            resize_method=ResizeMethod.ProportionalLeft,
        )
        self.logo_config["path_image"] = get_logo_file(
            s3=self.s3,
            temp_prefix="/tmp/",
            reporting=self.reportings[0],
        )
        self.provider_logo_config["path_image"] = get_provider_logo_file(
            s3=self.s3,
            temp_prefix="/tmp/",
            reporting=self.reportings[0],
        )
        first_reporting = self.reportings.first()
        self.form = first_reporting.occurrence_type
        self.company = first_reporting.company
        self.static_fields = {
            "id_ccr_annt": "C6",
            "extension": "C7",
            "length": "C8",
            "coord_initial_x": "C9",
            "coord_initial_y": "C10",
            "detail_element": "C11",
            "material": "C12",
            "initial_km": "H6",
            "end_km": "H7",
            "height": "H8",
            "coord_final_x": "H9",
            "coord_final_y": "H10",
            "conservation_state": "H11",
            "environment": "H12",
            "monitoring_date": "I4",
            "status_good": "E14",
            "repair": {
                "state": "E15",
                "extension": "F15",
            },
            "cleaning": {
                "state": "E16",
                "extension": "F16",
            },
            "implant": {
                "state": "E17",
                "extension": "F17",
            },
            "photo_panorama": "B20:E28",
            "photo_detail": "F20:I28",
        }

        self.border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        self.dict_filtered_roads = {
            "BR-116 SP": [],
            "BR-101 SP": [],
            "BR-116 RJ": [],
            "BR-101 RJ": [],
        }

    def create_dict(self, reporting):
        self.photo_panorama = None
        self.photo_detail = None

        result_id_ccr_annt = new_get_form_data(reporting, "idCcrAntt")

        result_extension = new_get_form_data(reporting, "length")

        result_length = new_get_form_data(reporting, "largura")

        result_height = new_get_form_data(reporting, "altura")
        result_coord_initial_x = new_get_form_data(reporting, "latidudeini")

        result_coord_initial_y = new_get_form_data(reporting, "longitudeini")

        result_detail_element = new_get_form_data(reporting, "detalheelemento")
        result_coord_fim_x = new_get_form_data(reporting, "latitudefim")

        result_coord_fim_y = new_get_form_data(reporting, "longitudefim")

        result_environment = new_get_form_data(reporting, "ambiente")

        result_material = new_get_form_data(reporting, "material")

        photos = reporting.form_data.get("fotos_relatorio")
        if photos:
            try:
                photo_report = reporting.form_data.get("fotos_relatorio", "")
                self.photo_panorama = result_photos(
                    s3=self.s3,
                    temp_file=tempfile.mkdtemp(),
                    photo_id=photo_report[0]["fotos_panoramicas"][0],
                    width=170,
                    height=100,
                    enable_is_shared_antt=True,
                    enable_include_dnit=False,
                )[0]
            except Exception:
                self.photo_panorama = ""

            try:
                photo_detail = reporting.form_data.get("fotos_relatorio", "")
                self.photo_detail = result_photos(
                    s3=self.s3,
                    temp_file=tempfile.mkdtemp(),
                    photo_id=photo_detail[0]["fotos_detalhe"][0],
                    width=170,
                    height=100,
                    enable_is_shared_antt=True,
                    enable_include_dnit=False,
                )[0]
            except Exception:
                self.photo_detail = ""

        result_conservation_state = new_get_form_data(
            reporting,
            "generalConservationState",
        )
        status_good = "X" if result_conservation_state == "Bom" else ""

        result_repair = new_get_form_data(reporting, "reparar")
        extension_repair = (
            reporting.form_data.get("extensaoreparo", "") if result_repair else ""
        )

        repair = {"state": "X" if result_repair else "", "extension": extension_repair}

        result_cleaning = new_get_form_data(reporting, "limpeza")
        extension_cleaning = (
            reporting.form_data.get("extensaolimpeza", "") if result_repair else ""
        )
        cleaning = {
            "state": "X" if result_cleaning else "",
            "extension": extension_cleaning,
        }

        result_implant = new_get_form_data(reporting, "implantar")
        extension_implant = (
            reporting.form_data.get("extensaoimplantacao", "") if result_repair else ""
        )

        implant = {
            "state": "X" if result_implant else "",
            "extension": extension_implant,
        }

        monitoring_date = (
            reporting.executed_at.strftime("%d/%m/%Y") if reporting.executed_at else ""
        )
        direction = get_custom_option(reporting, "direction")
        format_filename = {
            "id_ccr_annt": result_id_ccr_annt,
            "road_name": reporting.road_name,
            "direction": direction,
        }
        found_at = reporting.found_at

        data = {
            "id_ccr_annt": result_id_ccr_annt,
            "extension": result_extension,
            "length": result_length,
            "conservation_state": result_conservation_state,
            "coord_initial_x": result_coord_initial_x,
            "coord_initial_y": result_coord_initial_y,
            "detail_element": result_detail_element,
            "material": result_material,
            "initial_km": format_km(reporting, "km", 3),
            "end_km": format_km(reporting, "end_km", 3),
            "height": result_height,
            "coord_final_x": result_coord_fim_x,
            "coord_final_y": result_coord_fim_y,
            "environment": result_environment,
            "monitoring_date": monitoring_date,
            "status_good": status_good,
            "repair": repair,
            "cleaning": cleaning,
            "implant": implant,
            "photo_panorama": (
                self.photo_panorama if self.photo_panorama else self.photo_panorama
            ),
            "photo_detail": (
                self.photo_detail if self.photo_detail else self.photo_detail
            ),
            "format_filename": format_filename,
            "road_name": reporting.road_name,
            "found_at": found_at,
        }

        for k, v in data.items():
            if v is None:
                data[k] = ""
        return data

    def fill_sheets(self, road, year, reportings_data):
        convert_executor = None
        if self.__report_format == ReportFormat.PDF:
            convert_executor = ThreadExecutor(50)
        files_list = []
        for reporting_data in reportings_data:
            filename = None
            for internal_key, value in reporting_data.items():
                try:
                    if internal_key in ["repair", "cleaning", "implant"]:
                        for _key, _value in value.items():
                            key_value = self.static_fields[internal_key][_key]
                            self.__insert_status_values(
                                cell=key_value, value=_value, key=_key
                            )

                    elif internal_key in ["photo_panorama"] and value:
                        cell = f"{self.static_fields[internal_key]}"
                        insert_picture(
                            self._worksheet,
                            cell,
                            Image(value),
                            target=self.__sheet_target,
                            border_width=1,
                        )

                    elif internal_key in ["photo_detail"] and value:
                        cell = f"{self.static_fields[internal_key]}"
                        insert_picture(
                            self._worksheet,
                            cell,
                            Image(value),
                            target=self.__sheet_target,
                            border_width=1,
                        )
                    elif internal_key in ["format_filename"]:
                        filename = self.__create_filename_and_header(value, files_list)

                    else:
                        if internal_key not in ["road_name", "found_at"]:
                            key_value = self.static_fields[internal_key]
                            self._worksheet[key_value] = value
                except Exception as e:
                    print(e)

            try:
                insert_logo_and_provider_logo(
                    worksheet=self._worksheet,
                    target=self.__sheet_target,
                    logo_company=self.logo_config,
                    provider_logo=self.provider_logo_config,
                )

                if filename is not None:
                    self.wb.save(filename)
                    files_list.append(filename)
                    if self.__report_format == ReportFormat.PDF:
                        convert_executor.submit(synchronized_request_pdf, filename)
                self.__init_wb()
            except Exception as e:
                print(e)

        if self.__report_format == ReportFormat.PDF:
            files_list = list(set(convert_executor.get()))
            files_list.sort()

        temp_dir = tempfile.mkdtemp()
        path_file = f"{temp_dir}/{road}{year}.zip"

        with ZipFile(path_file, "w") as zipObj:
            for file in files_list:
                try:
                    zipObj.write(file, file.split("/")[-1])
                except Exception as e:
                    print(e)

        return path_file

    def __init_wb(self):
        self.wb = load_workbook("./fixtures/reports/crr_drainage_annex_one.xlsx")
        self._worksheet = self.wb.active

    def __create_filename_and_header(self, value, files_list):
        self._worksheet["B5"].value = f"Drenagem Superficial Rod.{value['road_name']}"
        XlsxHandlerReportOACAnnexOne.__format_fonts(
            cell=self._worksheet["B5"], bold=True, size=12
        )

        id_antt = (value["id_ccr_annt"] if value["id_ccr_annt"] else "").replace(
            "/", "-"
        )

        file_name = "/tmp/{}.xlsx".format(id_antt)
        i = 1
        while file_name in files_list:
            file_name = f"/tmp/{id_antt}({i}).xlsx"
            i += 1
        return file_name

    def __insert_status_values(self, cell, value, key):
        if value and key == "state":
            self._worksheet[cell] = "X"
            XlsxHandlerReportOACAnnexOne.__format_fonts(
                cell=self._worksheet[cell], size=10, horizontal="center"
            )
        else:
            self._worksheet[cell] = value

    @classmethod
    def __format_fonts(
        cls,
        *,
        cell,
        name="Cabrini",
        size: int,
        bold=False,
        horizontal="center",
        vertical="center",
    ) -> None:

        cell.alignment = Alignment(horizontal=horizontal, vertical=vertical)
        cell.font = Font(name=name, sz=size, bold=bold)

    def execute(self):
        query_set = Reporting.objects.filter(
            occurrence_type=self.form, uuid__in=self.list_uuids
        ).prefetch_related("occurrence_type", "company", "firm", "firm__subcompany")

        reportings_data_list = []
        for reporting in query_set:
            try:
                r_data = self.create_dict(reporting=reporting)
                reportings_data_list.append(r_data)
            except Exception as e:
                print(e)

        reportings_data: Dict[Tuple[str, int], List[dict]] = {}
        for item in reportings_data_list:
            if not item:
                continue
            road_name = item.get("road_name")
            found_at = item.get("found_at")
            if road_name is None or found_at is None:
                continue
            road_year = (road_name, found_at.year)
            if road_year in reportings_data:
                reportings_data[road_year].append(item)
            else:
                reportings_data[road_year] = [item]

        zip_files = []
        for (road, year), data in reportings_data.items():
            zip_file = self.fill_sheets(road, year, data)
            zip_files.append(zip_file)
        return zip_files


class CrrSurfaceDrainageAnnexOne(CCRReport):
    def __init__(
        self, uuids: List[str] = None, report_format: ReportFormat = ReportFormat.XLSX
    ) -> None:
        super().__init__(uuids, report_format)

    @classmethod
    def get_file_name(cls):
        file_name = "Anexo I - Fichas Drenagem Superficial"

        file_name = clean_latin_string(file_name.replace(".", "").replace("/", ""))
        file_name = f"{file_name}.zip"

        return file_name

    def export(self):
        s3 = get_s3()
        files = XlsxHandlerReportOACAnnexOne(
            list_uuids=self.uuids,
            s3=s3,
            sheet_target=self.sheet_target(),
            report_format=self.report_format(),
        ).execute()

        result_file = f"/tmp/{self.file_name}"
        with ZipFile(result_file, "w") as zipObj:
            for file in files:
                zipObj.write(file, file.split("/")[-1])

        upload_file(s3, result_file, self.object_name)
        return True


@task
def ccr_report_oac_annex_one_async_handler(reporter_dict: dict):
    reporter = CrrSurfaceDrainageAnnexOne.from_dict(reporter_dict)
    reporter.export()
