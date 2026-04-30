import csv
import json
import logging
import os
import uuid
from datetime import datetime
from os.path import splitext
from urllib import parse

import boto3
import sentry_sdk
from django.core.files.base import ContentFile
from zappa.asynchronous import task

from apps.quality_control.serializers import QualityAssaySerializer
from apps.templates.models import CSVImport
from apps.users.models import User
from helpers.dates import to_utc_string
from helpers.strings import dict_to_casing, to_camel_case
from RoadLabsAPI.settings import credentials


@task
def parse_csv_to_json(csv_import_id, user_id):
    try:
        csv_import = CSVImport.objects.get(pk=csv_import_id)
        user = User.objects.get(pk=user_id)
    except CSVImport.DoesNotExist as e:
        sentry_sdk.capture_exception(e)
        logging.error("CSVImport instance doesn't exist for this PK")
    except User.DoesNotExist as e:
        sentry_sdk.capture_exception(e)
        logging.error("User instance doesn't exist for this PK")
    else:
        parsed_csv_import = ImportCSV(csv_import, user).get_csv_import()
        parsed_csv_import.save()
        logging.info("CSV parsing done!")


@task
def group_csv_json(csv_import_id, input_data):
    try:
        csv_import = CSVImport.objects.get(pk=csv_import_id)
    except CSVImport.DoesNotExist as e:
        sentry_sdk.capture_exception(e)
        logging.error("CSVImport instance doesn't exist for this PK")
    else:
        # Error until proven error free
        error = True

        # Parse json data
        try:
            data = json.loads(csv_import.preview_file.read())
        except Exception as e:
            sentry_sdk.capture_exception(e)
            data = {}

        if data:
            entries = data["entries"]
            available_headers = data["headers"]
            grouped_entries = {}

            if set(input_data).issubset(available_headers) or input_data == []:
                # If it's already grouped, turn back into a flat list
                if type(entries) == dict:
                    entries = [
                        entry
                        for grouped_entries in entries.values()
                        for entry in grouped_entries
                    ]

                # Ungrouping
                if input_data == []:
                    # NOTE: entries, at this point, is already ungrouped
                    grouped_by = None
                # Grouping
                elif set(input_data).issubset(available_headers):
                    try:
                        for entry in entries:
                            key_str = ""

                            for header in input_data:
                                if not key_str:
                                    key_str = "'{}=={}'".format(header, entry[header])
                                else:
                                    key_str += "__'{}=={}'".format(
                                        header, entry[header]
                                    )

                            if key_str in grouped_entries:
                                grouped_entries[key_str].append(entry)
                            else:
                                grouped_entries[key_str] = [entry]

                        grouped_entries_with_uuid = {
                            str(uuid.uuid4()): group
                            for group in grouped_entries.values()
                        }

                        entries = grouped_entries_with_uuid
                        grouped_by = input_data
                    except Exception as e:
                        sentry_sdk.capture_exception(e)
                        logging.error("Error while generating key strings")

                data["entries"] = entries
                data["groupedBy"] = grouped_by
                error = False

                # Save changes to preview_file
                TEMP_PATH = "/tmp/csv_import/"
                os.makedirs(TEMP_PATH, exist_ok=True)
                json_name = "{}.json".format(csv_import_id)
                json_file_path = TEMP_PATH + json_name

                with open(json_file_path, "w") as outfile:
                    json.dump(data, outfile)

                json_file = open(json_file_path, "rb")
                csv_import.preview_file.save(json_name, ContentFile(json_file.read()))
            else:
                logging.error("The provided input contains non-valid headers")

            csv_import.error = error
            csv_import.save()

        logging.info("JSON grouping done!")


@task
def parse_csv_json_to_objs(csv_import_id, input_data):
    try:
        csv_import = CSVImport.objects.get(pk=csv_import_id)
    except CSVImport.DoesNotExist as e:
        sentry_sdk.capture_exception(e)
        logging.error("CSVImport instance doesn't exist for this PK")
    else:
        # Error until proven error free
        error = True

        # Parse json data
        try:
            data = json.loads(csv_import.preview_file.read())
        except Exception as e:
            sentry_sdk.capture_exception(e)
            data = {}

        if data:
            deferred_objs = []
            entries = data.get("entries", {})
            entries_are_grouped = type(entries) == dict
            all_input_uuid_present = (
                set(input_data.keys()) == set(entries.keys())
                if entries_are_grouped
                else False
            )

            # Since all_input_uuid_present being true depends on being grouped
            # I don't need to test entries_are_grouped here, only on elif clauses
            if all_input_uuid_present:
                for entry_uuid, entry in entries.items():
                    try:
                        # Handle input for that entry
                        input_for_entry = input_data[entry_uuid]
                        all_input_fields_present = all(
                            field in input_for_entry.keys()
                            for field in [
                                "responsible",
                                "qualityProject",
                                "reportings",
                            ]
                        )
                        if not all_input_fields_present:
                            break

                        # Format reportings
                        reportings = [
                            {"type": "Reporting", "id": reporting_id}
                            for reporting_id in input_for_entry["reportings"]
                        ]

                        quality_assay_data = {
                            # Basic model info
                            "uuid": entry_uuid,
                            "company": {
                                "type": "Company",
                                "id": str(csv_import.company.pk),
                            },
                            "created_by": {
                                "type": "User",
                                "id": str(csv_import.created_by.pk),
                            },
                            "csv_import": {
                                "type": "CSVImport",
                                "id": str(csv_import.pk),
                            },
                            "occurrence_type": {
                                "type": "OccurrenceType",
                                "id": str(csv_import.occurrence_type.pk),
                            },
                            "form_data": csv_import.form_data.copy(),
                            # From input_data
                            "responsible": {
                                "type": "User",
                                "id": input_for_entry["responsible"],
                            },
                            "quality_project": {
                                "type": "QualityProject",
                                "id": input_for_entry["qualityProject"],
                            },
                            "reportings": reportings,
                        }

                        # Inject entry
                        quality_assay_data["form_data"]["imported_data"] = entry

                        serialized_quality_assay = QualityAssaySerializer(
                            data=quality_assay_data
                        )
                        if serialized_quality_assay.is_valid(raise_exception=True):
                            deferred_objs.append(serialized_quality_assay)
                    except Exception as e:
                        sentry_sdk.capture_exception(e)
                        logging.error(
                            "Error parsing instance with the following uuid: {}".format(
                                entry_uuid
                            )
                        )
                        break

                # Create deferred items
                if len(entries.keys()) == len(deferred_objs):
                    error = False
                    for obj in deferred_objs:
                        assay_instance = obj.save()
                        logging.info(
                            "{}: {}".format("QualityAssay", assay_instance.uuid)
                        )

                        # Add created_by user to history (fallback for Zappa)
                        hist = assay_instance.history.first()
                        if hist and not hist.history_user:
                            hist.history_user = assay_instance.created_by
                            hist.save()
            elif not entries_are_grouped:
                logging.error("Entries need to be grouped before running Execute")
            elif not all_input_uuid_present:
                logging.error(
                    "Input needs to cover all entries inside the preview_file"
                )

        # Set as done and set final error status
        csv_import.error = error
        csv_import.done = True
        csv_import.save()

        logging.info("JSON parsing done!")


class ImportCSV:
    temp_path = "/tmp/csv_import/"

    def __init__(self, csv_import, user):
        self.file_name = ""
        self.uuid = str(csv_import.pk)
        self.csv_import = csv_import
        self.company_id = str(csv_import.company_id)
        self.company = csv_import.company
        self.user_id = str(user.uuid)
        self.created_at = to_utc_string(datetime.now())

    def download_csv_file(self):
        if self.csv_import.csv_file:
            try:
                unquoted_file_path = parse.unquote(self.csv_import.csv_file.url)
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

    def refine_entries(self, extracted_entries):
        def capture_error(exc, column_header, column_errors):
            """
            Helper function to easily add column errors and send them to Sentry
            """
            sentry_sdk.capture_exception(exc)
            logging.error("Error parsing " + column_header)
            column_errors.append(column_header)

        for entry in extracted_entries:
            # Prepare column errors (added only if there are errors)
            column_errors = []

            for header, value in entry.items():
                entry[header] = value.strip()

                if header in ["depth", "mtd"]:
                    try:
                        entry[header] = int(value)
                    except Exception as e:
                        capture_error(e, header, column_errors)

                if header in [
                    "offset",
                    "density",
                    "compaction",
                    "surfTemp",
                    "voids",
                ]:
                    try:
                        entry[header] = float(value)
                    except Exception as e:
                        capture_error(e, header, column_errors)

                if header in ["gpsTime", "dateTime"]:
                    # Adapt to utc string
                    try:
                        entry[header] = entry[header].replace(" ", ", ")
                    except Exception as e:
                        capture_error(e, header, column_errors)

            if column_errors:
                entry["columnErrors"] = column_errors

        return extracted_entries

    def get_data(self):
        data = {}
        with open(self.file_name, "r") as csv_file:
            try:
                csv_reader = csv.reader(csv_file, delimiter=";")
                data["fileInfo"] = next(csv_reader)
                data["headers"] = next(csv_reader)
                data["entries"] = []
            except Exception as e:
                sentry_sdk.capture_exception(e)
            else:
                # Change headers to camelCase
                tmp_headers = [  # Use _ as temp separator
                    header.replace(" ", "_").replace("/", "_").lower()
                    for header in data["headers"]
                ]
                data["headers"] = [to_camel_case(header) for header in tmp_headers]

                for row in csv_reader:
                    entry = {}
                    for header, row_data in zip(data["headers"], row):
                        # Handles the fact that there are two keys with the same name
                        if header == "location":
                            if "location1" in entry:
                                header = "location2"
                            else:
                                header = "location1"

                        entry[header] = row_data

                    data["entries"].append(entry)

                # Change headers to reflect Location1 and Location2 changes
                headers_exc_loc = [
                    header for header in data["headers"] if header != "location"
                ]
                data["headers"] = headers_exc_loc + ["location1", "location2"]

        data["entries"] = self.refine_entries(data["entries"])

        return data

    def get_csv_import(self):
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

        # Download csv
        self.file_name = self.download_csv_file()
        if self.file_name:
            data = self.get_data()

            if data:
                data["groupedBy"] = None
                data = dict_to_casing(data)

                with open(json_file_path, "w") as outfile:
                    json.dump(data, outfile)

                json_file = open(json_file_path, "rb")
                self.csv_import.preview_file.save(
                    json_name, ContentFile(json_file.read())
                )

                has_errors = [
                    error_column
                    for item in data["entries"]
                    for error_column in item.get("columnErrors", [])
                ]
                if not has_errors:
                    error = False

        self.csv_import.error = error

        # Delete temp files
        for file_name in os.listdir(self.temp_path):
            os.remove(self.temp_path + file_name)

        # Delete temporary folder
        os.rmdir(self.temp_path)

        return self.csv_import
