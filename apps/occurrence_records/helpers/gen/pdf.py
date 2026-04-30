import base64
import json
import logging
import math
import re
import time
from tempfile import NamedTemporaryFile
from typing import Dict, List, Tuple, Union
from uuid import uuid4

import boto3
import requests
from django.conf import settings
from django.db.models import Q
from django.template.loader import render_to_string
from geojson import FeatureCollection
from rest_framework import status
from shapely.geometry import GeometryCollection, Point, shape

from apps.maps.models import ShapeFile, TileLayer
from apps.occurrence_records.helpers.apis.service_map.build_data import (
    get_data_service_map,
)
from apps.occurrence_records.helpers.get.history import get_record_history
from apps.occurrence_records.models import OccurrenceRecord
from helpers.apps.record_filter import (
    get_context_in_form_data_to_reports,
    get_context_in_involved_parts_to_reports,
    settings_fields_in_context,
)
from helpers.files import get_resized_url
from helpers.gen.color import get_random_color_hex
from helpers.geon.const import BASE_MAP_NAME
from helpers.geon.feature_collection import create_feature_collection
from helpers.geon.lat_lon import (
    convert_geometry_to_utm,
    filter_max_distance,
    find_equal_features_array,
)
from helpers.strings import (
    DAY_WEEK,
    MAPS_MONTHS_ENG_TO_PT,
    MAPS_MONTHS_ENG_TO_PT_SHORT,
    TRANSLATE_TYPE,
    UF_CODE,
    deep_keys_to_snake_case,
    keys_to_snake_case,
    to_snake_case,
)
from RoadLabsAPI.settings import credentials


class PDFGeneratorBase:
    def __init__(
        self,
        request,
        occurrence_record: OccurrenceRecord,
        template_name: str,
        *args,
        **kwargs,
    ) -> None:
        self.template_name: str = template_name
        self.occurrence_record = occurrence_record
        self.form_fields = self._set_form_fields()
        self.company = occurrence_record.company
        self.form_data: dict = occurrence_record.form_data
        self.html_string = ""
        self.context = {"request": request}

    def _set_form_fields(self):

        form_fields = {}
        if getattr(self.occurrence_record, "occurrence_type"):
            occ_type = self.occurrence_record.occurrence_type
            form_fields = deep_keys_to_snake_case(occ_type.form_fields)

        return form_fields

    def get_image_data(self):
        image_data = []
        total_images = self.occurrence_record.file.count()  # Total number of images
        if not total_images:
            return image_data
        all_images = self.occurrence_record.file.all()

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
        occurrence_record_date = self.occurrence_record.datetime
        month_pt = MAPS_MONTHS_ENG_TO_PT[occurrence_record_date.strftime("%B")]
        month_pt_short = MAPS_MONTHS_ENG_TO_PT_SHORT[
            occurrence_record_date.strftime("%B")
        ]
        date_formatting = occurrence_record_date.strftime(f"%d de {month_pt} de %Y")
        date_formatting_short = occurrence_record_date.strftime(
            f"%d/{month_pt_short}/%Y"
        )
        date_with_day_of_the_week = (
            f"{DAY_WEEK[occurrence_record_date.weekday()]}, {date_formatting}"
        )

        self.context.update(
            {
                "company": self.company,
                "occurrence": self.occurrence_record,
                "created": date_formatting_short,
                "now": date_with_day_of_the_week,
                "number": self.occurrence_record.number,
                "firm": self.occurrence_record.firm,
                "images": self.get_image_data(),
            }
        )

        self.context.update({"form_fields": self.form_fields})
        signature_hist = self.get_creator_signature_hist()
        if signature_hist:
            self.context.update(
                {
                    "signature_date": signature_hist.history_date,
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
        levels = self.get_levels()

        self.context.update(levels)

        data_from_form_data = get_context_in_form_data_to_reports(
            self.get_form_data(), self.form_fields
        )
        data_from_involved_parts = get_context_in_involved_parts_to_reports(
            self.get_involved_parts(), self.company.custom_options
        )

        if "generic_fields" in data_from_form_data and data_from_involved_parts:
            data_from_form_data["generic_fields"] += data_from_involved_parts

        self.context.update(data_from_form_data)

        return self.context

    def get_levels(self) -> Dict:
        register_tag = getattr(
            self.occurrence_record.search_tags.filter(level=1).first(), "name", ""
        )
        if not register_tag:
            register_tag = self.occurrence_record.get_occurrence_kind_display()

        type_tag = getattr(
            self.occurrence_record.search_tags.filter(level=2).first(), "name", ""
        )

        nature_tag = getattr(
            self.occurrence_record.search_tags.filter(level=3).first(), "name", ""
        )

        subject_tag = getattr(
            self.occurrence_record.search_tags.filter(level=4).first(), "name", ""
        )
        if not subject_tag:
            subject_tag = self.occurrence_record.occurrence_type.name

        return {
            "register": register_tag,
            "type": type_tag,
            "nature": nature_tag,
            "subject": subject_tag,
        }

    def get_approval_hist(self):
        return get_record_history(self.occurrence_record, "approve")

    def get_creator_signature_hist(self):
        return get_record_history(self.occurrence_record, "sendToApproval")

    def get_form_data(self) -> dict:
        return self.occurrence_record.form_data

    def get_involved_parts(self) -> dict:
        return self.occurrence_record.involved_parts

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
        with html_file as f:
            f.write(self.html_string.encode())
        s3.upload_file(html_file.name, settings.HTML_TO_PDF_BUCKET_NAME, html_file_name)

        css_file_name = "input/" + pdf_task_uuid + ".css"
        css_file = NamedTemporaryFile(delete=False, suffix=".css")
        with css_file as f:
            f.write(self.get_style_css().encode())
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
                url=settings.HTML_TO_PDF_API_URL, json=body, headers=headers
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

            pdf_file = NamedTemporaryFile(delete=False, suffix=".pdf")
            with pdf_file as f:
                s3.download_fileobj(settings.HTML_TO_PDF_BUCKET_NAME, output_path, f)

            file_bytes = None

            with open(pdf_file.name, "rb") as f:
                file_bytes = f.read()

            return file_bytes

        logging.error("Timeout calling html to pdf API")

        return None


class PDFGeneratorWrittenNotification(PDFGeneratorBase):
    """
    A utility class for generating PDFs of written notifications based on provided template and context data.
    """

    def get_html_string(self):
        html_string = super().get_html_string()
        ref_pattern = r'<div class="header-text-ref">(.*?)</div>'
        ref_matches = re.findall(ref_pattern, html_string, re.DOTALL)
        ref_top_char_count = len(ref_matches[0])

        ref_lines = math.ceil(ref_top_char_count / 110)

        html_string = html_string.replace(
            "margin: 42mm 16mm 45mm 16mm;",
            "margin: {}mm 16mm 45mm 16mm;".format(60 + ref_lines * 9),
        )
        html_string = html_string.replace(
            "top: -78pt;", "top:-{}pt;".format(130 + ref_lines * 36)
        )

        self.html_string = html_string

        return self.html_string

    def get_context(self):
        context = super().get_context()
        context.update({"is_written_notification": True})
        context = settings_fields_in_context(context)
        self.context = context

        return context

    def get_style_css(self):
        return """
            @font-face {
                font-family: Roboto;
                src: url(http://fonts.gstatic.com/s/roboto/v15/W5F8_SL0XFawnjxHGsZjJA.ttf);
            }
        """


class PDFGenericGenerator(PDFGeneratorBase):
    def __init__(
        self,
        request,
        occurrence_record: OccurrenceRecord,
        template_name: str,
        pdf_config: Dict,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(
            request,
            occurrence_record,
            template_name,
            args,
            kwargs,
        )

        self.map_settings: list = pdf_config.get("map_settings", [])
        self.headers: dict = {
            "Accept": "*/*",
            "Content-Type": "application/vnd.api+json",
            "Authorization": "Basic ZW5naWU6ZXNzYVNlbmhhRGFFbmdpZVByZTIwMjM=",
        }
        self.property_intersections: list = []
        self.occurrence_feature_collection: FeatureCollection = None
        self.properties_feature_collection: FeatureCollection = None
        self.shape_file_feature_collections: Dict[str, FeatureCollection] = {}
        self.is_main_property: bool = False
        self.color_to_properties: str = ""

        # maps
        self.includes__is_occurrence_record: bool = True
        self.includes__is_properties: bool = False
        self.includes__is_shape_file: bool = False
        self.includes__active_shape_file: list = []

        # focus

        self.focus__is_properties: bool = False
        self.options__map__color__properties_default_color: str = "#fdd835"
        self.options__map__color__background_color_properties: str = "#00000000"
        self.options__legends__map__is_extra_coordinates: bool = False
        self.options__legends__properties__is_color: bool = False
        self.options__legends__map__coordinates_in_meters: bool = True
        self.options__legends__map__is_properties_coordinates: bool = False
        self.__maps: list = []
        self.__legend_property_intersections: list = []
        self.__legend_map: list = []
        self.__occurrence_geometry_collection: GeometryCollection = None
        self.__color_user: List[str] = [
            self.options__map__color__properties_default_color
        ]

        self.reference_point: Point = None
        self.__max_distance: float = 0.012
        self.__city = occurrence_record.city
        self.__tile_layers: TileLayer = None
        self.__transparent_color: str = "#00000000"
        self.__payloads: list = []
        self.__combined_feature_collection: list = []
        self.__properties_property: list = []

        self.__index__setting: int = 0

        self.__configure_settings(pdf_config)

    def get_html_string(self):
        html_string = super().get_html_string()
        extra_lines = 0
        for line_content in ["title", "subject"]:
            if self.context[line_content]:
                extra_lines += 1

        html_string = html_string.replace(
            "margin: 42mm 16mm 45mm 16mm;",
            "margin: {}mm 16mm 45mm 16mm;".format(42 + extra_lines * 9),
        )
        html_string = html_string.replace(
            "top: -78pt;", "top: -{}pt;".format(78 + extra_lines * 36)
        )

        self.html_string = html_string

        return self.html_string

    def __configure_settings(self, settings, prefix=""):
        for key, value in settings.items():
            key = to_snake_case(key)
            if isinstance(value, dict):
                self.__configure_settings(value, f"{prefix}{key}__")
            elif key != "map_settings":
                if hasattr(self, f"{prefix}{key}"):
                    setattr(self, f"{prefix}{key}", value)

    def __set_settings_map(self):
        if len(self.map_settings) > 0:
            self.__configure_map(self.get_map_settings())

    def __configure_map(self, settings, prefix=""):
        for key, value in settings.items():
            key = to_snake_case(key)
            if isinstance(value, dict):
                self.__configure_map(value, f"{prefix}{key}__")
            elif key == "map":
                self.set_tile_layers(
                    self.company.tile_layers.filter(name=BASE_MAP_NAME[value]).first()
                )
            elif hasattr(self, f"{prefix}{key}"):
                setattr(self, f"{prefix}{key}", value)

    def __set_reference_point(self) -> None:
        if self.includes__is_shape_file or self.includes__is_properties:
            self.reference_point = Point(
                self.__occurrence_geometry_collection.centroid.x,
                self.__occurrence_geometry_collection.centroid.y,
            )

    def __set_legends_properties(self) -> None:
        is_main = self.is_main_property
        properties = self.__properties_property
        for index, _property in enumerate(properties):
            attr = keys_to_snake_case(
                self.property_intersections[index].get("attributes", None)
            )
            if attr is not None:
                self.__legend_property_intersections.append(
                    {
                        "color": _property.get(
                            "color", self.options__map__color__properties_default_color
                        ),
                        "construction": attr.get("obra", ""),
                        "sequential": attr.get("sequencial", ""),
                        "Identifier": attr.get("identificador", ""),
                    }
                )
                if is_main:
                    break

    def __set_properties_property(
        self,
        properties_new_geometry_collection,
        properties_geometry_collection,
    ) -> list:
        properties = []
        label = self.company.metadata.get("properties_label", "Propriedade")

        index_properties = find_equal_features_array(
            properties_geometry_collection,
            properties_new_geometry_collection,
        )

        for _ in index_properties:
            color = self.get_color_to_properties()

            fit_bounds = self.focus__is_properties
            _property = {
                "color": color,
                "stroke": color,
                "fill": self.options__map__color__background_color_properties,
                "fitBounds": fit_bounds,
                "label": label,
            }
            properties.append(_property)

        if self.includes__is_properties:
            self.__properties_property = properties

        return properties

    def __set_properties_occurrence_record(self, obj: OccurrenceRecord) -> List:
        properties = []

        fit_bounds = True
        for index in range(len(obj.properties)):
            _property = {}
            color = (
                self.get_possible_color_in_property(obj.properties[index])
                if self.includes__is_occurrence_record
                else self.__transparent_color
            )
            collection = self.__occurrence_geometry_collection.geoms
            label = (
                obj.properties[index].get("label")
                if obj.properties[index].get("label", None)
                else TRANSLATE_TYPE[collection[index].type]
            )
            _property = {
                "color": color,
                "stroke": color,
                "mark-color": color,
                "fill": color,
                "fitBounds": fit_bounds,
                "label": label,
            }
            obj.properties[index].update(_property)

            properties.append(_property)

        return properties

    def __set_properties_shape_file(
        self, obj: ShapeFile, list_index: List[int] = None
    ) -> list:
        fill = obj.metadata.get("fill_color", self.get_color())
        stroke = obj.metadata.get("stroke_color", self.get_color())
        fit_bounds = False
        label = obj.name

        return list(
            map(
                lambda x: {
                    "stroke": stroke,
                    "mark-color": stroke,
                    "fill": fill,
                    "fitBounds": fit_bounds,
                    "label": label,
                },
                list_index,
            )
        )

    def __set_payload(self, obj: FeatureCollection) -> str:
        return get_data_service_map(obj, self.__tile_layers)

    def __set_maps(self, image: base64) -> None:
        self.__maps.append(base64.b64encode(image).decode("utf-8"))

    def get_uf(self):
        return UF_CODE[str(self.__city.uf_code)] if self.__city else None

    def set_tile_layers(self, object: TileLayer) -> None:
        if object is None:
            raise ValueError("kartado.errors.set_pdf.tile_layer_not_found")
        self.__tile_layers = object

    def get_response(self, payload) -> requests.Response:
        return requests.post(
            "https://staticmap.kartado.com.br/",
            data=payload,
            headers=self.headers,
        )

    def get_map_settings(self) -> dict:
        index = self.__index__setting
        return self.map_settings[index]

    def get_color_to_properties(self):
        if self.color_to_properties:
            return self.color_to_properties
        color = (
            self.get_color()
            if self.options__map__color__properties_default_color == "auto"
            else self.options__map__color__properties_default_color
        )
        self.color_to_properties = color
        return color

    def get_coordinates_and_zone(self, obj: GeometryCollection) -> Tuple[List, str]:
        coordinates, zone = convert_geometry_to_utm(obj)
        if not self.options__legends__map__coordinates_in_meters:
            coordinates = [
                [
                    geometry.centroid.x,
                    geometry.centroid.y,
                ]
                for geometry in obj.geoms
            ]
        return (coordinates, zone)

    def get_color(self):
        color = get_random_color_hex()
        while color in self.__color_user:
            color = get_random_color_hex()

        self.__color_user.append(color)
        return color

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

    def get_possible_color_in_property(self, property: dict) -> str:
        if property.get("fill", None):
            color = property.get("fill")
            self.__color_user.append(color[:3])
        elif property.get("stroke", None):
            color = property.get("stroke")
            self.__color_user.append(color[:3])
        elif property.get("marker-color", None):
            color = property.get("marker-color")
            self.__color_user.append(color[:3])
        elif property.get("color", None):
            color = property.get("color")
            self.__color_user.append(color[:3])
        elif property.get("fill-color", None):
            color = property.get("fill-color")
        elif property.get("stroke_color", None):
            color = property.get("stroke_color")
            self.__color_user.append(color[:3])
        else:
            color = self.get_color()
            self.__color_user.append(color[:3])
        return color

    def get_geojson(
        self, obj: dict, key: str = "geometries"
    ) -> Union[GeometryCollection, None]:
        if hasattr(obj, "geometry") and hasattr(obj.geometry, "geojson"):
            return json.loads(obj.geometry.geojson)

    def geojson_to_geometry_collection(
        self, geojson: dict, key: str = "geometries"
    ) -> Union[GeometryCollection, None]:
        if geojson.get(key, None):
            return GeometryCollection(
                [shape(geometry) for geometry in geojson.get(key)]
            )

    def list_geometries_to_geometry_collection(
        self, geometries: list
    ) -> Union[GeometryCollection, None]:
        if geometries:
            return GeometryCollection([shape(geometry) for geometry in geometries])

    def get_filter_max_distance(
        self, geometry_collection: GeometryCollection
    ) -> GeometryCollection:
        return filter_max_distance(
            geometry_collection, self.reference_point, self.__max_distance
        )

    def get_context(self):
        context = super().get_context()
        is_occurrence_geometry_collection = False
        is_properties_geometry_collection = False
        is_properties_legends = False
        is_shape_file_legends_map = []
        is_occurrence_legend_map = False
        form_data = self.get_form_data()
        company = self.company

        LOCATION_NAME = (
            self.occurrence_record.location.name
            if getattr(self.occurrence_record, "location")
            else ""
        )

        LOCAL = self.occurrence_record.get_place_on_dam_display()
        BOARD_REGISTRATION = self.occurrence_record.created_by.metadata.get(
            "board_registration", ""
        )

        # main occurrence
        occurrence_geojson = self.get_geojson(self.occurrence_record)
        zone_occurrence_record = ""

        maps_grouped = []
        if occurrence_geojson:
            # raise ValueError("kartado.errors.get_pdf.occurrence_record_not_geojson")

            for map_index in range(len(self.map_settings)):
                self.__index__setting = map_index
                self.__set_settings_map()

                if not is_occurrence_geometry_collection:
                    self.__occurrence_geometry_collection = (
                        self.geojson_to_geometry_collection(occurrence_geojson)
                    )

                properties = self.__set_properties_occurrence_record(
                    self.occurrence_record
                )

                if not is_occurrence_geometry_collection:
                    self.__set_reference_point()

                    (
                        coordinates_occurrence_record,
                        zone_occurrence_record,
                    ) = self.get_coordinates_and_zone(
                        self.__occurrence_geometry_collection
                    )

                    if (
                        self.includes__is_occurrence_record
                        and not is_occurrence_legend_map
                    ):
                        for index, _property in enumerate(properties):
                            x = f"{coordinates_occurrence_record[index][0]:.2f}"
                            y = f"{coordinates_occurrence_record[index][1]:.2f}"

                            self.__legend_map.append(
                                {
                                    "color": _property.get("color"),
                                    "label": _property.get("label", ""),
                                    "x": x,
                                    "y": y,
                                    "zone": zone_occurrence_record,
                                }
                            )
                        is_occurrence_legend_map = True

                    is_occurrence_geometry_collection = True

                self.occurrence_feature_collection = create_feature_collection(
                    self.__occurrence_geometry_collection,
                    properties,
                )

                # Properties
                if self.includes__is_properties and is_properties_geometry_collection:
                    self.__combined_feature_collection.append(
                        self.properties_feature_collection
                    )
                elif self.includes__is_properties:
                    self.is_main_property = form_data.get(
                        "shape_file_property_is_specified", None
                    )
                    if self.is_main_property:
                        self.property_intersections = [
                            self.occurrence_record.get_main_property()
                        ]
                    else:
                        self.property_intersections = self.form_data.get(
                            "property_intersections", {}
                        )

                    if self.property_intersections:
                        label_properties = company.metadata.get(
                            "properties_label", "Propriedade"
                        )
                        geometries = []

                        for _property in self.property_intersections:
                            if _property:
                                geometries.append(_property.get("geometry", None))

                        properties_geometry_collection = (
                            self.list_geometries_to_geometry_collection(geometries)
                        )

                        # Filtering nearby coordinates
                        properties_new_geometry_collection = (
                            self.get_filter_max_distance(properties_geometry_collection)
                        )

                        properties_property = self.__set_properties_property(
                            properties_new_geometry_collection,
                            properties_geometry_collection,
                        )

                        self.properties_feature_collection = create_feature_collection(
                            properties_new_geometry_collection, properties_property
                        )

                        is_properties_geometry_collection = True

                        self.__combined_feature_collection.append(
                            self.properties_feature_collection
                        )

                        x = y = zone = "-"

                        if not is_properties_legends:
                            if self.options__legends__map__is_extra_coordinates:
                                (coordinates, zone,) = self.get_coordinates_and_zone(
                                    properties_new_geometry_collection
                                )

                                x = f"{coordinates[0][0]:.2f}"
                                y = f"{coordinates[0][1]:.2f}"

                            self.__legend_map.append(
                                {
                                    "color": self.color_to_properties,
                                    "label": label_properties,
                                    "x": x,
                                    "y": y,
                                    "zone": zone,
                                }
                            )
                            self.__set_legends_properties()
                            is_properties_legends = True

                # Active Shape File
                if self.includes__is_shape_file and self.includes__active_shape_file:
                    shape_file_exclude_pk = (
                        company.metadata.get("properties_shape")
                        if isinstance(
                            company.metadata.get("properties_shape", None), list
                        )
                        else [company.metadata.get("properties_shape", None)]
                    )
                    qs_shape_file = self.occurrence_record.active_shape_files.exclude(
                        Q(pk__in=shape_file_exclude_pk) | Q(geometry__isnull=True)
                    ).filter(pk__in=self.includes__active_shape_file)
                    if qs_shape_file.exists():
                        for shape_file in qs_shape_file:
                            shape_file_pk = str(shape_file.pk)

                            if (
                                shape_file_pk
                                in self.shape_file_feature_collections.keys()
                            ):
                                self.__combined_feature_collection.append(
                                    self.shape_file_feature_collections.get(
                                        shape_file_pk
                                    )
                                )
                            else:
                                shape_geojson = self.get_geojson(shape_file)
                                if shape_geojson:
                                    shape_geometry_collection = (
                                        self.geojson_to_geometry_collection(
                                            shape_geojson
                                        )
                                    )
                                    shape_file_new_geometry_collection = (
                                        self.get_filter_max_distance(
                                            shape_geometry_collection
                                        )
                                    )

                                    index_properties = []
                                    index_properties = find_equal_features_array(
                                        shape_geometry_collection,
                                        shape_file_new_geometry_collection,
                                    )

                                    properties = self.__set_properties_shape_file(
                                        shape_file, index_properties
                                    )

                                    self.shape_file_feature_collections.update(
                                        {
                                            shape_file_pk: create_feature_collection(
                                                shape_file_new_geometry_collection,
                                                properties,
                                            )
                                        }
                                    )

                                    self.__combined_feature_collection.append(
                                        self.shape_file_feature_collections.get(
                                            shape_file_pk
                                        )
                                    )

                                    if properties and (
                                        shape_file_pk not in is_shape_file_legends_map
                                    ):
                                        x = y = zone = "-"

                                        if (
                                            self.options__legends__map__is_extra_coordinates
                                        ):
                                            (
                                                coordinates,
                                                zone,
                                            ) = self.get_coordinates_and_zone(
                                                shape_file_new_geometry_collection
                                            )
                                            x = f"{coordinates[index][0]:.2f}"
                                            y = f"{coordinates[index][1]:.2f}"

                                        self.__legend_map.append(
                                            {
                                                "color": properties[0].get(
                                                    "fill", None
                                                ),
                                                "label": shape_file.name,
                                                "x": x,
                                                "y": y,
                                                "zone": zone,
                                            }
                                        )
                                        is_shape_file_legends_map.append(shape_file_pk)

                if self.includes__is_properties or self.includes__is_shape_file:
                    combination_payload = self.__set_payload(
                        self.merge_features(
                            self.occurrence_feature_collection,
                            self.__combined_feature_collection,
                        )
                    )
                    self.__payloads.append(combination_payload)
                elif self.includes__is_occurrence_record and not (
                    self.includes__is_properties or self.includes__is_shape_file
                ):
                    _payload = self.__set_payload(self.occurrence_feature_collection)
                    self.__payloads.append(_payload)

                self.__combined_feature_collection = []

            payloads = self.__payloads
            for payload in payloads:
                response = self.get_response(payload)

                if response.status_code == 200:
                    image = response.content

                    self.__set_maps(image)

            # Group maps into pairs
            group_size = 2
            for i in range(0, len(self.__maps), group_size):
                maps_grouped.append(self.__maps[i : i + group_size])

        context.update(
            {
                "title": self.occurrence_record.search_tag_description,
                "city": self.__city.name if self.__city else "",
                "UF": self.get_uf() or "",
                "location_name": LOCATION_NAME,
                "board_registration": BOARD_REGISTRATION,
                "occurrence_record_local": LOCAL,
                "offender_name": self.occurrence_record.get_offender_name,
                "legend_map": self.__legend_map,
                "legend_property_intersections": self.__legend_property_intersections,
                "maps": maps_grouped,
                "options__legends__properties__is_color": self.options__legends__properties__is_color,
                "service_orders": self.occurrence_record.service_orders.filter(
                    company=self.company
                ),
            }
        )

        context = settings_fields_in_context(context)
        self.context = context

        return context
