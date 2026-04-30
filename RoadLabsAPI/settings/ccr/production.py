# flake8: noqa
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from ..production import *

# Database
DATABASES = {"default": credentials.CCR_PRODUCTION_DATABASE_URL}
AWS_STORAGE_BUCKET_NAME = credentials.AWS_STORAGE_CCR_PRODUCTION_BUCKET_NAME
AWS_S3_CUSTOM_DOMAIN = "%s.s3.amazonaws.com" % AWS_STORAGE_BUCKET_NAME
STATIC_URL = "https://%s/%s/" % (AWS_S3_CUSTOM_DOMAIN, AWS_STATIC_LOCATION)

BACKEND_URL = "https://ccr.api.kartado.com.br"
FRONTEND_URL = "https://ccr.kartado.com.br"

# Sentry Start
sentry_sdk.init(
    dsn=credentials.SENTRY_DATA_SOURCE_NAME,
    environment="production-ccr",
    integrations=[DjangoIntegration()],
    sample_rate=SENTRY_SAMPLE_RATE,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    send_default_pii=True,
)

AUTHENTICATION_BACKENDS = [
    "helpers.auth_backends.SharedModelBackend",
]

# SAML2 AUTH
SAML2_AUTH = {
    "DEFAULT_NEXT_URL": "/admin",
    # Custom target redirect URL after the user get logged in.
    # Default to /admin if not set.
    # This setting will be overwritten if you have parameter ?next= specificed in the login URL.
    "CREATE_USER": False,  # Create a new Django user when a new user logs in. Defaults to True.
    "USE_JWT": True,
    # Set this to True if you are running a Single Page Application (SPA)
    # with Django Rest Framework (DRF), and are using JWT authentication to authorize client users
    "DENIED_MESSAGE": "Seu usuário não foi configurado para utilizar o Kartado",
    "METADATA_AUTO_CONF_URL": "https://login.microsoftonline.com/abc7f1fd-344f-4917-8f35-fe0f49e1a79a/federationmetadata/2007-06/federationmetadata.xml?appid=703b7b80-bc9d-4e1e-b7e0-030778550bd0",
    "ENTITY_ID": "KARTADO",
    "FRONTEND_URL": "https://ccr.kartado.com.br/#/login",
    "ASSERTION_URL": "https://ccr.kartado.com.br",
}

# xmlsec binary for saml2 lib when running on lambda
if os.environ.get("XMLSEC_BINARY"):
    SAML2_AUTH["XMLSEC_BINARY"] = os.environ["XMLSEC_BINARY"]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# SQS Configuration for Production CCR Environment for Push Notifications
SQS_PUSH_NOTIFICATIONS_QUEUE_NAME = "kartado-push-notifications-ccr-production"
SQS_PUSH_NOTIFICATIONS_DLQ_NAME = "kartado-push-notifications-dlq-cccr-production"
SQS_REGION = "sa-east-1"
SQS_PUSH_NOTIFICATIONS_QUEUE_URL = f"https://sqs.{SQS_REGION}.amazonaws.com/608592777334/{SQS_PUSH_NOTIFICATIONS_QUEUE_NAME}"
SQS_PUSH_NOTIFICATIONS_DLQ_URL = f"https://sqs.{SQS_REGION}.amazonaws.com/608592777334/{SQS_PUSH_NOTIFICATIONS_DLQ_NAME}"

KARTADO_REPORTS_URL = (
    "https://xc2cn8qj64.execute-api.sa-east-1.amazonaws.com/ccr-production"
)

# ECS Fargate Configuration
ECS_CLUSTER_NAME = "ecs-ccr-cluster"
ECS_TASK_FAMILY = "ecs-ccr-family"
ECS_SUBNETS = [
    "subnet-0855c9a93c5b52c54",
    "subnet-0c433d7afa36bb70a",
    "subnet-0372a8ca124f9e288",
]
ECS_SECURITY_GROUPS = ["sg-089b111da3bea8878", "sg-09034cd22c625ed07"]
AWS_DEFAULT_REGION_ECS = "sa-east-1"
