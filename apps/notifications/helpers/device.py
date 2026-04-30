from time import time

from apps.notifications.models import Device


def create_device(push_token, os=""):
    try:
        mobile_device = Device.objects.get(push_token=push_token)
    except Exception as e:
        print("create_device exception!", repr(e))

        mobile_device = Device.objects.create(
            device_id="{}_{}".format(os, str(time())),
            push_token=push_token,
        )

    return mobile_device
