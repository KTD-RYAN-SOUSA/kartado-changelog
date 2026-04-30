# flake8: noqa

from .staging import *

SECRET_KEY = credentials.HOMOLOG_SECRET_KEY

# Database
DATABASES = {"default": credentials.DEFAULT_DB_URL}

AWS_STORAGE_BUCKET_NAME = credentials.AWS_STORAGE_HOMOLOG_BUCKET_NAME
AWS_S3_CUSTOM_DOMAIN = "%s.s3.amazonaws.com" % AWS_STORAGE_BUCKET_NAME
STATIC_URL = "https://%s/%s/" % (AWS_S3_CUSTOM_DOMAIN, AWS_STATIC_LOCATION)

# AWS X-Ray Configuration
AWS_XRAY_TRACING_NAME = "Kartado-Homolog"
XRAY_RECORDER = {
    # If turned on built-in database queries and template rendering will be recorded as subsegments
    "AUTO_INSTRUMENT": True,
    "AWS_XRAY_CONTEXT_MISSING": "LOG_ERROR",
    "PLUGINS": (),
    "SAMPLING": True,
    "SAMPLING_RULES": None,
    # the segment name for segments generated from incoming requests
    "AWS_XRAY_TRACING_NAME": "Kartado-Homolog",
    "DYNAMIC_NAMING": None,  # defines a pattern that host names should match
    # defines when a segment starts to stream out its children subsegments
    "STREAMING_THRESHOLD": None,
}

BACKEND_URL = "https://api.homolog.kartado.com.br"
FRONTEND_URL = "https://homolog.kartado.com.br"

# Sentry Start
sentry_sdk.init(
    dsn=credentials.SENTRY_DATA_SOURCE_NAME,
    environment="homolog",
    integrations=[DjangoIntegration()],
    sample_rate=SENTRY_SAMPLE_RATE,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    send_default_pii=True,
)

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://homolog-redis-001.llxpgt.0001.use1.cache.amazonaws.com:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
        },
    }
}
# SQS Configuration for Homolog General Environment for Push Notifications
SQS_PUSH_NOTIFICATIONS_QUEUE_NAME = "kartado-push-notifications-homolog"
SQS_PUSH_NOTIFICATIONS_DLQ_NAME = "kartado-push-notifications-dlq-homolog"
SQS_REGION = "us-east-1"
SQS_PUSH_NOTIFICATIONS_QUEUE_URL = f"https://sqs.{SQS_REGION}.amazonaws.com/270002629958/{SQS_PUSH_NOTIFICATIONS_QUEUE_NAME}"
SQS_PUSH_NOTIFICATIONS_DLQ_URL = f"https://sqs.{SQS_REGION}.amazonaws.com/270002629958/{SQS_PUSH_NOTIFICATIONS_DLQ_NAME}"

KARTADO_REPORTS_URL = "https://o2pbr6hug6.execute-api.us-east-1.amazonaws.com/homolog"

# ECS Fargate Configuration
ECS_CLUSTER_NAME = "ecs-homolog-cluster"
ECS_TASK_FAMILY = "ecs-homolog-family"
ECS_SUBNETS = ["subnet-0f3a57ed0d25d3ad4", "subnet-0ade5f8fc9c50497e"]
ECS_SECURITY_GROUPS = ["sg-0464d901478cc5558", "sg-03c76b4f7e3636182"]
AWS_DEFAULT_REGION_ECS = "us-east-1"
