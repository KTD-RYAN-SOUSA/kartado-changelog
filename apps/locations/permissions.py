from helpers.permissions import BaseModelAccessPermissions


class LocationPermissions(BaseModelAccessPermissions):
    model_name = "Location"


class RiverPermissions(BaseModelAccessPermissions):
    model_name = "River"
