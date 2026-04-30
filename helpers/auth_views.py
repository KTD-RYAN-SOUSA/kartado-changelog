from datetime import datetime, timedelta, timezone

from django.contrib.auth import authenticate
from django.utils.translation import gettext as _
from fnc.mappings import get
from rest_framework import serializers
from rest_framework_jwt.serializers import (
    JSONWebTokenSerializer,
    RefreshAuthTokenSerializer,
)
from rest_framework_jwt.settings import api_settings
from rest_framework_jwt.utils import check_payload, check_user, unix_epoch
from rest_framework_jwt.views import BaseJSONWebTokenAPIView

from helpers.auth import payload_handler as jwt_payload_handler

jwt_encode_handler = api_settings.JWT_ENCODE_HANDLER


def is_mobile(user_agent):
    # making this a function to leave room for future improvement
    return True if "okhttp" in user_agent or "CFNetwork" in user_agent else False


def custom_jwt_payload_handler(user, user_agent):
    payload = jwt_payload_handler(user)

    if is_mobile(user_agent):
        payload["exp"] = datetime.now(timezone.utc) + timedelta(days=30)

    return payload


class CustomJSONWebTokenSerializer(JSONWebTokenSerializer):
    def validate(self, data):
        user_agent = get(
            "context.request._request.META.HTTP_USER_AGENT", self, default=""
        )

        credentials = {
            self.username_field: data.get(self.username_field),
            "password": data.get("password"),
        }

        user = authenticate(self.context["request"], **credentials)

        if not user:
            msg = _("Unable to log in with provided credentials.")
            raise serializers.ValidationError(msg)
        else:
            if not user.is_active:
                msg = _("User account is disabled.")
                raise serializers.ValidationError(msg)

            payload = custom_jwt_payload_handler(user, user_agent)

            db_alias = "default"
            if hasattr(user, "backend") and "Engie" in user.backend:
                db_alias = "engie_prod"
            elif hasattr(user, "backend") and "CCR" in user.backend:
                db_alias = "ccr_prod"

            return {
                "token": jwt_encode_handler(payload, db_alias),
                "user": user,
                "issued_at": payload.get("iat", unix_epoch()),
            }


class CustomRefreshJSONWebTokenSerializer(RefreshAuthTokenSerializer):
    def validate(self, data):
        user_agent = get(
            "context.request._request.META.HTTP_USER_AGENT", self, default=""
        )

        token = data["token"]

        payload = check_payload(token=token)
        user = check_user(payload=payload)

        # Get and check 'orig_iat'
        orig_iat = payload.get("orig_iat")

        if orig_iat is None:
            msg = _("orig_iat field not found in token.")
            raise serializers.ValidationError(msg)

        refresh_limit = api_settings.JWT_REFRESH_EXPIRATION_DELTA.total_seconds()

        expiration_timestamp = orig_iat + refresh_limit
        now_timestamp = unix_epoch()

        if now_timestamp > expiration_timestamp:
            msg = _("Refresh has expired.")
            raise serializers.ValidationError(msg)

        db_alias = "default"
        if hasattr(user, "backend") and "Engie" in user.backend:
            db_alias = "engie_prod"
        elif hasattr(user, "backend") and "CCR" in user.backend:
            db_alias = "ccr_prod"

        new_payload = custom_jwt_payload_handler(user, user_agent)
        new_payload["orig_iat"] = orig_iat

        # Track the token ID of the original token, if it exists
        orig_jti = payload.get("orig_jti") or payload.get("jti")
        if orig_jti:
            new_payload["orig_jti"] = orig_jti
        elif api_settings.JWT_TOKEN_ID == "require":
            msg = _("orig_jti or jti field not found in token.")
            raise serializers.ValidationError(msg)

        return {
            "token": jwt_encode_handler(new_payload, db_alias),
            "user": user,
            "issued_at": new_payload.get("iat", unix_epoch()),
        }


class ObtainJSONWebToken(BaseJSONWebTokenAPIView):
    serializer_class = CustomJSONWebTokenSerializer


class RefreshJSONWebToken(BaseJSONWebTokenAPIView):
    serializer_class = CustomRefreshJSONWebTokenSerializer


custom_obtain_jwt_token = ObtainJSONWebToken.as_view()
custom_refresh_jwt_token = RefreshJSONWebToken.as_view()
