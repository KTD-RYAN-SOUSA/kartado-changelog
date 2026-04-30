from typing import List

from zappa.asynchronous import task

from helpers.apps.ccr_report_routine_artesp import RoutineARTESP
from helpers.apps.ccr_report_routine_artesp import XlsxHandler as RoutineXlsxHandler
from helpers.apps.ccr_report_utils.image import ReportFormat


class XlsxHandler(RoutineXlsxHandler):
    _EXPORT_CLASS = RoutineARTESP

    _EXPORT_NAME = "Rotineira_Passarela"
    _TEMPLATE_FILE = "./fixtures/reports/routine_footbridge.xlsm"
    _LOGO_CELL = "A55:B57"
    _PROVIDER_LOGO_CELL = "M55:N57"
    _SUBCOMPANY_LOGO_CELL = "F55:H57"
    _PICTURE_TEMPLATE_INDEX = 1

    _PICTURE_PROVIDER_LOGO_CELL = "P55:Q57"
    _PICTURE_TEAM_LOGO_CELL = "G55:K57"

    _EXECTUTED_AT_CELL = "N2"
    _COMPANY_CELL = "A2"
    _ROAD_NAME_CELL = "B5"
    _DIRECTION_CELL = "F5"
    _KM_CELL = "F7"

    _SIMPLE_PIC_FORM_DATA_FIELDS = {
        "artespCode": "Q3",
    }
    _PIC_EXECTUTED_AT_CELL = "Q2"

    _SIMPLE_FORM_DATA_FIELDS = {
        "artespCode": "N3",
        "tipoObra": "B7",
        "reparos": "B15",
        "reformas": "B18",
        "reforcos": "B21",
        "tabuleiro": "B26",
        "juntasDeDilatacao": "B31",
        "aparelhosApoio": "B36",
        "apoios": "B41",
        "encontros": "B46",
        "outrosElementos": "B51",
        "tiposAcesso": "I5",
        "piso": "I8",
        "drenagemVisual": "I11",
        "guardaCorposVisual": "I14",
        "telamento": "I17",
        "taludes": "I23",
        "iluminacao": "I25",
        "sinalizacao": "I27",
        "gabaritos": "I29",
        "protecaoPilares": "I31",
        "notes": "H35",
        "estrutural": "I53",
        "funcional": "K53",
        "durabilidade": "M53",
    }

    _DATE_FORM_DATA_FIELDS = {
        "inspecaoInicial": "B11",
        "ultimaInspecaoRot": "D11",
        "inspecaoEspecial": "F11",
    }

    _THERAPY_DESC_CELL = "H41"

    _PICTURE_RANGES = ["B6:G26", "K6:P26", "B30:G50", "K30:P50"]
    _PICTURE_CODE_CELLS = ["B27", "K27", "B51", "K51"]
    _PICTURE_DESCRIPTION_CELLS = ["D27", "M27", "D51", "M51"]


class RoutineFootbridge(RoutineARTESP):
    _XLSX_HANDLER: type = XlsxHandler
    _EXPORT_NAME = "Rotineira_Passarela"

    def __init__(
        self,
        uuids: List[str] = None,
        report_format: ReportFormat = ReportFormat.XLSX,
    ) -> None:
        super().__init__(uuids, report_format)


@task
def ccr_report_routine_footbridge_async_handler(
    reporter_dict: dict,
):
    reporter: RoutineFootbridge = RoutineFootbridge.from_dict(reporter_dict)
    reporter.export()
