from geojson import Feature, FeatureCollection

# from shapely.geometry import mapping


def create_feature_collection(geometry, properties):
    """
    Create a GeoJSON FeatureCollection from a geometry and properties.

    Parameters:
    - geometry: A Shapely geometry object.
    - properties: Dictionary of properties associated with the geometry.

    Returns:
    - GeoJSON FeatureCollection.
    """
    feature = [
        Feature(
            geometry=a,
            properties=properties[index] if index < len(properties) else {},
        )
        for index, a in enumerate(geometry.geoms)
    ]
    return FeatureCollection(feature)
