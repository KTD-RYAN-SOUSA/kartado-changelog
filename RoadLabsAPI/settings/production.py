# flake8: noqa
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger

from .base import *

DEBUG = False

# Security settings
ALLOWED_HOSTS = ["*"]
SECRET_KEY = credentials.PRODUCTION_SECRET_KEY


# Database
DATABASES = {
    "default": credentials.PRODUCTION_DATABASE_URL,
    "engie_prod": credentials.ENGIE_PRODUCTION_DATABASE_URL,
    "ccr_prod": credentials.CCR_PRODUCTION_DATABASE_URL,
}

# Allow browsable API login on dev environment
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] += [
    "rest_framework.authentication.BasicAuthentication",
    "rest_framework.authentication.SessionAuthentication",
]

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


# AWS X-Ray Configuration
AWS_XRAY_TRACING_NAME = "HidrOS-Production"
XRAY_RECORDER = {
    # If turned on built-in database queries and template rendering will be recorded as subsegments
    "AUTO_INSTRUMENT": True,
    "AWS_XRAY_CONTEXT_MISSING": "LOG_ERROR",
    "PLUGINS": (),
    "SAMPLING": True,
    "SAMPLING_RULES": None,
    # the segment name for segments generated from incoming requests
    "AWS_XRAY_TRACING_NAME": "HidrOS-Production",
    "DYNAMIC_NAMING": None,  # defines a pattern that host names should match
    # defines when a segment starts to stream out its children subsegments
    "STREAMING_THRESHOLD": None,
}

AUTHENTICATION_BACKENDS = [
    "helpers.auth_backends.SharedModelBackend",
    "helpers.auth_backends.EngieModelBackend",
    "helpers.auth_backends.CCRModelBackend",
]


# SILKY Silk
SILKY_AUTHENTICATION = True
SILKY_AUTHORISATION = True

# SAML2 AUTH
SAML2_AUTH[
    "METADATA_AUTO_CONF_URL"
] = "https://kartado-public-assets.s3.amazonaws.com/arteris-ad-kartado.xml"
SAML2_AUTH["ENTITY_ID"] = "KARTADO"
SAML2_AUTH["FRONTEND_URL"] = "https://arteris.kartado.com.br/#/login"
SAML2_AUTH["ASSERTION_URL"] = "https://arteris.kartado.com.br"
SAML2_AUTH["ATTRIBUTES_MAP"] = {
    "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    "username": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
}

# Don`t use AWS X-Ray for local development
if "aws_xray_sdk.ext.django" in INSTALLED_APPS:
    INSTALLED_APPS.remove("aws_xray_sdk.ext.django")

if "aws_xray_sdk.ext.django.middleware.XRayMiddleware" in MIDDLEWARE:
    MIDDLEWARE.remove("aws_xray_sdk.ext.django.middleware.XRayMiddleware")

EMAIL_HOST = credentials.AWS_SES["HOST"]
EMAIL_PORT = credentials.AWS_SES["PORT"]
EMAIL_HOST_USER = credentials.AWS_SES["USERNAME"]
EMAIL_HOST_PASSWORD = credentials.AWS_SES["PASSWORD"]
EMAIL_USE_SSL = credentials.AWS_SES["USE_SSL"]
EMAIL_USE_TLS = credentials.AWS_SES["USE_TLS"]

if os.environ.get("BACKEND_URL"):
    BACKEND_URL = os.environ.get("BACKEND_URL")
else:
    BACKEND_URL = "https://api.hidros.roadlabs.com.br"

if os.environ.get("FRONTEND_URL"):
    FRONTEND_URL = os.environ.get("FRONTEND_URL")
else:
    FRONTEND_URL = "https://app.kartado.com.br"


# Sentry Start
sentry_sdk.init(
    dsn=credentials.SENTRY_DATA_SOURCE_NAME,
    environment="production",
    integrations=[DjangoIntegration()],
    sample_rate=SENTRY_SAMPLE_RATE,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    send_default_pii=True,
)
ignore_logger("cssutils")

ENGIE_BACKEND_URL = "https://api.engie.kartado.com.br"
CCR_BACKEND_URL = "https://ccr.api.kartado.com.br"
ZIP_DOWNLOAD_URL = "http://flask-env.eba-rxnpexty.us-east-1.elasticbeanstalk.com/"
KARTADO_REPORTS_URL = (
    "https://d42w1qfaxb.execute-api.us-east-1.amazonaws.com/production"
)

if os.environ.get("ENABLE_REDIS_CACHE", False):
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": "redis://production-cache-001.xjecij.0001.use1.cache.amazonaws.com:6379/1",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": True,
            },
        }
    }

# SQS Configuration for Production General Environment for Push Notifications
SQS_PUSH_NOTIFICATIONS_QUEUE_NAME = "kartado-push-notifications-production"
SQS_PUSH_NOTIFICATIONS_DLQ_NAME = "kartado-push-notifications-dlq-production"
SQS_REGION = "us-east-1"
SQS_PUSH_NOTIFICATIONS_QUEUE_URL = f"https://sqs.{SQS_REGION}.amazonaws.com/608592777334/{SQS_PUSH_NOTIFICATIONS_QUEUE_NAME}"
SQS_PUSH_NOTIFICATIONS_DLQ_URL = f"https://sqs.{SQS_REGION}.amazonaws.com/608592777334/{SQS_PUSH_NOTIFICATIONS_DLQ_NAME}"

# ECS Fargate Configuration
ECS_CLUSTER_NAME = "ecs-general-cluster"
ECS_TASK_FAMILY = "ecs-general-family"
ECS_SUBNETS = [
    "subnet-0e870aea7f9e91a25",
    "subnet-0bf427a53c6ef389c",
    "subnet-06211fff7f47af28f",
]
ECS_SECURITY_GROUPS = [
    "sg-0154e080d4bdfcfbe",
    "sg-01573d1eb4fa1e8cf",
    "sg-0ef8e651a256d32da",
]
AWS_DEFAULT_REGION_ECS = "us-east-1"
