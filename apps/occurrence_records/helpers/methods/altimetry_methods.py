import json

from apps.occurrence_records.helpers.apis.tessadem.functions import get_elevation
from apps.occurrence_records.helpers.get.coordinates import find_min_elevation
from helpers.arrays import is_matrix
from helpers.strings import keys_to_snake_case, to_snake_case


class AltimetryMethods:
    def set_altimetry(self) -> bool:
        """
        Calculate and set additional properties for an occurrence record, including elevation.

        This function processes the geometry of the occurrence record, calculates the elevation
        of geographic coordinates, and updates properties and form data as needed.

        Returns:
            bool: True if the properties were successfully set, False otherwise.
        """
        if not hasattr(self.geometry, "geojson"):
            return False

        list_geometries = []
        list_geometries_clear = []
        geojson = json.loads(self.geometry.geojson)
        list_geometries_complete = geojson.get("geometries", [])

        for geo in list_geometries_complete:
            if geo.get("type") == "Point" and len(geo.get("coordinates", [])) > 1:
                list_geometries_clear.append(geo["coordinates"][:2])

            elif geo.get("type") == "Polygon":
                collection_coordinates = []
                for collections in geo.get("coordinates", []):
                    for coordinates in collections:
                        if len(coordinates) > 2:
                            collection_coordinates.append(coordinates[:2])
                        else:
                            collection_coordinates.append(coordinates)

                if collection_coordinates:
                    list_geometries_clear.extend(collection_coordinates)
            elif geo.get("type") == "LineString":
                collection_coordinates = []
                for coordinates in geo.get("coordinates", []):
                    if len(coordinates) > 2:
                        collection_coordinates.append(coordinates[:2])
                    else:
                        collection_coordinates.append(coordinates)

                if collection_coordinates:
                    list_geometries_clear.extend(collection_coordinates)

            list_geometries.append(geo["coordinates"][:2])

        if not list_geometries_clear:
            return False

        reverse_coordinates = True
        logs_lats_clean = get_elevation(
            list_geometries_clear, self.company, self.created_by, reverse_coordinates
        )
        properties = self.properties
        form_type = self.occurrence_type
        form_data = self.form_data
        building = form_data.get("building", [])

        try:
            primary_buildings = [i["shape_point"] for i in building if i["kind"] == "1"]
        except Exception:
            primary_buildings = []

        min_elevations = []
        if logs_lats_clean:
            for index, elevation_data in enumerate(list_geometries):
                if is_matrix(elevation_data):
                    for sub_elevation_1 in elevation_data:
                        list_elevation = []
                        if is_matrix(sub_elevation_1):
                            for sub_elevation_2 in sub_elevation_1:
                                list_elevation.append(
                                    find_min_elevation(
                                        sub_elevation_2,
                                        logs_lats_clean,
                                        reverse_coordinates,
                                    )
                                )
                        else:
                            list_elevation.append(
                                find_min_elevation(
                                    sub_elevation_1,
                                    logs_lats_clean,
                                    reverse_coordinates,
                                )
                            )

                    elevation = min(list_elevation)
                else:
                    elevation = find_min_elevation(
                        elevation_data, logs_lats_clean, reverse_coordinates
                    )

                try:
                    if (
                        primary_buildings
                        and properties[index]["label"] not in primary_buildings
                    ):
                        pass
                    else:
                        min_elevations.append(elevation)

                    properties[index].update({"elevation_m": elevation})
                except IndexError:
                    if index < len(self.geometry.tuple):
                        properties.append({"elevation_m": elevation})
                    else:
                        break

        field_altimetry_calculated = False

        for field in form_type.form_fields.get("fields", []):
            field = keys_to_snake_case(field)
            if to_snake_case(field.get("api_name", "")) == "altimetry_calculated":
                field_altimetry_calculated = True
                break

        if form_type and field_altimetry_calculated:
            try:
                if self.form_metadata.get("altitude") and not self.form_metadata.get(
                    "altitude"
                ).get("manually_specified"):
                    min_result = min(min_elevations)
                    min_elevation = {
                        "altimetry_calculated": min_result,
                        "altitude": min_result,
                    }
                    form_data.update(min_elevation)
            except Exception as e:
                print(
                    ">>>>>>>>>>>>>>>>>>> if form_type and field_altimetry_calculated:",
                    e,
                )

        self.__class__.objects.filter(pk=self.pk).update(
            properties=properties, form_data=form_data
        )
        return True
