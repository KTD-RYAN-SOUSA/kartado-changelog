import logging
import time
from tempfile import NamedTemporaryFile
from typing import Dict, List
from uuid import uuid4

import boto3
import requests
from django.conf import settings
from django.template.loader import render_to_string
from geojson import FeatureCollection
from rest_framework import status

from apps.reportings.helpers.get.history import get_reporting_history
from apps.reportings.models import Reporting
from helpers.apps.record_filter import get_context_in_form_data_to_reports
from helpers.files import get_resized_url
from helpers.strings import (
    MAPS_MONTHS_ENG_TO_PT_SHORT,
    deep_keys_to_snake_case,
    get_obj_from_path,
)
from RoadLabsAPI.settings import credentials


class PDFGeneratorBase:
    """
    Base class for generating PDF Reportings from Reporting data using HTML templates and S3 storage.

    This class handles the conversion of Reporting objects to PDF documents by processing
    context data, rendering templates, and managing file storage.

    Attributes:
        template_name (str): Name of the HTML template to use
        reporting (Reporting): The Reporting instance to generate PDF from
        form_fields (dict): Form fields from the Reporting's OccurrenceType
        company (Company): Company instance from the Reporting
        form_data (dict): form_data from the Reporting
        html_string (str): Generated HTML content
        context (dict): Template context data

    Methods:
        __init__(request, reporting: Reporting, template_name: str, *args, **kwargs):
            Initializes generator with required data.

        get_context():
            Gathers template context including:
            - Company and Reporting information
            - Formatted dates
            - Image data
            - Form fields and data
            - Inventory data
            - Approval history
            - Custom options from company configuration

        get_image_data():
            Processes ReportingFiles for PDF including:
            - Image descriptions
            - Dates
            - Resized URLs
            - Position information

        build_pdf(pdf_file_path=None):
            Generates PDF by:
            1. Rendering HTML template
            2. Uploading HTML/CSS to S3
            3. Calling conversion service
            4. Returns presigned S3 URL

    Notes:
        - Uses external HTML-to-PDF conversion service
        - Requires AWS credentials and bucket configuration
        - Handles image resizing and formatting
        - Supports company-specific customization
        - Includes error handling and logging
        - Manages temporary file creation
    """

    def __init__(
        self,
        request,
        reporting: Reporting,
        template_name: str,
        *args,
        **kwargs,
    ) -> None:
        self.template_name: str = template_name
        self.reporting = reporting
        self.form_fields = self._set_form_fields()
        self.company = reporting.company
        self.form_data: dict = reporting.form_data
        self.html_string = ""
        self.context = {"request": request}

    def _set_form_fields(self):

        form_fields = {}
        if getattr(self.reporting, "occurrence_type"):
            occ_type = self.reporting.occurrence_type
            form_fields = deep_keys_to_snake_case(occ_type.form_fields)

        return form_fields

    def get_image_data(self):
        image_data = []
        total_images = self.reporting.reporting_files.count()  # Total number of images
        if not total_images:
            return image_data
        all_images = self.reporting.reporting_files.all()

        for index, file in enumerate(all_images):
            file_extension = file.upload.name.split(".")[-1].lower()
            if file_extension not in ["jpg", "jpeg", "png"]:
                continue

            if file_extension == "jpeg":
                file_extension = "jpg"

            this_image_data = {
                "description": file.description,
                "date": file.datetime,
                "img_data": get_resized_url(file.upload, 1000),
                "is_last": index == total_images - 1,
            }
            image_data.append(this_image_data)

        return image_data

    def get_context(self):
        def format_date(date, month_map):
            if date is None:
                return ""
            month_short = month_map[date.strftime("%B")]
            return date.strftime(f"%d/{month_short}/%Y")

        found_at = self.reporting.found_at
        found_at_date_formatting_short = format_date(
            found_at, MAPS_MONTHS_ENG_TO_PT_SHORT
        )

        due_at = self.reporting.due_at
        due_at_date_formatting_short = format_date(due_at, MAPS_MONTHS_ENG_TO_PT_SHORT)

        executed_at = self.reporting.executed_at
        executed_at_date_formatting_short = format_date(
            executed_at, MAPS_MONTHS_ENG_TO_PT_SHORT
        )

        def find_name_by_value(value, custom_options_list):
            for item in custom_options_list:
                if item["value"] == value:
                    return item["name"]
            return ""

        occurrence_kind_value = get_obj_from_path(
            self.company.custom_options,
            "occurrencetype__fields__occurrencekind__selectoptions__options",
        )
        direction_value = get_obj_from_path(
            self.company.custom_options,
            "reporting__fields__direction__selectoptions__options",
        )
        lane_value = get_obj_from_path(
            self.company.custom_options,
            "reporting__fields__lane__selectoptions__options",
        )
        lot_value = get_obj_from_path(
            self.company.custom_options,
            "reporting__fields__lot__selectoptions__options",
        )

        pdf_reporting_right_margin = get_obj_from_path(
            self.company.custom_options,
            "reporting__pdfReporting__pdfReportingRightMargin",
        )
        footer_title = get_obj_from_path(
            self.company.custom_options,
            "reporting__pdfReporting__footerTitle",
        )
        footer_subtitle = get_obj_from_path(
            self.company.custom_options,
            "reporting__pdfReporting__footerSubtitle",
        )
        hide_reporting_location = get_obj_from_path(
            self.company.metadata, "hidereportinglocation"
        )

        road_can_view = False
        request = self.context.get("request")
        if request and hasattr(request, "permissions_manager"):
            road_can_view = request.permissions_manager.has_permission("can_view")

        if not pdf_reporting_right_margin:
            pdf_reporting_right_margin = ""
        if not footer_title:
            footer_title = ""
        if not footer_subtitle:
            footer_subtitle = ""

        self.context.update(
            {
                "company": self.company,
                "occurrence": self.reporting,
                "firm": self.reporting.firm,
                "subcompany": self.reporting.firm.subcompany,
                "found_at": found_at_date_formatting_short,
                "due_at": due_at_date_formatting_short,
                "executed_at": executed_at_date_formatting_short,
                "number": self.reporting.number,
                "road_name": self.reporting.road_name,
                "km": self.reporting.km,
                "end_km": self.reporting.end_km,
                "lane": find_name_by_value(self.reporting.lane, lane_value),
                "direction": find_name_by_value(
                    self.reporting.direction, direction_value
                ),
                "lot": find_name_by_value(self.reporting.lot, lot_value),
                "kind": find_name_by_value(
                    self.reporting.occurrence_type.occurrence_kind,
                    occurrence_kind_value,
                ),
                "occurrence_type": self.reporting.occurrence_type,
                "status": self.reporting.status,
                "approval_step": self.reporting.approval_step,
                "images": self.get_image_data(),
                "pdf_reporting_right_margin": pdf_reporting_right_margin,
                "footer_title": footer_title,
                "footer_subtitle": footer_subtitle,
                "hide_reporting_location": hide_reporting_location,
                "road_can_view": road_can_view,
            }
        )

        inventory = self.reporting.get_inventory()

        if inventory:
            inventory_created_at_date_formatting_short = ""
            if inventory.created_at:
                inventory_created_at = inventory.created_at
                inventory_created_at_date_formatting_short = format_date(
                    inventory_created_at, MAPS_MONTHS_ENG_TO_PT_SHORT
                )

            self.context.update(
                {
                    "has_inventory": True,
                    "inventory_number": inventory.number or "",
                    "inventory_road_name": inventory.road_name or "",
                    "inventory_km": inventory.km or "",
                    "inventory_project_km": inventory.project_km or "",
                    "inventory_occurrence_type": inventory.occurrence_type.name or "",
                    "inventory_direction": find_name_by_value(
                        inventory.direction, direction_value
                    ),
                    "inventory_lane": find_name_by_value(inventory.lane, lane_value),
                    "inventory_created_at": inventory_created_at_date_formatting_short,
                }
            )

        approval_hist = self.get_approval_hist()
        if approval_hist:
            self.context.update(
                {
                    "approved_by": approval_hist.history_user,
                    "approved_date": approval_hist.history_date,
                }
            )

        self.context.update({"form_fields": self.form_fields})

        if self.form_fields and self.reporting.form_data:
            self.context.update(
                get_context_in_form_data_to_reports(
                    self.get_form_data(), self.form_fields
                )
            )

        return self.context

    def get_approval_hist(self):
        return get_reporting_history(self.reporting)

    def get_form_data(self) -> dict:
        return self.reporting.form_data

    def get_html_string(self) -> str:
        html_string = render_to_string(self.template_name, self.context)
        self.html_string = html_string
        return html_string

    def get_style_css(self) -> str:
        return ""

    def build_pdf(self, pdf_file_path=None):
        if not self.context:
            self.get_context()

        self.get_html_string()

        s3 = boto3.client(
            "s3",
            aws_access_key_id=credentials.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=credentials.AWS_SECRET_ACCESS_KEY,
            aws_session_token=credentials.AWS_SESSION_TOKEN,
        )

        pdf_task_uuid = str(uuid4())

        html_file_name = "input/" + pdf_task_uuid + ".html"
        html_file = NamedTemporaryFile(delete=False, suffix=".html")
        html_file.write(self.html_string.encode())
        html_file.close()

        s3.upload_file(html_file.name, settings.HTML_TO_PDF_BUCKET_NAME, html_file_name)

        css_file_name = "input/" + pdf_task_uuid + ".css"
        css_file = NamedTemporaryFile(delete=False, suffix=".css")
        css_file.write(self.get_style_css().encode())
        css_file.close()

        s3.upload_file(css_file.name, settings.HTML_TO_PDF_BUCKET_NAME, css_file_name)

        pdf_file_name = "output/" + pdf_task_uuid + ".pdf"

        headers = {
            "Authorization": credentials.HTMLTOPDF_API_KEY,
            "Content-Type": "application/json",
        }

        body = {
            "html_path": html_file_name,
            "css_path": css_file_name,
            "pdf_path": pdf_file_name,
        }

        try:
            request = requests.post(
                url=settings.HTML_TO_PDF_API_URL,
                json=body,
                headers=headers,
            )

        except Exception as e:
            logging.error("Exception calling html to pdf API", e)
            return None

        success = False

        if request.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
            for _ in range(30):
                try:
                    s3.head_object(
                        Bucket=settings.HTML_TO_PDF_BUCKET_NAME, Key=pdf_file_name
                    )
                except Exception as e:
                    print(e)
                    time.sleep(1)
                else:
                    success = True
                    output_path = pdf_file_name
                    break

        elif request.status_code == status.HTTP_200_OK:
            response = request.json()

            output_path = response["out_path"]
            success = True

        if success:
            presigned_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.HTML_TO_PDF_BUCKET_NAME, "Key": output_path},
                ExpiresIn=3600,
            )
            return presigned_url

        logging.error("Erro ao gerar o PDF Reporting")

        return None


class PDFGenericGenerator(PDFGeneratorBase):
    """
    Generic PDF generator for Reportings that extends PDFGeneratorBase with additional customization.

    This class adds support for custom headers, extra lines adjustments and map configurations
    when generating PDFs from Reportings.

    Args:
        request: The HTTP request object
        reporting (Reporting): The reporting instance to generate PDF from
        template_name (str): Name of the HTML template to use
        pdf_config (Dict): Configuration dictionary for PDF generation including:
            - map_settings: Map visualization settings
            - extra_lines: Number of extra lines to add
            - custom_headers: Additional HTTP headers

    Attributes:
        headers (dict): Default headers for HTTP requests

    Methods:
        get_html_string():
            Overrides base method to add margin and position adjustments based on extra lines.
            Returns modified HTML string with adjusted margins.

        get_response(payload):
            Makes HTTP POST request to static map service.
            Args:
                payload: Request payload data
            Returns:
                requests.Response: Response from map service

        merge_features(main_feature_collection, seconds_feature_collection):
            Merges multiple GeoJSON feature collections.
            Args:
                main_feature_collection (FeatureCollection): Primary feature collection
                seconds_feature_collection (List[FeatureCollection]): Additional collections
            Returns:
                FeatureCollection: Combined feature collection

    Notes:
        - Handles authentication with basic auth
        - Supports custom map configurations
        - Adjusts PDF margins and positions dynamically
        - Manages feature collection merging for maps
    """

    def __init__(
        self,
        request,
        reporting: Reporting,
        template_name: str,
        pdf_config: Dict,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(
            request,
            reporting,
            template_name,
            args,
            kwargs,
        )

        self.headers: dict = {
            "Accept": "*/*",
            "Content-Type": "application/vnd.api+json",
            "Authorization": "Basic ZW5naWU6ZXNzYVNlbmhhRGFFbmdpZVByZTIwMjM=",
        }

    def get_html_string(self):
        html_string = super().get_html_string()
        extra_lines = 0

        html_string = html_string.replace(
            "margin: 42mm 16mm 45mm 16mm;",
            "margin: {}mm 16mm 45mm 16mm;".format(42 + extra_lines * 9),
        )
        html_string = html_string.replace(
            "top: -78pt;", "top: -{}pt;".format(78 + extra_lines * 36)
        )

        self.html_string = html_string

        return self.html_string

    def get_response(self, payload) -> requests.Response:
        return requests.post(
            "https://staticmap.kartado.com.br/",
            data=payload,
            headers=self.headers,
        )

    def merge_features(
        self,
        main_feature_collection: FeatureCollection,
        seconds_feature_collection: List[FeatureCollection],
    ) -> FeatureCollection:
        combined_feature_collection = {}
        for index, second in enumerate(seconds_feature_collection):
            if index == 0:
                combined_geometry_collection = (
                    second["features"] + main_feature_collection["features"]
                )
            else:
                combined_geometry_collection = (
                    second["features"] + combined_feature_collection["features"]
                )

            combined_feature_collection = {
                "type": "FeatureCollection",
                "features": combined_geometry_collection,
            }

        return combined_feature_collection
