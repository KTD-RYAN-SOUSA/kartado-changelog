# flake8: noqa
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger

from ..production import *

# Database
DATABASES = {"default": credentials.ENGIE_PRODUCTION_DATABASE_URL}
AWS_STORAGE_BUCKET_NAME = credentials.AWS_STORAGE_ENGIE_PRODUCTION_BUCKET_NAME
AWS_S3_CUSTOM_DOMAIN = "%s.s3.amazonaws.com" % AWS_STORAGE_BUCKET_NAME
STATIC_URL = "https://%s/%s/" % (AWS_S3_CUSTOM_DOMAIN, AWS_STATIC_LOCATION)
AWS_S3_REGION_NAME = "sa-east-1"

BACKEND_URL = "https://api.engie.kartado.com.br"
FRONTEND_URL = "https://engie.kartado.com.br"

# Sentry Start
sentry_sdk.init(
    dsn=credentials.SENTRY_DATA_SOURCE_NAME,
    environment="production-engie",
    integrations=[DjangoIntegration()],
    sample_rate=SENTRY_SAMPLE_RATE,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    send_default_pii=True,
)
ignore_logger("cssutils")

ARCGIS_SYNC_ENABLE = True

# Engie VG credentials
VG_TOKEN = credentials.PRODUCTION_VG_TOKEN
VG_LOGIN = credentials.PRODUCTION_VG_LOGIN
VG_PWD = credentials.PRODUCTION_VG_PWD
VG_BASE_URL = credentials.PRODUCTION_VG_BASE_URL


ECM_SEARCH_URL_INITIAL = credentials.ECM_SEARCH_URL_INITIAL_PROD

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# SQS Configuration for Production Engie Environment for Push Notifications
SQS_PUSH_NOTIFICATIONS_QUEUE_NAME = "kartado-push-notifications-engie-production"
SQS_PUSH_NOTIFICATIONS_DLQ_NAME = "kartado-push-notifications-dlq-cengie-production"
SQS_REGION = "sa-east-1"
SQS_PUSH_NOTIFICATIONS_QUEUE_URL = f"https://sqs.{SQS_REGION}.amazonaws.com/608592777334/{SQS_PUSH_NOTIFICATIONS_QUEUE_NAME}"
SQS_PUSH_NOTIFICATIONS_DLQ_URL = f"https://sqs.{SQS_REGION}.amazonaws.com/608592777334/{SQS_PUSH_NOTIFICATIONS_DLQ_NAME}"

KARTADO_REPORTS_URL = (
    "https://9l641ldhd8.execute-api.sa-east-1.amazonaws.com/engie-production"
)

# ECS Fargate Configuration
ECS_CLUSTER_NAME = "ecs-engie-cluster"
ECS_TASK_FAMILY = "ecs-engie-family"
ECS_SUBNETS = ["subnet-070f85df233bded59", "subnet-03020664788e7cd33"]
ECS_SECURITY_GROUPS = ["sg-00a2e81b298d365d0", "sg-07edea72c620c6c7e"]
AWS_DEFAULT_REGION_ECS = "sa-east-1"
