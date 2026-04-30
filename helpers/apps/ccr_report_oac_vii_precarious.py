from zappa.asynchronous import task

from helpers.apps.ccr_report_oac_vii import OACVII, XlsxHandler


class PrecariousXlsxHandler(XlsxHandler):
    _ELEMENT_HOLE_CLASSIFICATION = "3"
    _TEMPLATE_FILE = "./fixtures/reports/oac_vii_precarious.xlsx"
    _TEMPLATE_EMPTY_FILE = "./fixtures/reports/oac_vii_precarious_empty.xlsx"


class OACVIIPrecarious(OACVII):
    _CLASSIFICATION = "Precários"
    _XLSX_HANDLER = PrecariousXlsxHandler


@task
def ccr_report_oac_vii_precarious_async_handler(
    reporter_dict: dict,
):
    reporter: OACVIIPrecarious = OACVIIPrecarious.from_dict(reporter_dict)
    reporter.export()
