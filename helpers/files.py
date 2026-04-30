from time import sleep

from django.core.files import File
from rest_framework.response import Response
from storages.utils import clean_name

from RoadLabsAPI.storage_backends import PrivateMediaStorage


def get_rdo_file_url(obj, field_name="upload"):
    if getattr(obj, field_name, None) is not None:
        storage = PrivateMediaStorage()
        filename = storage.get_available_name(getattr(obj, field_name).name)
        return storage.get_post_url(filename)
    else:
        return {}


def get_url(obj, field_name="upload"):
    try:
        _ = getattr(obj, field_name).size
    except FileNotFoundError:
        storage = PrivateMediaStorage()
        filename = storage.get_available_name(getattr(obj, field_name).name)
        return storage.get_post_url(filename)
    except Exception:
        return {}
    else:
        return {}


def check_endpoint(file_obj, field_name="upload"):
    file_exists = False
    deleted = False
    size = None
    md5 = None
    uuid = file_obj.uuid

    try:
        field = getattr(file_obj, field_name)
    except Exception:
        field = None

    if field:
        for _ in range(5):
            file_exists = field.storage.exists(field.name)
            if file_exists:
                size = field.size
                md5 = field.storage.e_tag(field.name).strip('"')
                break
            sleep(1)

        if not file_exists or not size:
            file_obj._change_reason = (
                "Auto-deleting file on /Check. "
                "Exists was {} and size was {}. E-Tag was {}"
            ).format(file_exists, size, md5)
            deleted = file_obj.delete()[0] > 0

    return Response(
        {
            "type": "FileCheck",
            "attributes": {
                "exists": file_exists,
                "size": size,
                "md5": md5,
                "uuid": uuid,
                "deleted": deleted,
            },
        }
    )


def get_resized_url(file: File, size: int) -> str:
    if size not in [400, 1000]:
        raise ValueError("Size must be either 400 or 1000")

    storage = file.storage
    # Preserve the trailing slash after normalizing the path.
    name = storage._normalize_name(clean_name(file.name))
    expire = storage.querystring_expire
    params = {}

    params["Bucket"] = storage.bucket.name + f"-{size}px"
    params["Key"] = name

    connection = (
        storage.connection if storage.querystring_auth else storage.unsigned_connection
    )
    url = connection.meta.client.generate_presigned_url(
        "get_object", Params=params, ExpiresIn=expire, HttpMethod=None
    )
    return url
