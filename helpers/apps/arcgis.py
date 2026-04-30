import json
from collections import defaultdict

import requests
import sentry_sdk
from django.conf import settings

from apps.maps.models import ShapeFile
from helpers.fields import FeatureCollectionField
from helpers.strings import get_obj_from_path, transform_geo
from RoadLabsAPI.settings import credentials


class ArcGisSync:
    def __init__(self, record, created):
        self.arcgis_ids = {} if created else record.arcgis_ids.copy()
        self.record = record
        self.token_url = credentials.ARCGIS_TOKEN
        self.created = created
        self.map_arcgis_ids = {"0": "point", "1": "path", "2": "ring"}
        self.geometries = {}

        try:
            self.features = FeatureCollectionField(
                "geometry", "properties"
            ).to_representation(record)["features"]
        except Exception:
            self.features = []

    def get_token(self):
        token_data = {
            "username": credentials.ARCGIS_LOGIN,
            "password": credentials.ARCGIS_PWD,
            "client": "referer",
            "referer": credentials.ARCGIS_URL,
            "expiration": "15",
            "f": "json",
        }
        token_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        token_request = requests.post(
            self.token_url, data=token_data, headers=token_headers
        )
        if token_request.status_code == 200:
            return token_request.json()["token"]
        else:
            return False

    def get_attributes(self, geo_type):

        occurrence_kind_options = get_obj_from_path(
            self.record.company.custom_options,
            "occurrencerecord__fields__occurrencekind__selectoptions__options",
        )
        try:
            record_occurrence_kind = next(
                item["name"]
                for item in occurrence_kind_options
                if item["value"] == self.record.occurrence_type.occurrence_kind
            )
        except Exception:
            record_occurrence_kind = ""

        if self.record.city and self.record.location:
            obs = "Município: {}; Localidade: {}.".format(
                self.record.city.name, self.record.location.name
            )
        else:
            obs = self.record.form_data.get("action", "")

        try:
            if "shape_file_property" in self.record.form_data:
                shape_file_id = "-".join(
                    self.record.form_data["shape_file_property"].split("-")[:-1]
                )
                property_id = self.record.form_data["shape_file_property"].split("-")[
                    -1
                ]
                shape_file = ShapeFile.objects.get(uuid=shape_file_id)
                property_object = next(
                    a
                    for a in shape_file.properties
                    if str(a["OBJECTID"]) == property_id
                )
                imovel_id = property_object["IDENTIFICADOR"]
            else:
                imovel_id = ""
        except Exception:
            imovel_id = ""

        try:
            infrator = ""
            if "people" in self.record.form_data:
                names = [
                    a["full_name"]
                    for a in self.record.form_data["people"]
                    if "full_name" in a and "condition" in a and a["condition"] == "1"
                ]
                infrator = ", ".join(names)
            else:
                infrator = ""
        except Exception:
            infrator = ""

        attributes = {
            "rg_id": self.record.number,
            "tipo_rg": self.record.occurrence_type.name
            if self.record.occurrence_type
            else "",
            "tipo_intervencao": record_occurrence_kind,
            "posicao": self.record.firm.name if self.record.firm else "",
            "criador": self.record.created_by.get_full_name()
            if self.record.created_by
            else "",
            "status": self.record.status.name if self.record.status else "",
            "obs": obs,
            "link_hidros": "{}/#/SharedLink/{}/{}/show?company={}".format(
                settings.FRONTEND_URL,
                "OccurrenceRecord",
                str(self.record.uuid),
                str(self.record.company.pk),
            ),
            "imovel_id": imovel_id,
            "infrator": infrator,
        }
        if not self.created:
            geo_type_translation = self.map_arcgis_ids.get(geo_type, False)
            if geo_type_translation:
                objectid = self.record.arcgis_ids.get(geo_type_translation, False)
                if objectid:
                    attributes["objectid"] = objectid

        return attributes

    def get_geometries(self):
        """
        example:
        {
            "points": [[-48.4981, -27.5539], [-48.4982, -27.5839], [-48.4985, -27.5545]],
            "paths": [[[-48.4981, -27.5539], [-48.4982, -27.5839], [-48.4985, -27.5545]]],
            "rings": [[[-48.4981, -27.5539], [-48.4982, -27.5839], [-48.4985, -27.5545], [-48.4981, -27.5539]]],
        }
        """
        geometries_dict = defaultdict(list)
        comprimento = 0
        area = 0
        perimetro = 0
        len_points = 0
        if self.features:
            for item in self.features:
                geometry_type = item.get("geometry", {}).get("type", False)
                coordinates = item.get("geometry", {}).get("coordinates", False)
                if coordinates and geometry_type:
                    if geometry_type == "Point":
                        geometries_dict["points"].append(coordinates)
                        len_points += 1
                    elif geometry_type == "LineString":
                        geometries_dict["paths"].append(coordinates)
                        line = transform_geo(coordinates, line=True)
                        comprimento += line.length
                    elif geometry_type == "Polygon":
                        geometries_dict["rings"].append(coordinates[0])
                        polygon = transform_geo(coordinates[0], polygon=True)
                        perimetro += polygon.length
                        area += polygon.area

        geometries_dict["len_points"] = len_points
        geometries_dict["comprimento"] = comprimento
        geometries_dict["area"] = area
        geometries_dict["perimetro"] = perimetro

        return geometries_dict

    def send_geometry(self, token, geos, geo_type, geo_name):
        features_url = credentials.ARCGIS_FEATURES
        if self.created:
            operation_type = "add"
            features_url += "{}/{}Features".format(geo_type, operation_type)
        else:
            operation_type = ""
            map_geo_type_name = self.map_arcgis_ids.get(geo_type, False)
            if map_geo_type_name:
                map_objectid = self.record.arcgis_ids.get(map_geo_type_name, False)
                if map_objectid:
                    operation_type = "update"
            if not operation_type:
                operation_type = "add"

            features_url += "{}/{}Features".format(geo_type, operation_type)

        geometry = {geo_name: geos, "spatialReference": {"wkid": 4326}}
        attributes = self.get_attributes(geo_type)
        if geo_name == "points":
            attributes["num_pontos"] = self.geometries.get("len_points", 0)
        elif geo_name == "paths":
            attributes["comprimento"] = self.geometries.get("comprimento", 0)
        elif geo_name == "rings":
            attributes["area"] = self.geometries.get("area", 0)
            attributes["perimetro"] = self.geometries.get("perimetro", 0)

        features_data = {
            "features": json.dumps([{"attributes": attributes, "geometry": geometry}]),
            "f": "pjson",
        }

        features_headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            send_geometry_request = requests.post(
                features_url, data=features_data, headers=features_headers
            )

            if send_geometry_request.status_code == 200:
                result_key = operation_type + "Results"
                return send_geometry_request.json()[result_key][0]["objectId"]
            else:
                return False
        except Exception as e:
            sentry_sdk.capture_exception(e)
            return False

    def delete_geometry(self, token, geometry, geo_type):
        delete_url = credentials.ARCGIS_FEATURES
        delete_url += "{}/{}Features".format(geo_type, "delete")

        delete_data = {"objectIds": geometry, "f": "pjson"}

        delete_headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        delete_request = requests.post(
            delete_url, data=delete_data, headers=delete_headers
        )

        if delete_request.status_code == 200:
            return True
        else:
            return False

    def send_requests(self, token, geos, number, name, geo_name):
        if geos:
            obj_id = self.send_geometry(token, geos, number, geo_name)
            if obj_id and name:
                self.arcgis_ids[name] = obj_id
        elif (
            not self.created
            and not geos
            and name
            and name in self.arcgis_ids.keys()
            and self.arcgis_ids[name]
        ):
            geo_deleted = self.delete_geometry(token, self.arcgis_ids[name], number)
            if geo_deleted:
                del self.arcgis_ids[name]
        return

    def process_sync(self):
        token = self.get_token()
        if token:
            self.geometries = self.get_geometries()
            geo_point_name = "points"
            geo_path_name = "paths"
            geo_ring_name = "rings"
            points = self.geometries.get(geo_point_name, False)
            paths = self.geometries.get(geo_path_name, False)
            rings = self.geometries.get(geo_ring_name, False)
            point_number = "0"
            path_number = "1"
            ring_number = "2"
            name_points = self.map_arcgis_ids.get(point_number, False)
            name_paths = self.map_arcgis_ids.get(path_number, False)
            name_rings = self.map_arcgis_ids.get(ring_number, False)

            self.send_requests(token, points, point_number, name_points, geo_point_name)
            self.send_requests(token, paths, path_number, name_paths, geo_path_name)
            self.send_requests(token, rings, ring_number, name_rings, geo_ring_name)

            self.record.arcgis_ids = self.arcgis_ids

        return self.record
