import datetime
import logging
import os

from corsheaders.defaults import default_headers

from . import credentials

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def base_dir_join(*args):
    return os.path.join(BASE_DIR, *args)


APPS = [
    "apps.users",
    "apps.companies",
    "apps.locations",
    "apps.resources",
    "apps.occurrence_records",
    "apps.service_orders",
    "apps.permissions",
    "apps.work_plans",
    "apps.email_handler",
    "apps.dashboard",
    "apps.reportings",
    "apps.templates",
    "apps.roads",
    "apps.services",
    "apps.saml2_auth",
    "apps.files",
    "apps.monitorings",
    "apps.maps",
    "apps.approval_flows",
    "apps.zas",
    "apps.wmdb",
    "apps.daily_reports",
    "apps.constructions",
    "apps.quality_control",
    "apps.project_management",
    "apps.to_dos",
    "apps.integrations",
    "apps.scarface",
    "apps.notifications",
    "apps.forms_ia",
    "apps.sql_chat",
    "apps.bim",
    "apps.ml_predictions",
]

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.gis",
    "django.contrib.postgres",
    # Faster static file caching
    "collectfast",
    "django.contrib.staticfiles",
    # Third party
    "storages",
    "corsheaders",
    "django_filters",
    "rest_framework",
    "rest_framework_gis",
    "rest_framework_jwt",
    "rest_framework_jwt.blacklist",
    "drf_yasg",
    "sequences.apps.SequencesConfig",
    "crispy_forms",
    "fieldsignals",
    "aws_xray_sdk.ext.django",
    "simple_history",
    "django_rest_passwordreset",
    "django_extensions",
    "django_premailer",
] + APPS

MIDDLEWARE = [
    "helpers.middlewares.RawRequestBodyMiddleware",
    "helpers.middlewares.ActionLogMiddleware",
    "aws_xray_sdk.ext.django.middleware.XRayMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "django_ratelimit.middleware.RatelimitMiddleware",
]

RATELIMIT_VIEW = "helpers.middlewares.ratelimit_exceeded_view"

# Django settings
AUTH_USER_MODEL = "users.User"
ROOT_URLCONF = "RoadLabsAPI.urls.base"
WSGI_APPLICATION = "RoadLabsAPI.wsgi.application"
DATA_UPLOAD_MAX_MEMORY_SIZE = 20971520
FILE_UPLOAD_MAX_MEMORY_SIZE = 20971520

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]


# Django REST Framework configuration
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "helpers.auth.CustomTokenAuthentication",
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    "ORDERING_PARAM": "sort",
    # JSON API Pagination and redering settings
    "PAGE_SIZE": 500,
    "EXCEPTION_HANDLER": "helpers.error_messages.custom_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "helpers.pagination.CustomPagination",
    "DEFAULT_PARSER_CLASSES": [
        "helpers.json_parser.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "helpers.renderers.LimitedSizeJSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "TEST_REQUEST_RENDERER_CLASSES": ["rest_framework_json_api.renderers.JSONRenderer"],
    "DEFAULT_METADATA_CLASS": "rest_framework_json_api.metadata.JSONAPIMetadata",
    "TEST_REQUEST_DEFAULT_FORMAT": "vnd.api+json",
}

# Login Configuration
LOGIN_URL = "/api-auth/login/"
LOGOUT_URL = "/api-auth/logout/"

# JSON API Configuration
JSON_API_FORMAT_FIELD_NAMES = "camelize"
JSON_API_FORMAT_TYPES = "capitalize"
JSON_API_PLURALIZE_TYPES = False

# E-mail settings
PREMAILER_OPTIONS = dict(
    preserve_internal_links=True,
    remove_classes=False,
    keep_style_tags=True,
    include_star_selectors=True,
)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
DEFAULT_FROM_EMAIL = credentials.EMAIL_DEFAULT_FROM
SERVER_EMAIL = credentials.EMAIL_SERVER
EMAIL_HOST = credentials.MAILTRAP["HOST"]
EMAIL_PORT = credentials.MAILTRAP["PORT"]
EMAIL_HOST_USER = credentials.MAILTRAP["USERNAME"]
EMAIL_HOST_PASSWORD = credentials.MAILTRAP["PASSWORD"]
EMAIL_USE_SSL = credentials.MAILTRAP["USE_SSL"]
EMAIL_USE_TLS = credentials.MAILTRAP["USE_TLS"]
ADMINS = [
    ("Marcos - Slackbot", "e2v2r5j7k8d3k1j0@road-labs.slack.com"),
    ("Backend Admin Group", "backend-admin@roadlabs.com.br"),
]

# Internationalization
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_L10N = True
USE_TZ = True

# AWS Config
AWS_ACCESS_KEY_ID = credentials.AWS_ACCESS_KEY_ID
AWS_ACCESS_KEY = credentials.AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = credentials.AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN = credentials.AWS_SESSION_TOKEN
AWS_DEFAULT_REGION = credentials.AWS_DEFAULT_REGION
AWS_SES_VERIFY_BOUNCE_SIGNATURES = False
AWS_S3_SIGNATURE_VERSION = "s3v4"


# Silk
SILKY_META = True
SILKY_MAX_RECORDED_REQUESTS = 10**4
SILKY_INTERCEPT_PERCENT = 10
SILKY_MAX_RECORDED_REQUESTS_CHECK_PERCENT = 0


# JWT Token Configuration
JWT_AUTH = {
    "JWT_EXPIRATION_DELTA": datetime.timedelta(days=7),
    # the mobile expiration delta is set in helpers.auth_views
    "JWT_ALLOW_REFRESH": True,
    "JWT_REFRESH_EXPIRATION_DELTA": datetime.timedelta(days=730),
    "JWT_RESPONSE_PAYLOAD_HANDLER": "helpers.testing.auth_testing.auth_payload",
    "JWT_GET_USER_SECRET_KEY": "helpers.auth.jwt_get_secret_key",
    "JWT_PAYLOAD_HANDLER": "helpers.auth.payload_handler",
    "JWT_ENCODE_HANDLER": "helpers.auth.custom_encode_handler",
    "JWT_AUTH_HEADER_PREFIX": "JWT",
}

# documentation
SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "Basic": {"type": "basic"},
        "JWT": {
            "type": "apiKey",
            "description": "JWT Token",
            "name": "Authorization",
            "in": "header",
        },
    },
    "SHOW_REQUEST_HEADERS": True,
    "DEFAULT_INFO": "RoadLabsAPI.documentation.open_api_info",
}

# CORS
CORS_ALLOW_ALL_ORIGINS = True

CORS_ALLOW_HEADERS = (
    *default_headers,
    "x-invalidate-cache",
)

# geospatial library imports
if os.environ.get("GDAL_LIBRARY_PATH"):
    GDAL_LIBRARY_PATH = os.environ["GDAL_LIBRARY_PATH"]
    GDAL_DATA = os.environ["GDAL_DATA"]

if os.environ.get("GEOS_LIBRARY_PATH"):
    GEOS_LIBRARY_PATH = os.environ["GEOS_LIBRARY_PATH"]


# Django-Simple-History
SIMPLE_HISTORY_HISTORY_ID_USE_UUID = True

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
    "DENIED_MESSAGE": "Seu usuário Okta não foi configurado para utilizar o Kartado Energia",
}

# xmlsec binary for saml2 lib when running on lambda
if os.environ.get("XMLSEC_BINARY"):
    SAML2_AUTH["XMLSEC_BINARY"] = os.environ["XMLSEC_BINARY"]

BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3000"
DEFAULT_BACKEND_URL = "https://api.hidros.roadlabs.com.br"

ARCGIS_SYNC_ENABLE = False


# AWS Logging Config
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("s3transfer").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Sentry Configs
SENTRY_SAMPLE_RATE = 1.0
SENTRY_TRACES_SAMPLE_RATE = 0.005

ECM_SEARCH_URL_INITIAL = credentials.ECM_SEARCH_URL_INITIAL_DES

HTML_TO_PDF_API_URL = (
    "http://html-to-pdf-prod-3.us-east-1.elasticbeanstalk.com/transform"
)
HTML_TO_PDF_BUCKET_NAME = "kartado-htmltopdf"
N8N_DAILY_REPORT_WEBHOOK_URL = (
    "https://kartado.app.n8n.cloud/webhook/b6129102-2fcf-4dbc-b493-2421c0738ccb"
)
N8N_EDITED_DAILY_REPORT_WEBHOOK_URL = (
    "https://kartado.app.n8n.cloud/webhook/83a2a1fd-e5f4-4afd-b2ce-168336230d87"
)
N8N_DAILY_REPORT_FILE_WEBHOOK_URL = (
    "https://kartado.app.n8n.cloud/webhook/d8e79fdd-70ff-46b3-adb6-83530339a50f"
)

COLLECTFAST_STRATEGY = "collectfast.strategies.boto3.Boto3Strategy"

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Configuração de Logging (CloudWatch / ECS Fargate)
from .logging_config import LOGGING  # noqa
