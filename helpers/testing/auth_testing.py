from datetime import timedelta

from django.contrib.auth.signals import user_logged_in
from django.db.models import prefetch_related_objects
from django.utils import timezone
from rest_framework_jwt.settings import api_settings

from apps.users.serializers import AuthUserSerializer


def get_user_token(user, expires=None, type_access="all"):
    # expires need to be a TIMEDELTA object

    jwt_payload_handler = api_settings.JWT_PAYLOAD_HANDLER
    jwt_encode_handler = api_settings.JWT_ENCODE_HANDLER

    payload = jwt_payload_handler(user, type_access)

    if expires and isinstance(expires, timedelta):
        payload["exp"] = timezone.now() + expires
    return jwt_encode_handler(payload, "default")


# Keet it here to avoid import recursion
def auth_payload(token, user=None, request=None, issued_at=None):
    from django.conf import settings

    SHARED_BACKEND_URL = settings.BACKEND_URL

    if user and request:
        user_logged_in.send(sender=user.__class__, request=request, user=user)
    api_url = SHARED_BACKEND_URL
    if hasattr(user, "backend") and "Engie" in user.backend:
        api_url = settings.ENGIE_BACKEND_URL
    elif hasattr(user, "backend") and "CCR" in user.backend:
        api_url = settings.CCR_BACKEND_URL

    prefetch_related_objects([user], *AuthUserSerializer._PREFETCH_RELATED_FIELDS)

    return {
        "token": token,
        "user": AuthUserSerializer(user, context={"request": request}).data,
        "api_url": api_url,
        "pk": issued_at,
    }
