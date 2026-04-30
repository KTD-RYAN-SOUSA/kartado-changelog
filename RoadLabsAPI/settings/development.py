import os

from dotenv import load_dotenv

# flake8: noqa
from .base import *

DEBUG = True

# Load .env
if os.path.exists(".env"):
    load_dotenv(".env")

# Security settings
SECRET_KEY = "secret"
SECURE_SSL_REDIRECT = False
ALLOWED_HOSTS = ["*"]

# Allow easy passwords on local
AUTH_PASSWORD_VALIDATORS = []

# Database
DATABASES = {"default": credentials.DATABASE_URL}

# Use development URLs
ROOT_URLCONF = "RoadLabsAPI.urls.development"

# SILKY Silk
# Use Silk for the development environment
INSTALLED_APPS.append("silk")
MIDDLEWARE.append("silk.middleware.SilkyMiddleware")
SILKY_INTERCEPT_PERCENT = 100
SILKY_MAX_RECORDED_REQUESTS_CHECK_PERCENT = 0
SILKY_AUTHENTICATION = False
SILKY_AUTHORISATION = False

# Django storages
STATIC_URL = "/static/"
AWS_STORAGE_BUCKET_NAME = credentials.AWS_STORAGE_DEVELOPMENT_BUCKET_NAME
AWS_S3_CUSTOM_DOMAIN = "%s.s3.amazonaws.com" % AWS_STORAGE_BUCKET_NAME
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
AWS_LOCATION = "static"

STATICFILES_DIRS = [os.path.join(BASE_DIR, "assets/")]

AWS_STATIC_LOCATION = "static"
STATICFILES_STORAGE = "RoadLabsAPI.storage_backends.StaticStorage"
STATIC_URL = "https://%s/%s/" % (AWS_S3_CUSTOM_DOMAIN, AWS_STATIC_LOCATION)

AWS_PUBLIC_MEDIA_LOCATION = "media/public"
DEFAULT_FILE_STORAGE = "RoadLabsAPI.storage_backends.PublicMediaStorage"

AWS_PRIVATE_MEDIA_LOCATION = "media/private"
PRIVATE_FILE_STORAGE = "RoadLabsAPI.storage_backends.PrivateMediaStorage"

# Don`t use AWS X-Ray for local development
if "aws_xray_sdk.ext.django" in INSTALLED_APPS:
    INSTALLED_APPS.remove("aws_xray_sdk.ext.django")

if "aws_xray_sdk.ext.django.middleware.XRayMiddleware" in MIDDLEWARE:
    MIDDLEWARE.remove("aws_xray_sdk.ext.django.middleware.XRayMiddleware")

# SAML2 AUTH
SAML2_AUTH[
    "METADATA_AUTO_CONF_URL"
] = "https://dev-300545.oktapreview.com/app/exkjg6jkjb8ZeZ5pt0h7/sso/saml/metadata"
SAML2_AUTH["ENTITY_ID"] = "http://localhost:8000/saml2/acs/"
SAML2_AUTH["FRONTEND_URL"] = "http://localhost:3000/#/login"

# Engie VG credentials
VG_TOKEN = credentials.STAGING_VG_TOKEN
VG_LOGIN = credentials.STAGING_VG_LOGIN
VG_PWD = credentials.STAGING_VG_PWD
VG_BASE_URL = credentials.STAGING_VG_BASE_URL

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

KARTADO_REPORTS_URL = "http://host.docker.internal:3001"
