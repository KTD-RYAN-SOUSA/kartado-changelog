# flake8: noqa
from .base import *

DEBUG = False

# Security settings
ALLOWED_HOSTS = ["*"]
SECRET_KEY = credentials.PRODUCTION_SECRET_KEY

# Database
DATABASES = {"default": credentials.DATABASE_URL}

# Only safe passwords on production
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "helpers.validators.password_validations.UserAttributeSimilarityValidatorCustom"
    },
    {"NAME": "helpers.validators.password_validations.MinimumLengthValidatorCustom"},
    {"NAME": "helpers.validators.password_validations.CommonPasswordValidatorCustom"},
    {"NAME": "helpers.validators.password_validations.NumericPasswordValidatorCustom"},
]

# Django storages
STATIC_URL = "/static/"
AWS_STORAGE_BUCKET_NAME = credentials.AWS_STORAGE_PRODUCTION_BUCKET_NAME
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
INSTALLED_APPS.remove("aws_xray_sdk.ext.django")
MIDDLEWARE.remove("aws_xray_sdk.ext.django.middleware.XRayMiddleware")
MIDDLEWARE.remove("helpers.middlewares.ActionLogMiddleware")
