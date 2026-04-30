from zappa.asynchronous import task

from helpers.apps.ccr_report_oac_vii import OACVII, XlsxHandler


class RegularXlsxHandler(XlsxHandler):
    _ELEMENT_HOLE_CLASSIFICATION = "2"
    _TEMPLATE_FILE = "./fixtures/reports/oac_vii_regular.xlsx"
    _TEMPLATE_EMPTY_FILE = "./fixtures/reports/oac_vii_regular_empty.xlsx"


class OACVIIRegular(OACVII):
    _CLASSIFICATION = "Regulares"
    _XLSX_HANDLER = RegularXlsxHandler


@task
def ccr_report_oac_vii_regular_async_handler(
    reporter_dict: dict,
):
    reporter: OACVIIRegular = OACVIIRegular.from_dict(reporter_dict)
    reporter.export()
