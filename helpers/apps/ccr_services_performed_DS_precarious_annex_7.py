import re
from datetime import datetime, timedelta
from typing import List, Literal, Union
from zipfile import ZipFile

from django.db.models import BooleanField, Case, Value, When
from zappa.asynchronous import task

from apps.reportings.models import Reporting
from helpers.apps.ccr_report_utils.ccr_report import CCRReport
from helpers.apps.ccr_report_utils.export_utils import (
    get_conditions_date,
    get_s3,
    upload_file,
)
from helpers.apps.ccr_report_utils.image import ReportFormat
from helpers.apps.ccr_report_utils.pdf import convert_files_to_pdf
from helpers.import_excel.base_ccr_services_performed_annex_7 import (
    XlsxHandlerBaseServicePerformedAnnex7,
)


class XlsxHandler(XlsxHandlerBaseServicePerformedAnnex7):
    def __init__(
        self, s3, query_set_serializer, sheet_target, file_name_single, **kwargs
    ):
        super().__init__(
            s3=s3,
            query_set_serializer=query_set_serializer,
            path_file_xlsx="./fixtures/reports/ccr_services_performed_annex_7.xlsx",
            sheet_target=sheet_target,
            file_name_single=file_name_single,
            title="Anexo VII - Serviços Realizados no Período - Drenagem Superficial \n",
            text_fix="Precário",
            logo_company_range_string="K1:K1",
            provider_logo_range_string="A1:A1",
            executed_at_after=kwargs.pop("executed_at_after", None),
            executed_at_before=kwargs.pop("executed_at_before", None),
            pk_invalid=kwargs.pop("pk_invalid", []),
        )


class ServicesPerformedDSPrecariousAnnex7(CCRReport):
    def __init__(
        self,
        uuids: List[str] = None,
        panel_id: str = "",
        executed_at: dict = {},
        report_format: ReportFormat = ReportFormat.XLSX,
    ) -> None:
        self.limit_date_executed_at = 30
        self.select_option: int = 3
        self.options = [
            {"name": "Bom", "value": "1"},
            {"name": "Regular", "value": "2"},
            {"name": "Precário", "value": "3"},
        ]

        self.executed_at_after = None
        self.executed_at_before = None
        self.panel_id = panel_id
        self.executed_at = executed_at
        self.__set_executed_at(executed_at, panel_id)
        self.queryset_reportings_serializer: str = ""
        self.tags: Union[List[str], List[dict]] = []
        self.pk_invalid = []
        if uuids:
            self.__set_class(uuids)

        self.file_name_single = "Anexo VII - Serviços Realizados DS - %s"
        self.file_name_zip = "Anexo VII - Serviços Realizados DS - Precarios_%s.zip"
        super().__init__(uuids, report_format)

    def __set_executed_at(self, executed_at: dict, panel_id: str = ""):
        executed_at_after_str = ""
        executed_at_before_str = ""
        if panel_id:
            executed_at_after_str = get_conditions_date(
                panel_id, "executed_at__date__gt", r"\d+\-\d+\-\d+"
            )
            executed_at_before_str = get_conditions_date(
                panel_id, "executed_at__date__lt", r"\d+\-\d+\-\d+"
            )
        else:
            executed_at_after_str = executed_at.get("after")
            executed_at_before_str = executed_at.get("before")

        self.executed_at_after = (
            datetime.strptime(executed_at_after_str, "%Y-%m-%d")
            if executed_at_after_str
            else datetime.now()
        )

        self.executed_at_before = (
            datetime.strptime(executed_at_before_str, "%Y-%m-%d")
            + timedelta(days=self.limit_date_executed_at, hours=23, minutes=59)
            if executed_at_before_str
            else datetime.now().date()
            + timedelta(days=self.limit_date_executed_at, hours=23, minutes=59)
        )

    def __set_class(self, uuids):
        query_set = Reporting.objects.filter(uuid__in=uuids, company__isnull=False)
        if query_set.exists():
            if self.executed_at_after and self.executed_at_before:
                company = query_set.first().company
                class_pk = company.metadata[
                    "report_surface_drainage_monitoring_form_id"
                ]
                query_set = (
                    query_set.prefetch_related(
                        "occurrence_type",
                        "company",
                        "parent",
                        "reporting_relation_parent",
                        "reporting_relation_parent__child",
                    )
                    .filter(
                        occurrence_type_id=class_pk,
                    )
                    .distinct()
                )
                self.pk_invalid = [
                    str(x.pk)
                    for x in query_set.exclude(
                        form_data__general_conservation_state=self.options[
                            self.select_option - 1
                        ].get("value"),
                        reporting_relation_parent__child__executed_at__gte=self.executed_at_after,
                        reporting_relation_parent__child__executed_at__lte=self.executed_at_before,
                    ).distinct()
                ]

                query_set = query_set.annotate(
                    is_valid=Case(
                        When(
                            pk__in=self.pk_invalid,
                            then=Value(False),
                        ),
                        default=Value(True),
                        output_field=BooleanField(),
                    )
                )

                self.uuids = [str(x) for x in query_set.values_list("pk", flat=True)]
                self.tags = [
                    re.sub(r"[-\ ]", "", x)
                    for x in list(
                        set(query_set.values_list("road_name", flat=True).distinct())
                    )
                ]
                self.tags.sort()

            else:
                query_set = query_set.none()

        self.executed_at_after = self.executed_at_after.strftime("%Y-%m-%d")
        self.executed_at_before = self.executed_at_before.strftime("%Y-%m-%d")

        self.queryset_reportings_serializer = self.serializer_queryset(query_set)

    def get_file_name(self) -> str:
        file_name = ""
        tags = self.tags

        if len(tags) == 1:
            file = self.file_name_single % tags[0]
            extension = "xlsx"
            if self.report_format() == ReportFormat.PDF:
                extension = "pdf"

            file_name = f"{file}.{extension}"
        else:
            file_name = self.file_name_zip % "_".join(tags)

        return file_name

    def export(self) -> Literal[True]:
        s3 = get_s3()
        files = XlsxHandler(
            s3=s3,
            query_set_serializer=self.queryset_reportings_serializer,
            sheet_target=self.sheet_target(),
            file_name_single=self.file_name_single,
            executed_at_after=self.executed_at_after,
            executed_at_before=self.executed_at_before,
            pk_invalid=self.pk_invalid,
        ).execute()
        result_file = ""

        if self.report_format() == ReportFormat.PDF:
            files = convert_files_to_pdf(files)

        result_file = ""
        if len(files) == 1:
            result_file = files[0]
        elif len(files) > 1:
            result_file = f"/tmp/{self.get_file_name()}"
            with ZipFile(result_file, "w") as zipObj:
                for file in files:
                    zipObj.write(file, file.split("/")[-1])

        upload_file(s3, result_file, self.object_name)
        return True


@task
def ccr_services_performed_ds_precarious_annex7_async_handler(reporter_dict):
    instance = ServicesPerformedDSPrecariousAnnex7.from_dict(reporter_dict)
    instance.export()
