from datetime import datetime, timedelta

import requests
from zappa.asynchronous import task

from helpers.fields import FeatureCollectionField

from .models import ShapeFile


@task
def execute_arcgis_sync(shapefile_id):
    shapefile = ShapeFile.objects.get(uuid=shapefile_id)

    base_url = shapefile.metadata["sync"]["url"]
    params = shapefile.metadata["sync"]["params"]

    if "auth" in shapefile.metadata["sync"]:
        url_token = shapefile.metadata["sync"]["auth"]["url"]
        data_token = {
            "username": shapefile.metadata["sync"]["auth"]["username"],
            "password": shapefile.metadata["sync"]["auth"]["password"],
            "client": "referer",
            "referer": "https://gisdes.engieenergia.com.br/portal",
            "expiration": 15,
            "f": "json",
        }
        req_token = requests.post(url_token, data=data_token)

        if "token" in req_token.json():
            params.append({"name": "token", "value": req_token.json()["token"]})
        else:
            return

    request_params = {a["name"]: a["value"] for a in params if a["name"] == "token"}
    request_params["f"] = "pjson"

    req = requests.get(base_url, params=request_params)
    req = req.json()

    shapefile.metadata["arcgis_layer_info"] = req

    request_params = {a["name"]: a["value"] for a in params}
    request_params["returnIdsOnly"] = "true"

    req = requests.get(base_url + "/query", params=request_params)
    req = req.json()
    object_ids = req["objectIds"]

    features = []

    while len(object_ids):
        oids = [str(object_ids.pop()) for _ in range(100) if len(object_ids)]
        request_params = {a["name"]: a["value"] for a in params}
        request_params["objectIds"] = ",".join(oids)
        r = requests.get(base_url + "/query", params=request_params)
        features += r.json()["features"]

    collection = {"type": "FeatureCollection", "features": features}

    field = FeatureCollectionField(
        required=False,
        allow_null=True,
        geometry_field="geometry",
        properties_field="properties",
    )

    internal_values = field.to_internal_value(collection)

    if "translate" in shapefile.metadata["sync"]:
        for item in internal_values["properties"]:
            for key, value in item.items():
                for translate in shapefile.metadata["sync"]["translate"]:
                    if key == translate["field"]:
                        if value in translate["lookup"]:
                            item[key] = translate["lookup"][value]

    shapefile.geometry = internal_values["geometry"]
    shapefile.properties = internal_values["properties"]
    shapefile.synced_at = datetime.now()
    shapefile.metadata["sync"]["params"] = [
        a for a in shapefile.metadata["sync"]["params"] if a["name"] != "token"
    ]
    shapefile.save()

    return


def sync_shape_files():
    for shapefile in ShapeFile.objects.all():
        if "sync" in shapefile.metadata:
            if "interval" in shapefile.metadata["sync"]:
                interval = shapefile.metadata["sync"]["interval"]
                if shapefile.synced_at + timedelta(hours=interval) > datetime.now():
                    continue
            if shapefile.metadata["sync"]["type"] == "arcgis":
                execute_arcgis_sync(str(shapefile.uuid))
