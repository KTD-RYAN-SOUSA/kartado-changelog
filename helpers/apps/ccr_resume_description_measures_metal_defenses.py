from helpers.apps.ccr_report_utils.image import ReportFormat, SheetTarget
from helpers.import_excel.ccr_eps_mixins import XlsxHandlerBaseEPS


class XlsxHandlerResumeReportDescriptionMeasuresMetalDefenses(XlsxHandlerBaseEPS):
    def __init__(
        self,
        uuid: str,
        list_uuids: list,
        s3,
        sheet_target: SheetTarget = SheetTarget.DesktopExcel,
        report_format: ReportFormat = ReportFormat.XLSX,
    ):
        super().__init__(
            uuid,
            list_uuids,
            s3,
            path_file="./fixtures/reports/ccr_resume_description_therapy_eps.xlsx",
            file_name="ANEXO IX.2 Descrição das Providências - Defensas Metálicas - ",
            class_name="Monitoração de Defensas Metálicas",
            title="Anexo IX.2 Defensas Metálicas \n%s",
            dispositive="Defesa Metálica",
            sheet_target=sheet_target,
            report_format=report_format,
        )
