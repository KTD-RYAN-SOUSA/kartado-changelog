import tempfile
from datetime import timedelta
from typing import Dict, List, Tuple
from zipfile import ZipFile

from openpyxl import load_workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from zappa.asynchronous import task

from apps.reportings.models import Reporting, ReportingInReporting
from helpers.apps.ccr_report_utils.ccr_report import CCRReport
from helpers.apps.ccr_report_utils.export_utils import get_s3, upload_file
from helpers.apps.ccr_report_utils.form_data import new_get_form_data
from helpers.apps.ccr_report_utils.image import (
    ReportFormat,
    ResizeMethod,
    SheetTarget,
    get_logo_file,
    insert_picture,
    insert_picture_2,
    result_photos,
)
from helpers.apps.ccr_report_utils.pdf import convert_files_to_pdf
from helpers.apps.ccr_report_utils.reporting_utils import get_custom_option
from helpers.strings import clean_latin_string, format_km


class XlsxHandlerReportOACAnnexFour(object):
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
        self.filename = None
        self.list_uuids = list_uuids
        self.wb: Workbook = None
        self.uuid = self.list_uuids[0]
        self._worksheet: Worksheet = None
        self.reportings = Reporting.objects.filter(uuid=self.uuid).prefetch_related(
            "company"
        )
        first_reporting = self.reportings.first()
        self.form = first_reporting.occurrence_type
        self.company = first_reporting.company
        self.logo_company = get_logo_file(self.s3, tempfile.mkdtemp(), first_reporting)
        self.static_fields = {
            "id_ccr_antt": "A",
            "road_name": "B",
            "initial_km": "C",
            "end_km": "D",
            "direction": "E",
            "type_manhole": "F",
            "reference_point": "G",
            "previous_conservation_state": "H",
            "previous_photo": "I",
            "conservation_state": "J",
            "current_photo": "K",
            "corrective_actions": "L",
        }
        self.border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        self.__init_wb()

    def __insert_new_rows(self, row: int):
        chars = [chr(ord("A") + i) for i in range(12)]

        for char in chars:
            self._worksheet[f"{char}{row}"].border = self.border
            self._worksheet.row_dimensions[row].height = 100
            self._worksheet.row_dimensions[row].length = 100

    def create_dict(self, reporting: Reporting):
        list_dicts = []
        linked_reports = ReportingInReporting.objects.filter(parent=reporting.uuid)
        if linked_reports:
            for data in linked_reports:
                result_dict = {}
                report = data.child
                name_reporting_relation = data.reporting_relation.name
                if name_reporting_relation in ["Jusante", "Montante"]:

                    result_dict["id_ccr_antt"] = new_get_form_data(
                        reporting, "idCcrAntt"
                    )
                    result_dict["initial_km"] = format_km(reporting, "km", 3)
                    result_dict["end_km"] = format_km(reporting, "end_km", 3)
                    result_dict["road_name"] = reporting.road_name
                    result_dict["found_at"] = reporting.found_at

                    result_dict["direction"] = get_custom_option(report, "direction")
                    result_dict["conservation_state"] = new_get_form_data(
                        report, "holeClassification"
                    )
                    result_dict["type_manhole"] = new_get_form_data(
                        report, "entryStruc"
                    )
                    result_dict["reference_point"] = name_reporting_relation

                    photos = report.form_data.get("photos_mon")
                    if photos:
                        photo = self.__get_photos(photos)
                        result_dict["current_photo"] = photo
                    previous_result = (
                        XlsxHandlerReportOACAnnexFour.__get_previous_relation_reporting(
                            report, name_reporting_relation, data
                        )
                    )
                    if previous_result:
                        result_dict["previous_conservation_state"] = new_get_form_data(
                            previous_result,
                            "holeClassification",
                        )
                        result_dict[
                            "corrective_actions"
                        ] = self.__set_corrective_actions(
                            previous_result,
                            str(result_dict["conservation_state"]).upper(),
                            str(result_dict["previous_conservation_state"]).upper(),
                        )
                        previous_photo = previous_result.form_data.get("photos_mon", "")
                        result_dict["previous_photo"] = (
                            self.__get_photos(previous_photo) if previous_photo else ""
                        )
                list_dicts.append(result_dict)
        return list_dicts

    def __set_corrective_actions(
        self, reporting, conservation_state, previous_conservation_state
    ):
        state = f"{previous_conservation_state}/{conservation_state}"

        if state in ["REGULAR/BOM", "PRECÁRIO/BOM"]:
            state_dict = {
                "LIMPEZA": new_get_form_data(reporting, "cleaningmon"),
                "ROÇADA": new_get_form_data(reporting, "rocadaMon"),
                "EROSÃO": new_get_form_data(reporting, "erosion"),
                "TUBULAÇÃO DANIFICADA": new_get_form_data(reporting, "tubeDamagemon"),
                "TESTA/ALA DANIFICADA": new_get_form_data(
                    reporting, "foreheadDamagemon"
                ),
                "FISSURAS/TRINCAS": new_get_form_data(reporting, "broken"),
                "CAIXA DANIFICADA": new_get_form_data(reporting, "boxDamagemon"),
                "TAMPA DANIFICADA/INEXISTENTE": new_get_form_data(
                    reporting, "coverDamagemon"
                ),
                "AFOGADO": new_get_form_data(reporting, "desobstrucaomon"),
                "ASSOREADO": new_get_form_data(reporting, "desassoreamentomon"),
            }
            true_keys = [key for key, value in state_dict.items() if value]

            concatenated_keys = ", ".join(true_keys)
            return concatenated_keys

        elif state in [
            "BOM/REGULAR",
            "REGULAR/REGULAR",
            "BOM/PRECÁRIO",
            "REGULAR/PRECÁRIO",
        ]:
            return "Cronograma Conforme Anexo VI"

    @classmethod
    def __get_previous_relation_reporting(
        cls, reporting, name_reporting_relation, data
    ):
        previous_date = reporting.created_at - timedelta(days=365)
        previous_reporting = ReportingInReporting.objects.filter(
            child__executed_at__gte=previous_date,
            child__executed_at__lte=reporting.found_at,
            reporting_relation__name=name_reporting_relation,
            child__parent=reporting.parent,
        ).order_by("-child__found_at")
        if previous_reporting:
            return previous_reporting[0].child

    def __get_photos(self, photos):
        photos_result = ""
        for photo in photos:
            try:
                for detail_photo_mon in photo["detail_photos_mon"]:
                    try:
                        return result_photos(
                            s3=self.s3,
                            temp_file=tempfile.mkdtemp(),
                            photo_id=detail_photo_mon,
                            width=337,
                            height=242,
                            enable_include_dnit=False,
                            enable_is_shared_antt=True,
                        )[0]
                    except (IndexError, KeyError):
                        photos_result = ""
            except (IndexError, KeyError):
                photos_result = ""

        return photos_result

    def __resize_and_insert_logo(self, logo_company):
        try:
            img = Image(logo_company)
            insert_picture_2(
                self._worksheet,
                "L1",
                img,
                self.__sheet_target,
                border_width=(1, 1, 3, 1),
                resize_method=ResizeMethod.ProportionalRight,
            )
        except Exception:
            pass

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
        wrap_text: bool = False,
    ) -> None:

        cell.alignment = Alignment(
            horizontal=horizontal, vertical=vertical, wrap_text=wrap_text
        )
        cell.font = Font(name=name, sz=size, bold=bold)

    def execute(self):
        query_set = Reporting.objects.filter(
            occurrence_type=self.form, uuid__in=self.list_uuids
        ).prefetch_related("occurrence_type", "firm", "firm__subcompany")
        data = []
        for reporting in query_set:
            data.extend(self.create_dict(reporting))

        reportings_data: Dict[Tuple[str, int], List[dict]] = {}
        for item in data:
            if not item:
                continue
            road_name = item.get("road_name", None)
            found_at = item.get("found_at", None)
            if road_name is None or found_at is None:
                continue
            road_year = (road_name, found_at.year)
            if road_year in reportings_data:
                reportings_data[road_year].append(item)
            else:
                reportings_data[road_year] = [item]

        files_year: Dict[int, List[Dict]] = {}
        for (road_name, year), data in reportings_data.items():
            file = self.fill_sheet(road_name, year, data)
            if year in files_year:
                files_year[year].append(file)
            else:
                files_year[year] = [file]

        if self.__report_format == ReportFormat.PDF:
            pdf_files_year = {}
            for year, files in files_year.items():
                pdf_files_year[year] = convert_files_to_pdf(files)
            files_year = pdf_files_year

        zip_files = []
        for year, files in files_year.items():
            zip_path = f"/tmp/Anexo IV - Comparativo OAC - Ano {year}.zip"
            with ZipFile(zip_path, "w") as zipObj:
                for file in files:
                    zipObj.write(file, file.split("/")[-1])
            zip_files.append(zip_path)

        return zip_files

    def fill_sheet(self, road_name, year, data: List[dict]):
        row = 5
        for reporting_data in data:
            for internal_key, value in reporting_data.items():
                if internal_key in ["current_photo"] and value:
                    cell = f"{self.static_fields[internal_key]}{row}"
                    try:
                        insert_picture(
                            self._worksheet,
                            cell,
                            Image(value),
                            self.__sheet_target,
                        )
                    except Exception as e:
                        print(e)
                elif internal_key in ["previous_photo"] and value:
                    cell = f"{self.static_fields[internal_key]}{row}"
                    try:
                        insert_picture(
                            self._worksheet,
                            cell,
                            Image(value),
                            self.__sheet_target,
                        )
                    except Exception as e:
                        print(e)

                else:
                    if internal_key not in ["found_at"]:
                        self.__insert_new_rows(row=row)
                        key_value = f"{self.static_fields[internal_key]}{row}"
                        try:
                            self._worksheet[key_value] = value
                        except Exception as e:
                            print(e)

                        wrap_text = False
                        if internal_key == "corrective_actions":
                            wrap_text = True
                        XlsxHandlerReportOACAnnexFour.__format_fonts(
                            cell=self._worksheet[key_value],
                            size=10,
                            wrap_text=wrap_text,
                        )
            row += 1

        self._worksheet[
            "A1"
        ] = f"Anexo IV - Quadro Comparativo - Obra de arte corrente - {road_name}"
        XlsxHandlerReportOACAnnexFour.__format_fonts(
            cell=self._worksheet["A1"], size=12, bold=True
        )
        self._worksheet.title = road_name

        file_name = f"Anexo IV - Comparativo OAC - {road_name}{year}"
        file_name = clean_latin_string(file_name.replace(".", "").replace("/", ""))
        file_path = f"/tmp/{file_name}.xlsx"
        self.wb.save(file_path)
        self.__init_wb()

        return file_path

    def __init_wb(self):
        self.wb = load_workbook("./fixtures/reports/crr_drainage_annex_four.xlsx")
        self._worksheet = self.wb.active
        if self.logo_company:
            self.__resize_and_insert_logo(self.logo_company)


class CrrSurfaceDrainageAnnexFour(CCRReport):
    def __init__(
        self, uuids: List[str] = None, report_format: ReportFormat = ReportFormat.XLSX
    ) -> None:
        super().__init__(uuids, report_format)

    @classmethod
    def get_file_name(cls):
        file_name = "Anexo IV - Comparativo OAC"

        file_name = clean_latin_string(file_name.replace(".", "").replace("/", ""))
        file_name = f"{file_name}.zip"

        return file_name

    def export(self):
        s3 = get_s3()
        files = XlsxHandlerReportOACAnnexFour(
            list_uuids=self.uuids,
            s3=s3,
            sheet_target=self.sheet_target(),
            report_format=self.report_format(),
        ).execute()
        files = list(set(files))
        result_file = f"/tmp/{self.file_name}"
        with ZipFile(result_file, "w") as zipObj:
            for file in files:
                zipObj.write(file, file.split("/")[-1])

        upload_file(s3, result_file, self.object_name)
        return True


@task
def ccr_report_oac_annex_four_async_handler(reporter_dict: dict):
    reporter = CrrSurfaceDrainageAnnexFour.from_dict(reporter_dict)
    reporter.export()
