import json

from geojson import FeatureCollection

from apps.maps.models import TileLayer


def get_data_service_map(
    feature_collection: FeatureCollection, tile_layer: TileLayer
) -> str:
    """
    Get the data service map payloads.

    Args:
        feature_collection (FeatureCollection): The feature collection to be sent to the data service.
        tile_layers (object): The tile layer to be sent to the data service.

    Returns:
        list: The data service map payloads.
    """
    send_map = {
        "featureCollection": feature_collection,
        "fitBoundsFilter": "fitBounds",
    }

    title = {
        "tileLayer": {
            "url": tile_layer.provider_info.get("url"),
            "attribution": tile_layer.provider_info.get("attribution"),
            "type": tile_layer.provider_info.get("type"),
            "accessToken": tile_layer.provider_info.get("accessToken", ""),
            "styleString": tile_layer.provider_info.get("styleString", ""),
            "width": 1024,
            "height": 600,
        },
    }

    send_map.update(title)

    return json.dumps(send_map)
