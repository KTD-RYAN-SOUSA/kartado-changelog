import json
import logging
import os
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from os.path import splitext
from typing import List, Tuple
from urllib import parse, request

import boto3
import sentry_sdk
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from pdfminer.high_level import extract_text
from zappa.asynchronous import task

from apps.approval_flows.models import ApprovalStep
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import Reporting, ReportingFile
from apps.reportings.serializers import ReportingFileSerializer, ReportingSerializer
from apps.roads.models import Road
from apps.templates.models import PDFImport
from apps.users.models import User
from helpers.apps.json_logic import apply_json_logic
from helpers.dates import to_utc_string
from helpers.forms import get_form_metadata
from helpers.import_pdf.exceptions import (
    MixedPDFFormatException,
    PageLimitExceededException,
    UnsupportedPDFFormatException,
)
from helpers.import_pdf.extractors.factory import DINExtractorFactory
from helpers.strings import dict_to_casing, get_obj_from_path
from RoadLabsAPI.settings import credentials


@task
def parse_pdf_to_json(pdf_import_id, user_id):
    try:
        pdf_import = PDFImport.objects.get(pk=pdf_import_id)
        user = User.objects.get(pk=user_id)
    except PDFImport.DoesNotExist as e:
        sentry_sdk.capture_exception(e)
        logging.error("PDFImport instance doesn't exist for this PK")
    except User.DoesNotExist as e:
        sentry_sdk.capture_exception(e)
        logging.error("User instance doesn't exist for this PK")
    else:
        try:
            parsed_pdf_import = ImportPDF(pdf_import, user).get_pdf_import()
            parsed_pdf_import.save()
            logging.info("PDF parsing done!")
        except (
            UnsupportedPDFFormatException,
            MixedPDFFormatException,
            PageLimitExceededException,
        ) as e:
            logging.error(f"PDF format validation failed: {str(e)}")
            pdf_import.error = True
            pdf_import.description = str(e)
            pdf_import.save()
        except Exception as e:
            sentry_sdk.capture_exception(e)
            logging.error(f"Unexpected error parsing PDF: {str(e)}")
            pdf_import.error = True
            pdf_import.save()


@task
def parse_pdf_json_to_objs(pdf_import_id, reportings_data={}):
    try:
        pdf_import = PDFImport.objects.get(pk=pdf_import_id)
    except PDFImport.DoesNotExist as e:
        sentry_sdk.capture_exception(e)
        logging.error("PDFImport instance doesn't exist for this PK")
    else:
        # Error until proven error free
        error = True

        # Parse json data
        try:
            data = json.loads(pdf_import.preview_file.read())
        except Exception as e:
            sentry_sdk.capture_exception(e)
            data = {}

        if data:
            # Change all keys to snake_case
            data = dict_to_casing(data, format_type="underscore")
            reportings_data = dict_to_casing(reportings_data, format_type="underscore")

            deferred_objs = []
            reportings = reportings_data.get("reportings", [])
            images = data.get("images", {})
            num_images = sum(
                len(v) if isinstance(v, list) else 1 for v in images.values()
            )
            num_of_items = len(reportings) + num_images

            occ_type_uuids = [str(r["occurrence_type"]).strip() for r in reportings]
            occurrence_types = OccurrenceType.objects.filter(
                uuid__in=occ_type_uuids
            ).distinct()
            occurrence_types_dict = {
                str(occ_type.uuid): occ_type for occ_type in occurrence_types
            }
            for reporting in reportings:
                # Required Reporting data
                form_data = reporting.get("form_data", {})
                form_metadata = {}
                occurrence_type = occurrence_types_dict.get(
                    str(reporting["occurrence_type"]).strip(), None
                )
                if form_data and occurrence_type:
                    form_metadata = get_form_metadata(
                        form_data,
                        occurrence_type,
                    )
                reporting_data = {
                    # From model
                    "pdf_import_id": pdf_import.pk,
                    "company_id": pdf_import.company.pk,
                    "firm_id": reporting["firm"],
                    "menu_id": pdf_import.menu.pk,
                    "lane": pdf_import.lane,
                    "status_id": pdf_import.status.pk,
                    "created_by_id": pdf_import.created_by.pk,
                    "occurrence_type_id": reporting["occurrence_type"],
                    # From json data
                    "form_data": form_data,
                    "form_metadata": form_metadata,
                    "uuid": reporting["uuid"],
                    "road_name": reporting["road_name"],
                    "km": reporting["km"],
                    "end_km": reporting["end_km"],
                    "direction": reporting["direction"],
                    # Config
                    "end_km_manually_specified": True,
                }

                # Set default approval step
                approval_step = ApprovalStep.objects.filter(
                    approval_flow__company=reporting_data["company_id"],
                    approval_flow__target_model="reportings.Reporting",
                    previous_steps__isnull=True,
                ).first()
                if approval_step:
                    reporting_data["approval_step_id"] = str(approval_step.uuid)

                # Parse dates
                current_timezone = timezone.get_current_timezone()
                try:
                    found_at = datetime.strptime(reporting["found_at"], "%d/%m/%Y")
                    # Add timezone
                    found_at = found_at.replace(tzinfo=current_timezone)
                except Exception:
                    reporting_data["found_at"] = timezone.now()
                else:
                    reporting_data["found_at"] = found_at

                try:
                    due_at = datetime.strptime(reporting["due_at"], "%d/%m/%Y")

                    # Add timezone
                    due_at = due_at.replace(tzinfo=current_timezone)
                except Exception:
                    # Don't provide due_at
                    pass
                else:
                    reporting_data["due_at"] = due_at
                    reporting_data["due_at_manually_specified"] = True

                # Optional Reporting data from model
                if pdf_import.track:
                    reporting_data["track"] = pdf_import.track
                if pdf_import.branch:
                    reporting_data["branch"] = pdf_import.branch
                if pdf_import.km_reference:
                    reporting_data["km_reference"] = pdf_import.km_reference

                # Defer Reporting save() if valid
                serialized_reporting = ReportingSerializer(data=reporting_data)
                if serialized_reporting.is_valid():
                    deferred_objs.append(Reporting(**reporting_data))
                else:
                    break

                # Handle images
                image_info = images.get(reporting["supervision_code"], "")

                # If there's no image info for that code, continue to next reporting
                if not image_info:
                    continue

                # Suporta uma imagem (dict, two_column) ou múltiplas (list, one_column)
                image_list = (
                    image_info if isinstance(image_info, list) else [image_info]
                )

                for image_item in image_list:
                    image_url = image_item.get("url", "")
                    image_uuid = image_item.get("uuid", "")

                    if image_url and image_uuid:
                        reporting_file_data = {
                            "uuid": image_uuid,
                            "created_by_id": pdf_import.created_by.pk,
                            "km": reporting["km"],
                            "upload": {"filename": image_url},
                        }
                    else:
                        break

                    # Handle upload field
                    image_name = parse.urlparse(image_url).path.split("/")[-1]
                    tmpfile, _ = request.urlretrieve(image_url)
                    image_file = SimpleUploadedFile(
                        image_name, open(tmpfile, "rb").read()
                    )

                    # Handle optional fields for ReportingFile
                    if pdf_import.description:
                        reporting_file_data["description"] = pdf_import.description
                    if pdf_import.kind:
                        reporting_file_data["kind"] = pdf_import.kind

                    # Defer ReportingFile save() if valid
                    serialized_reporting_file = ReportingFileSerializer(
                        data=reporting_file_data
                    )
                    if serialized_reporting_file.is_valid():
                        reporting_file_data["reporting_id"] = reporting["uuid"]
                        reporting_file_obj = ReportingFile(**reporting_file_data)
                        reporting_file_obj.upload = image_file
                        deferred_objs.append(reporting_file_obj)
                    else:
                        break

            # Create all deferred objects
            if num_of_items == len(deferred_objs):
                error = False
                for obj in deferred_objs:
                    logging.info("{}: {}".format(obj._meta.model_name, obj.uuid))
                    obj.save()

                    # Add created_by user to history (fallback for Zappa)
                    hist = obj.history.first()
                    if hist and not hist.history_user:
                        hist.history_user = obj.created_by
                        hist.save()

        # Set as done and set final error status
        pdf_import.error = error
        pdf_import.done = True
        pdf_import.save()

        logging.info("JSON parsing done!")


PROPERTY_TO_HEADING = OrderedDict(
    {
        "supervision_code": "Código Fiscalização:",
        "dealership": "Concessionária:",
        "lot": "Lote:",
        "road_name": "Rodovia (SP):",
        "road": "Rodovia:",
        "km": ("KM+MTS - Inicial:", "Km+m - Inicial:"),
        "end_km": ("KM+MTS - Final:", "Km+m - Final:"),
        "direction": "Sentido:",
        "activity": "Atividade:",
        "note": "Observação:",
        "found_at": "Constatação -",
        "due_at": "Data Limite para Reparo -",
    }
)

PROPERTY_TO_HEADING_ONE_COLUMN = OrderedDict(
    {
        "supervision_code": "Código Fiscalização:",
        "dealership": "Concessionária:",
        "lot": "Lote:",
        "road_name": "Rodovia (SP):",
        "direction": "Sentido:",
        "km": ("KM+MTS - Inicial:", "Km+m - Inicial:"),
        "end_km": ("KM+MTS - Final:", "Km+m - Final:"),
        "type_activity": "Tipo Atividade:",
        "group_activity": "Grupo Atividade:",
        "activity": "Atividade:",
        "due_at": "Data Limite para Reparo:",
        "note": "Observação:",
        "found_at": "Constatação -",
    }
)


class ImportPDF:
    """
    Rules:

    1) All datetime objects must use function to_utc_string
    """

    temp_path = "/tmp/pdf_import/"

    def __init__(self, pdf_import, user):
        self.file_name = ""
        self.uuid = str(pdf_import.pk)
        self.pdf_import = pdf_import
        self.company_id = str(pdf_import.company_id)
        self.company = pdf_import.company
        self.user_id = str(user.uuid)
        self.created_at = to_utc_string(datetime.now())
        self.count_images = 0
        self.detected_format = None

    def download_pdf_file(self):
        if self.pdf_import.pdf_file:
            try:
                unquoted_file_path = parse.unquote(self.pdf_import.pdf_file.url)
                file_path = unquoted_file_path.split("?")[0].split(".com/")[1]
                bucket_name = unquoted_file_path.split(".s3")[0].split("/")[-1]
                full_file_name = file_path.split("/")[-1]
                file_name, file_format = splitext(full_file_name)
            except Exception as e:
                sentry_sdk.capture_exception(e)
                return ""

            file_temp_path = "{}{}{}{}".format(
                self.temp_path, file_name, self.uuid, file_format
            )

            try:
                self.s3.download_file(bucket_name, file_path, file_temp_path)
            except Exception as e:
                sentry_sdk.capture_exception(e)
                return ""
            else:
                return file_temp_path
        return ""

    def refine_kms(self, nc_km):
        try:
            # Garante que só a primeira linha é usada (evita contaminação por campos fora de ordem no PDF)
            nc_km = nc_km.split("\n")[0].strip()
            # Split into kilometer and meter (also strip whitespace)
            (kms, meters) = [chunk.strip() for chunk in nc_km.split("+")]
            # Use the proper float format and convert it to float
            float_km = float("{}.{}".format(kms, meters))
        except Exception:
            float_km = None

        return float_km

    def refine_direction(self, nc_direction):
        default_direction_value = get_obj_from_path(
            self.company.custom_options,
            "reporting__fields__direction__defaultvalue",
        )
        possible_direction_path = "reporting__fields__direction__selectoptions__options"
        possible_directions = get_obj_from_path(
            self.company.custom_options, possible_direction_path
        )
        direction_to_value = {
            option["name"]: option["value"]
            for option in possible_directions
            if "value" in option and "name" in option
        }

        if nc_direction in direction_to_value:
            return direction_to_value[nc_direction]
        elif default_direction_value:
            return default_direction_value
        else:
            return None

    def refine_road_name(self, nc_road_name):
        # Garante que só a primeira linha é usada (evita contaminação por campos fora de ordem no PDF)
        nc_road_name = nc_road_name.split("\n")[0].strip()
        # Change spaces to hyphen
        nc_road_name = nc_road_name.replace(" ", "-")

        self.road = Road.objects.filter(company=self.company, name=nc_road_name).first()

        return self.road.name if self.road else None

    def refine_notes(self, nc_note, nc_activity):
        refined_note = ""
        append_template = "{}\n\n"

        if nc_note:
            refined_note += append_template.format(nc_note)
        if nc_activity:
            # Garante que só a primeira linha é usada (evita contaminação por campos fora de ordem no PDF)
            nc_activity = nc_activity.split("\n")[0].strip()
            # Não adiciona atividade se já está presente na observação
            note_stripped = nc_note.strip() if nc_note else ""
            if nc_activity not in note_stripped:
                refined_note += append_template.format(nc_activity)

        return refined_note.strip() if refined_note else None

    def refine_date(self, string_date: str):
        try:
            # Validar se string não está vazia antes de fazer split
            if not string_date or not string_date.strip():
                return None

            string_date = string_date.split()[0]
            # NOTE: result ignored on purpose
            datetime.strptime(string_date, "%d/%m/%Y")

            return string_date
        except (ValueError, IndexError):
            return None

    def refine_entries(self, extracted_entries):
        for entry in extracted_entries:
            # Prepare column errors (added only if there are errors)
            column_errors = []

            def append_column_error(property):
                """
                Appends error to error list for the given property.
                Assumes column_errors exists.
                """
                heading = PROPERTY_TO_HEADING[property]
                if isinstance(heading, tuple):
                    for name in heading:
                        column_errors.append(name)
                else:
                    column_errors.append(heading)

            # Inject entry uuid
            entry["uuid"] = str(uuid.uuid4())

            # Refine km
            refined_km = self.refine_kms(entry["km"])
            entry["km"] = refined_km
            if refined_km is None:
                append_column_error("km")

            # Refine end_km
            refined_end_km = self.refine_kms(entry["end_km"])
            entry["end_km"] = refined_end_km
            if refined_end_km is None:
                append_column_error("end_km")

            # Refine direction
            refined_direction = self.refine_direction(entry["direction"])
            entry["direction"] = refined_direction
            if refined_direction is None:
                append_column_error("direction")

            # Refine road & road_name
            refined_road_name = self.refine_road_name(entry["road_name"])
            entry["road_name"] = refined_road_name
            if refined_road_name is None:
                append_column_error("road_name")

            # Refine supervision_code (garante que só a primeira linha é usada)
            if entry.get("supervision_code"):
                entry["supervision_code"] = (
                    entry["supervision_code"].split("\n")[0].strip()
                )

            # Refine activity (garante que só a primeira linha é usada)
            if entry.get("activity"):
                entry["activity"] = entry["activity"].split("\n")[0].strip()

            # Truncate note before first known heading (evita contaminação por leitura
            # em colunas pelo pdfminer em páginas com poucos NCs)
            note_text = entry.get("note", "")
            for heading in PROPERTY_TO_HEADING.values():
                if isinstance(heading, tuple):
                    continue
                idx = note_text.find(heading)
                if idx > 0:
                    note_text = note_text[:idx].strip()
                    break
            entry["note"] = note_text

            # Refine notes
            refined_notes = self.refine_notes(entry["note"], entry["activity"])
            entry["form_data"]["notes"] = refined_notes
            if refined_notes is None:
                append_column_error("activity")

            # Refine dates
            entry["found_at"] = self.refine_date(entry.get("found_at", ""))
            entry["due_at"] = self.refine_date(entry.get("due_at", ""))

            # Add artesp code
            entry["form_data"]["artesp_code"] = entry["supervision_code"]

            if self.road and self.road.lot_logic and self.road.lot_logic != {}:
                try:
                    lot = apply_json_logic(
                        self.road.lot_logic,
                        {"data": {"km": entry.get("km", None)}},
                    )
                except Exception:
                    lot = ""
                if not lot:
                    append_column_error("km")

            # If there are errors
            if column_errors:
                entry["column_errors"] = column_errors

    def extract_reportings(self, pdf_format=None):
        heading_map = (
            PROPERTY_TO_HEADING_ONE_COLUMN
            if pdf_format == "one_column"
            else PROPERTY_TO_HEADING
        )

        # Setup
        pdf_text = extract_text(self.file_name).strip()
        # Remove page title from pdf_text (suporta 1 e 2 colunas)
        page_text = pdf_text.replace("Relatório de Conservação de Rotina", "")
        page_text = page_text.replace(
            "Relatório de Fiscalização de Conservação de Rotina", ""
        )

        first_heading = next(iter(heading_map.values()))
        # Separate text by entry using first header
        entries = [
            first_heading + entry
            for entry in page_text.split(first_heading)
            if entry.strip()
        ]

        def remove_heading(entry, heading):
            """
            Removes heading for that section and strips it from empty space
            """
            return entry.replace(heading, "").strip()

        def find_exact_heading(text, heading):
            """
            Finds the exact heading in the text, avoiding false matches.

            :param text: The text to search within.
            :param heading: The heading to find.
            :return: The index of the exact heading or -1 if not found.
            """
            idx = text.find(heading)
            while idx >= 0:
                is_false_match = any(
                    isinstance(v, str)
                    and len(v) > len(heading)
                    and v.endswith(heading)
                    and text[idx - (len(v) - len(heading)) : idx + len(heading)] == v
                    for v in heading_map.values()
                )
                if not is_false_match:
                    return idx
                idx = text.find(heading, idx + 1)
            return -1

        # Extract info for each entry
        extracted_entries = []
        for entry in entries:
            # Find index of the starting point for each heading
            fields: List[Tuple[str, str, int]] = []
            for api_name, heading in heading_map.items():
                if isinstance(heading, tuple):
                    # This api name accepts more than one heading
                    idx = -1
                    heading_name = ""
                    for name in heading:
                        heading_name = name
                        idx = (
                            find_exact_heading(entry, name)
                            if pdf_format == "one_column"
                            else entry.find(name)
                        )
                        if idx > 0:
                            # A heading for this api name was found, stop searching
                            break
                    fields.append((heading_name, api_name, idx))
                else:
                    idx = (
                        find_exact_heading(entry, heading)
                        if pdf_format == "one_column"
                        else entry.find(heading)
                    )
                    fields.append((heading, api_name, idx))

            # Extract data (in order of the headings)
            extracted_data = {}

            field_it = iter(fields)
            field = next(field_it, None)
            api_name = None
            while field is not None:
                # Check if next item in list exists and extract section
                (heading, api_name, start) = field
                next_field = next(field_it, None)
                if next_field:
                    (_, _, end) = next_field
                    section = entry[start:end]
                else:
                    section = entry[start:]
                field = next_field

                section_data = remove_heading(section, heading)
                if api_name not in extracted_data:
                    extracted_data[api_name] = section_data

            # Check if last data item has residual bottom info and removes it
            if extracted_data:
                last_api_name = api_name
                last_item_split = extracted_data[last_api_name].split("\n")
                if len(last_item_split) > 1:
                    extracted_data[last_api_name] = last_item_split[0]

            extracted_data["form_data"] = {}

            extracted_entries.append(extracted_data)

        # Refine extracted data
        self.refine_entries(extracted_entries)

        return extracted_entries

    def upload_images(self, filenames):
        images_info = {}

        for filename in filenames:
            try:
                image_full_path = self.temp_path + filename

                bucket_name = settings.AWS_STORAGE_BUCKET_NAME
                expires = timezone.now() + timedelta(hours=6)
                object_name = "media/private/{}".format(filename)

                self.s3.upload_file(
                    image_full_path,
                    bucket_name,
                    object_name,
                    ExtraArgs={"Expires": expires},
                )
                url_s3 = self.s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket_name, "Key": object_name},
                )
                self.count_images += 1
            except Exception:
                url_s3 = ""

            filename_without_ext = filename.rsplit(".", 1)[0]
            parts = filename_without_ext.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                # Formato com índice: {nc}_{index}.png (one_column com múltiplas imagens)
                nc_code = parts[0]
                if nc_code not in images_info:
                    images_info[nc_code] = []
                images_info[nc_code].append({"url": url_s3, "uuid": str(uuid.uuid4())})
            else:
                # Formato simples: {nc}.png (two_column, uma imagem por NC)
                images_info[filename_without_ext] = {
                    "url": url_s3,
                    "uuid": str(uuid.uuid4()),
                }

        return images_info

    def get_data(self):
        pdf_format = None
        images_info = {}
        extractor = None

        try:
            extractor, pdf_format = DINExtractorFactory.create(self.file_name)
        except (
            UnsupportedPDFFormatException,
            MixedPDFFormatException,
            PageLimitExceededException,
        ) as e:
            logging.error(f"PDF format error: {str(e)}")
            raise
        except Exception as e:
            logging.error(f"Unexpected error creating extractor: {str(e)}")
            sentry_sdk.capture_exception(e)

        reportings = self.extract_reportings(pdf_format)

        if extractor and reportings:
            try:
                image_filenames = extractor.extract_images(reportings)
                images_info = self.upload_images(image_filenames)
            except Exception as e:
                logging.error(f"Unexpected error extracting images: {str(e)}")
                sentry_sdk.capture_exception(e)
                images_info = {}

        if reportings:
            result = {"reportings": reportings, "images": images_info}
            if pdf_format:
                result["pdf_format"] = pdf_format
            return result
        else:
            return {}

    def get_pdf_import(self):
        error = True

        # Get S3 Client
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=credentials.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=credentials.AWS_SECRET_ACCESS_KEY,
            aws_session_token=credentials.AWS_SESSION_TOKEN,
        )

        # Create temporary folder
        os.makedirs(self.temp_path, exist_ok=True)
        json_name = "{}.json".format(self.uuid)
        json_file_path = self.temp_path + json_name

        # Download pdf
        self.file_name = self.download_pdf_file()
        if self.file_name:
            data = self.get_data()

            if data:
                # Capturar formato detectado antes de camelizar
                self.detected_format = data.get("pdf_format")

                # Camelize data
                data = dict_to_casing(data)

                with open(json_file_path, "w") as outfile:
                    json.dump(data, outfile)

                json_file = open(json_file_path, "rb")
                self.pdf_import.preview_file.save(
                    json_name, ContentFile(json_file.read())
                )

                has_errors = [
                    error_column
                    for item in data["reportings"]
                    for error_column in item.get("columnErrors", [])
                ]
                if not has_errors:
                    error = False

        self.pdf_import.error = error

        # Delete temp files
        for file_name in os.listdir(self.temp_path):
            os.remove(self.temp_path + file_name)

        # Delete temporary folder
        os.rmdir(self.temp_path)

        return self.pdf_import
