# flake8: noqa
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger

from .base import *

DEBUG = False

# Disable error emails
ADMINS = []

# Security settings
ALLOWED_HOSTS = ["*"]
SECRET_KEY = credentials.STAGING_SECRET_KEY

# Database
DATABASES = {"default": credentials.STAGING_DATABASE_URL}

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
AWS_STORAGE_BUCKET_NAME = credentials.AWS_STORAGE_STAGING_BUCKET_NAME
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
AWS_XRAY_TRACING_NAME = "HidrOS-Staging"
XRAY_RECORDER = {
    # If turned on built-in database queries and template rendering will be recorded as subsegments
    "AUTO_INSTRUMENT": True,
    "AWS_XRAY_CONTEXT_MISSING": "LOG_ERROR",
    "PLUGINS": (),
    "SAMPLING": True,
    "SAMPLING_RULES": None,
    # the segment name for segments generated from incoming requests
    "AWS_XRAY_TRACING_NAME": "HidrOS-Staging",
    "DYNAMIC_NAMING": None,  # defines a pattern that host names should match
    # defines when a segment starts to stream out its children subsegments
    "STREAMING_THRESHOLD": None,
}

# SILKY Silk
SILKY_AUTHENTICATION = True
SILKY_AUTHORISATION = True

# SAML2 AUTH
SAML2_AUTH[
    "METADATA_AUTO_CONF_URL"
] = "https://engieapppreview.oktapreview.com/app/exk6b7ndozaN1ae220x6/sso/saml/metadata"
SAML2_AUTH["ENTITY_ID"] = "https://hidros.staging.roadlabs.com.br/saml2/acs/"
SAML2_AUTH["FRONTEND_URL"] = "https://pre.engie.kartado.com.br/#/login"
SAML2_AUTH["ASSERTION_URL"] = "https://hidros.staging.roadlabs.com.br"

# Engie VG credentials
VG_TOKEN = credentials.STAGING_VG_TOKEN
VG_LOGIN = credentials.STAGING_VG_LOGIN
VG_PWD = credentials.STAGING_VG_PWD
VG_BASE_URL = credentials.STAGING_VG_BASE_URL

# Don`t use AWS X-Ray for local development
if "aws_xray_sdk.ext.django" in INSTALLED_APPS:
    INSTALLED_APPS.remove("aws_xray_sdk.ext.django")

if "aws_xray_sdk.ext.django.middleware.XRayMiddleware" in MIDDLEWARE:
    MIDDLEWARE.remove("aws_xray_sdk.ext.django.middleware.XRayMiddleware")

BACKEND_URL = "https://api.hidros.staging.roadlabs.com.br"
FRONTEND_URL = "https://app.staging.kartado.com.br"

# Sentry Start
sentry_sdk.init(
    dsn=credentials.SENTRY_DATA_SOURCE_NAME,
    environment="staging",
    integrations=[DjangoIntegration()],
    sample_rate=SENTRY_SAMPLE_RATE,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    send_default_pii=True,
)
ignore_logger("cssutils")

ENGIE_BACKEND_URL = "https://pre.api.engie.kartado.com.br"
CCR_BACKEND_URL = "https://homolog-ccr.api.kartado.com.br"
ZIP_DOWNLOAD_URL = (
    "http://staging-general-2.eba-aud5cajn.us-east-1.elasticbeanstalk.com"
)
KARTADO_REPORTS_URL = "https://s8lxc6l5mf.execute-api.us-east-1.amazonaws.com/staging"

# ECS Fargate Configuration
ECS_CLUSTER_NAME = "ecs-staging-cluster"
ECS_TASK_FAMILY = "ecs-staging-family"
ECS_SUBNETS = ["subnet-0f3a57ed0d25d3ad4", "subnet-0ade5f8fc9c50497e"]
ECS_SECURITY_GROUPS = ["sg-0464d901478cc5558", "sg-03c76b4f7e3636182"]
AWS_DEFAULT_REGION_ECS = "us-east-1"
