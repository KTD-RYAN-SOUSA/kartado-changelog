from typing import List

from zappa.asynchronous import task

from helpers.apps.ccr_report_initial_artesp import InitialARTESP
from helpers.apps.ccr_report_initial_artesp import XlsxHandler as InitialXlsxHandler
from helpers.apps.ccr_report_utils.image import ReportFormat


class XlsxHandler(InitialXlsxHandler):
    _EXPORT_CLASS = InitialARTESP

    _EXPORT_NAME = "Inicial_Túnel"
    _TEMPLATE_FILE = "./fixtures/reports/initial_tunnel.xlsm"
    _LOGO_CELL = "A55:B57"
    _PROVIDER_LOGO_CELL = "M55:N57"
    _SUBCOMPANY_LOGO_CELL = "F55:H57"

    _PICTURE_PROVIDER_LOGO_CELL = "P55:Q57"
    _PICTURE_TEAM_LOGO_CELL = "G55:K57"

    _EXECTUTED_AT_CELL = "N2"
    _COMPANY_CELL = "A2"
    _ROAD_NAME_CELL = "B7"
    _DIRECTION_CELL = "F7"
    _KM_CELL = "F9"

    _SIMPLE_PIC_FORM_DATA_FIELDS = {
        "artespCode": "Q3",
    }

    _SIMPLE_CROQUI_FORM_DATA_FIELDS = {
        "artespCode": "N3",
    }

    _PIC_EXECTUTED_AT_CELL = "Q2"

    _SIMPLE_FORM_DATA_FIELDS = {
        "artespCode": "N3",
        "tipoObra": "B9",
        "obsElementosGeom": "B19",
        "tipoTabuleiro": "B23",
        "tipologiaEstrutural": "E23",
        "abobada": "B30",
        "paredesLaterais": "B35",
        "juntas": "B40",
        "emboques": "B46",
        "outrosElementos": "B51",
        "pavimentoVisual": "I7",
        "acostamentoVisual": "I10",
        "drenagemVisual": "I13",
        "guardaCorposVisual": "I16",
        "barreirasDefensas": "I19",
        "contencao": "I23",
        "iluminacao": "I26",
        "sinalizacao": "I28",
        "gabaritos": "I30",
        "notes": "H35",
        "estrutural": "I53",
        "funcional": "K53",
        "durabilidade": "M53",
    }

    _THERAPY_DESC_CELL = "H41"

    _PICTURE_RANGES = ["B6:G26", "K6:P26", "B30:G50", "K30:P50"]
    _PICTURE_CODE_CELLS = ["B27", "K27", "B51", "K51"]
    _PICTURE_DESCRIPTION_CELLS = ["D27", "M27", "D51", "M51"]

    _GEOELEMENT_FIELDS = {
        "vaos": "B13",
        "pilares": "B15",
        "vigas": "F15",
        "juntasDeDilatacaoElemGeom": "F17",
    }

    _TWO_DECIMAL_PLACES = {
        "larguraTabuleiro": "B17",
        "comprimentoTotal": "F13",
    }


class InitialTunnel(InitialARTESP):
    _XLSX_HANDLER: type = XlsxHandler
    _EXPORT_NAME = "Inicial_Túnel"

    def __init__(
        self,
        uuids: List[str] = None,
        report_format: ReportFormat = ReportFormat.XLSX,
    ) -> None:
        super().__init__(uuids, report_format)


@task
def ccr_report_initial_tunnel_async_handler(
    reporter_dict: dict,
):
    reporter: InitialTunnel = InitialTunnel.from_dict(reporter_dict)
    reporter.export()
