import jwt
from django.apps import apps
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from rest_framework import exceptions
from rest_framework.utils.encoders import JSONEncoder
from rest_framework_jwt.authentication import JSONWebTokenAuthentication
from rest_framework_jwt.blacklist.exceptions import MissingToken
from rest_framework_jwt.compat import ExpiredSignature, jwt_version
from rest_framework_jwt.settings import api_settings
from rest_framework_jwt.utils import jwt_create_payload


def jwt_get_secret_key(user_model):
    return user_model.jwt_secret


def payload_handler(user, type_access="all"):
    payload = jwt_create_payload(user)
    payload["type_access"] = type_access
    return payload


def custom_jwt_get_secret_key(payload=None, db_alias="default"):
    """
    For enhanced security you may want to use a secret key based on user.
    This way you have an option to logout only this user if:
        - token is compromised
        - password is changed
        - etc.
    """
    if api_settings.JWT_GET_USER_SECRET_KEY:
        User = get_user_model()  # noqa: N806
        user = User.objects.using(db_alias).get(pk=payload.get("user_id"))
        key = str(api_settings.JWT_GET_USER_SECRET_KEY(user))
        return key
    return api_settings.JWT_SECRET_KEY


def custom_encode_handler(payload, db_alias):
    """Encode JWT token claims."""

    headers = None

    signing_algorithm = api_settings.JWT_ALGORITHM
    if isinstance(signing_algorithm, list):
        signing_algorithm = signing_algorithm[0]
    if signing_algorithm.startswith("HS"):
        key = custom_jwt_get_secret_key(payload, db_alias)
    else:
        key = api_settings.JWT_PRIVATE_KEY

    if isinstance(key, dict):
        kid, key = next(iter(key.items()))
        headers = {"kid": kid}
    elif isinstance(key, list):
        key = key[0]

    enc = jwt.encode(
        payload, key, signing_algorithm, headers=headers, json_encoder=JSONEncoder
    )
    if jwt_version == 1:
        enc = enc.decode()
    return enc


class CustomTokenAuthentication(JSONWebTokenAuthentication):
    """
    Custom Token based authentication using the JSON Web Token standard and type_access
    """

    def authenticate(self, request):
        """
        Returns a two-tuple of `User` and token if a valid signature has been
        supplied using JWT-based authentication.  Otherwise returns `None`.

        Modified way to get jwt value, because now we will use in GET requests
        """
        try:
            token = self.get_token_from_request(request)
            if token is None:
                return None
        except MissingToken:
            return None

        try:
            payload = self.jwt_decode_token(token)
        except ExpiredSignature:
            msg = _("Token has expired.")
            raise exceptions.AuthenticationFailed(msg)
        except jwt.DecodeError:
            msg = _("Error decoding token.")
            raise exceptions.AuthenticationFailed(msg)
        except jwt.InvalidTokenError:
            msg = _("Invalid token.")
            raise exceptions.AuthenticationFailed(msg)

        if apps.is_installed("rest_framework_jwt.blacklist"):
            from rest_framework_jwt.blacklist.models import BlacklistedToken

            if BlacklistedToken.is_blocked(token, payload):
                msg = _("Token is blacklisted.")
                raise exceptions.PermissionDenied(msg)

        # Return error if not valid type
        if "type_access" in payload:
            try:
                authentication_types = request.parser_context[
                    "view"
                ].authentication_types
            except Exception:
                if payload["type_access"] != "all":
                    msg = _("Type not specified.")
                    raise exceptions.AuthenticationFailed(msg)
            else:
                if payload["type_access"] not in authentication_types:
                    raise exceptions.AuthenticationFailed(msg)

        user = self.authenticate_credentials(payload)
        if user.auth_error:
            raise exceptions.PermissionDenied(detail=user.auth_error)

        return user, token
