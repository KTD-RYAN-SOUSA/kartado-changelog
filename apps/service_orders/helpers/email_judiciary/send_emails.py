import logging

import sentry_sdk
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from zappa.asynchronous import task

from apps.files.models import FileDownload
from apps.occurrence_records.views import OccurrenceRecordView
from apps.service_orders.helpers.email_judiciary.context_check_email_judiciary import (
    get_obra_sequencial_identificador,
)
from apps.service_orders.helpers.report_config_map_default import (
    get_default_config_map_to_report,
)
from apps.service_orders.models import Procedure
from helpers.gen_files.zip import download_file_and_zip
from helpers.middlewares import get_current_request
from helpers.notifications import create_notifications
from helpers.strings import clean_string


def get_record_file_name(record, file, blacklist):
    index = 0
    try:
        file_name = "{} - {}.{}".format(
            record.number,
            file.description,
            file.upload.name.split(".")[-1],
        )
        while file_name in blacklist:
            index += 1
            file_name = "{} - {} ({}).{}".format(
                record.number,
                file.description,
                index,
                file.upload.name.split(".")[-1],
            )
        return file_name
    except Exception:
        return file.upload.name


@task
def process_judiciary_emails(procedure_id: str, issuer_id: str):

    TEMPLATE_PATH = "service_orders/email/procedure_created"

    try:
        procedure = Procedure.objects.get(pk=procedure_id)
    except Procedure.DoesNotExist:
        logging.error(
            "process_judiciary_emails: Provided Procedure UUID does not exist in the database"
        )

    try:
        # General email data
        service_order = procedure.action.service_order
        company = service_order.company
        judiciary_users = company.get_judiciary_users()
        url = "{}/#/SharedLink/Procedure/{}/show?company={}".format(
            settings.FRONTEND_URL, str(procedure.uuid), str(company.uuid)
        )
        email_data = {
            "to_do": clean_string(procedure.to_do) if procedure.to_do.split() else "",
            "action": procedure.action.name,
            "deadline": procedure.deadline.strftime("%d/%m/%Y às %H:%M"),
            "os_number": service_order.number,
            "os_description": service_order.description,
            "responsible": (
                procedure.responsible.get_full_name() if procedure.responsible else ""
            ),
            "created_by": (
                procedure.created_by.get_full_name() if procedure.created_by else ""
            ),
            "created_at": procedure.created_at.strftime("%d/%m/%Y"),
            "url": url,
            "company_id": str(company.pk),
        }
        # NOTE: Sadly we can't use values_list to get the full url, only the filename
        files_data = {
            "links": [
                {"url": file.upload.url, "file_name": file.upload.name}
                for file in procedure.procedure_files.all()
            ],
            "views": [],
        }

        # Add files from each ServiceOrder to files_data
        for record in service_order.so_records.all():
            for file in record.file.all():
                file_name = get_record_file_name(
                    record, file, [a["file_name"] for a in files_data["links"]]
                )
                files_data["links"].append(
                    {"url": file.upload.url, "file_name": file_name}
                )

            request = get_current_request(default_to_empty_request=True)
            if not hasattr(request, "data"):
                request.data = {}
            request.data.update(get_default_config_map_to_report(record))
            files_data["views"].extend(
                [
                    OccurrenceRecordView.pdf_report_occurrence_record(
                        "", request, str(record.pk)
                    )
                ]
            )

        # Process main OccurrenceRecord
        rep_record = service_order.get_main_occurrence_record()
        if rep_record:
            # Fetch the property intersection info
            try:
                main_property = rep_record.get_main_property(
                    service_order.shape_file_property
                )
            except Exception as e:
                # Handle the problem but report it to Sentry
                sentry_sdk.capture_exception(e)

            if main_property:
                (
                    OBRA,
                    SEQUENCIAL,
                    IDENTIFICADOR,
                ) = get_obra_sequencial_identificador(main_property)

                ID = main_property["attributes"]["OBJECTID"]
            else:
                OBRA, SEQUENCIAL, IDENTIFICADOR, ID = "", "", "", ""

            OFFENDER_NAME = service_order.get_offender_name()
            PROCESS = service_order.get_process_type_display()

            file_name = f"Arquivos {service_order.number} - {procedure_id}.zip"

            zip_url = download_file_and_zip(
                files_data=files_data, zip_filename=file_name
            )

            if zip_url:
                with transaction.atomic():
                    download = FileDownload.objects.create(
                        file_name=file_name,
                        object_id=procedure.pk,
                        file=zip_url,
                        service_order_id=service_order.pk,
                        content_type=ContentType.objects.get_for_model(Procedure),
                    )
                    BACKEND_URL = settings.BACKEND_URL
                    zip_file_url = "{}/FileDownload/{}".format(
                        BACKEND_URL, str(download.pk)
                    )

                    service_order_action_name = (
                        procedure.action.name if procedure.action else ""
                    )

                    subject = f"{service_order_action_name}: {PROCESS} - {OBRA} - {SEQUENCIAL} - ID: {IDENTIFICADOR}"
                    if OFFENDER_NAME:
                        subject += " - " + OFFENDER_NAME

                    email_data.update(
                        {
                            "process": PROCESS,
                            "construction": OBRA,
                            "id": ID,
                            "sequential": SEQUENCIAL,
                            "identifier": IDENTIFICADOR,
                            "offender_name": OFFENDER_NAME,
                            "url": url,
                            "title": subject,
                            "zip_file_url": zip_file_url,
                        }
                    )

                    create_notifications(
                        send_to=judiciary_users,
                        company=company,
                        context=email_data,
                        template_path=TEMPLATE_PATH,
                        can_unsubscribe=False,
                        file_download=download.pk,
                        issuer=issuer_id,
                        extra_email={"send_anyway": True},
                    )
    except Exception as e:
        sentry_sdk.capture_exception(e)
