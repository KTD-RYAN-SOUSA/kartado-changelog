from typing import List

from pyproj import Proj, transform
from shapely.geometry import GeometryCollection, Point, shape


def calculate_utm_zone_and_hemisphere(latitude, longitude):
    utm_zone = int((longitude + 180) / 6) + 1
    hemisphere = "N" if latitude >= 0 else "S"
    return utm_zone, hemisphere


def convert_geometry_to_utm(geometry):
    # Get the centroid of the geometry
    centroid = geometry.centroid

    # Calculate the average UTM zone and hemisphere for the centroid
    utm_zone, hemisphere = calculate_utm_zone_and_hemisphere(centroid.y, centroid.x)

    # Define the coordinate system for WGS 84 (latitude/longitude)
    epsg = "epsg:4326"
    lat_lon_proj = Proj(init=epsg)

    # Define the coordinate system for UTM with units in meters
    utm_proj = Proj(
        proj="utm",
        zone=utm_zone,
        ellps="WGS84",
        datum="WGS84",
        units="m",
        south=True if hemisphere == "S" else False,
    )

    # Transform each geometry in the GeometryCollection from UTM to latitude/longitude
    geometries_utm = []
    zone = str(utm_zone) + hemisphere
    for feature in geometry.geoms:
        # Transform to UTM
        geometry_utm = transform(
            lat_lon_proj, utm_proj, feature.centroid.y, feature.centroid.x
        )

        coords_meters = list(geometry_utm)
        geometries_utm.append(coords_meters)

    return geometries_utm, zone


def check_max_distance(geometry_collection, reference_point, max_distance=0.01):
    # Filtering nearby coordinates

    return len(
        [
            geom
            for geom in geometry_collection.geoms
            if geom.distance(reference_point) <= max_distance
        ]
    ) == len(geometry_collection)


def filter_max_distance(
    geometry_collection: GeometryCollection,
    reference_point: Point,
    max_distance: float = 0.005,
) -> GeometryCollection:
    """
    Filters a collection of geometries based on their distance from a reference point.

    Args:
        geometry_collection (GeometryCollection): A collection of geometries to filter.
        reference_point (Point): The reference point to calculate distances from.
        max_distance (float, optional): The maximum distance a geometry can be from the reference point to be included in the output. Defaults to 0.01.

    Returns:
        GeometryCollection: A collection of geometries that are within the specified maximum distance from the reference point.
    """

    if not geometry_collection:
        return GeometryCollection([])

    nearby_coordinates = [
        geom
        for geom in geometry_collection.geoms
        if geom.distance(reference_point) <= max_distance
    ]
    return GeometryCollection(
        [shape(coordinates) for coordinates in nearby_coordinates]
    )


def find_equal_features_array(
    old_geometry_collection: GeometryCollection,
    new_geometry_collection: GeometryCollection,
) -> List[int]:
    features_diff = []

    if not old_geometry_collection or not new_geometry_collection:
        return features_diff

    # Percorre as geometrias da primeira coleção
    for index, new in enumerate(old_geometry_collection.geoms):
        # Verifica se a geometria da primeira coleção está presente na segunda
        if new in new_geometry_collection.geoms:
            features_diff.append(index)

    return features_diff
