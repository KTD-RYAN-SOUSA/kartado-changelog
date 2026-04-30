# flake8: noqa
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger

from ..staging import *

# Database
DATABASES = {"default": credentials.ENGIE_STAGING_DATABASE_URL}
AWS_STORAGE_BUCKET_NAME = credentials.AWS_STORAGE_ENGIE_STAGING_BUCKET_NAME
AWS_S3_CUSTOM_DOMAIN = "%s.s3.amazonaws.com" % AWS_STORAGE_BUCKET_NAME
STATIC_URL = "https://%s/%s/" % (AWS_S3_CUSTOM_DOMAIN, AWS_STATIC_LOCATION)
AWS_S3_REGION_NAME = "sa-east-1"

EMAIL_HOST = credentials.ETHEREAL_MAIL["HOST"]
EMAIL_PORT = credentials.ETHEREAL_MAIL["PORT"]
EMAIL_HOST_USER = credentials.ETHEREAL_MAIL["USERNAME"]
EMAIL_HOST_PASSWORD = credentials.ETHEREAL_MAIL["PASSWORD"]
EMAIL_USE_SSL = credentials.ETHEREAL_MAIL["USE_SSL"]
EMAIL_USE_TLS = credentials.ETHEREAL_MAIL["USE_TLS"]

BACKEND_URL = "https://pre.api.engie.kartado.com.br"
FRONTEND_URL = "https://pre.engie.kartado.com.br"

ARCGIS_SYNC_ENABLE = False

# Sentry Start
sentry_sdk.init(
    dsn=credentials.SENTRY_DATA_SOURCE_NAME,
    environment="staging-engie",
    integrations=[DjangoIntegration()],
    sample_rate=SENTRY_SAMPLE_RATE,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    send_default_pii=True,
)
ignore_logger("cssutils")

KARTADO_REPORTS_URL = (
    "https://mqw6qcmcga.execute-api.sa-east-1.amazonaws.com/engie-staging"
)

# ECS Fargate Configuration
ECS_CLUSTER_NAME = "ecs-engie-homolog-cluster"
ECS_TASK_FAMILY = "ecs-engie-homolog-family"
ECS_SUBNETS = ["subnet-070f85df233bded59", "subnet-03020664788e7cd33"]
ECS_SECURITY_GROUPS = ["sg-00a2e81b298d365d0", "sg-07edea72c620c6c7e"]
AWS_DEFAULT_REGION_ECS = "sa-east-1"
