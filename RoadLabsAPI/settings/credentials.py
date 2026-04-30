# flake8: noqa
import os
import random
import string

from decouple import config
from dj_database_url import parse as dburl


def generate_random_database_name():
    return "".join(
        random.SystemRandom().choice(string.ascii_lowercase + string.digits)
        for _ in range(10)
    )


stage = config("STAGE", default="LOCAL")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
if ":" in DB_HOST:
    # Split host into host:port
    DB_HOST, DB_PORT = DB_HOST.split(":")
DB_NAME = os.environ.get("DB_NAME", "hidros-local")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

# Will be defined from env variables
DEFAULT_DB_URL = dburl(
    "postgis://{}:{}@{}:{}/{}".format(DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME)
)

# Add statement_timeout to Production Genreal Database
if stage == "PRODUCTION":
    DEFAULT_DB_URL["OPTIONS"] = {
        "options": "-c statement_timeout=60000",
    }

# Database URLs
DATABASE_URL = DEFAULT_DB_URL
TESTING_DATABASE_URL = dburl(
    "postgis://{}:{}@{}:{}/{}".format(
        DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, generate_random_database_name()
    )
)
STAGING_DATABASE_URL = dburl(
    os.environ.get(
        "STAGING_DATABASE_URL",
        "postgis://postgres:postgres@localhost:5432/hidros-staging",
    )
)
PRODUCTION_DATABASE_URL = DEFAULT_DB_URL

ENGIE_DB_HOST = os.environ.get("ENGIE_DB_HOST", "localhost")
ENGIE_DB_PORT = os.environ.get("ENGIE_DB_PORT", "5432")
if ":" in ENGIE_DB_HOST:
    # Split host into host:port
    ENGIE_DB_HOST, ENGIE_DB_PORT = ENGIE_DB_HOST.split(":")
ENGIE_DB_NAME = os.environ.get("ENGIE_DB_NAME", "hidros-local")
ENGIE_DB_USER = os.environ.get("ENGIE_DB_USER", "postgres")
ENGIE_DB_PASSWORD = os.environ.get("ENGIE_DB_PASSWORD", "postgres")

ENGIE_PRODUCTION_DATABASE_URL = dburl(
    "postgis://{}:{}@{}:{}/{}".format(
        ENGIE_DB_USER, ENGIE_DB_PASSWORD, ENGIE_DB_HOST, ENGIE_DB_PORT, ENGIE_DB_NAME
    )
)
ENGIE_STAGING_DATABASE_URL = DEFAULT_DB_URL

CCR_DB_HOST = os.environ.get("CCR_DB_HOST", "localhost")
CCR_DB_PORT = os.environ.get("CCR_DB_PORT", "5432")
if ":" in CCR_DB_HOST:
    # Split host into host:port
    CCR_DB_HOST, CCR_DB_PORT = CCR_DB_HOST.split(":")
CCR_DB_NAME = os.environ.get("CCR_DB_NAME", "hidros-local")
CCR_DB_USER = os.environ.get("CCR_DB_USER", "postgres")
CCR_DB_PASSWORD = os.environ.get("CCR_DB_PASSWORD", "postgres")

# Will be defined from env variables
CCR_PRODUCTION_DATABASE_URL = dburl(
    "postgis://{}:{}@{}:{}/{}".format(
        CCR_DB_USER, CCR_DB_PASSWORD, CCR_DB_HOST, CCR_DB_PORT, CCR_DB_NAME
    )
)

CCR_HOMOLOG_DATABASE_URL = DEFAULT_DB_URL


# Secret keys
SECRET_KEY = "teste"
STAGING_SECRET_KEY = ":iNU4uM$<xk(N!m>ZvuyqeM`s+DKPQL[=oh;-f[/i9h8s>i9GY8h,<LGI=88]gA"
HOMOLOG_SECRET_KEY = "6sh(yxdkp0si6@6#((9&_5@e($8u^x7p$4^8$5+h_&kgp_0841"
PRODUCTION_SECRET_KEY = "c2343f09d-08J-8-98M-((__M--8j-8j-vçlkxcxlknv__))"

# AWS Credentials
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get(
    "AWS_SECRET_ACCESS_KEY", ""
)
AWS_SESSION_TOKEN = os.environ.get("AWS_SESSION_TOKEN", "")
AWS_STORAGE_PRODUCTION_BUCKET_NAME = "spotway-roadlabs-assets"
AWS_STORAGE_DEVELOPMENT_BUCKET_NAME = os.environ.get(
    "AWS_STORAGE_DEVELOPMENT_BUCKET_NAME", "spotway-roadlabs-assets-dev"
)
AWS_STORAGE_HOMOLOG_BUCKET_NAME = "kartado-homolog-assets"
AWS_STORAGE_STAGING_BUCKET_NAME = "kartado-staging-assets"
AWS_STORAGE_ENGIE_PRODUCTION_BUCKET_NAME = "engie-production-assets"
AWS_STORAGE_ENGIE_STAGING_BUCKET_NAME = "engie-staging-assets"
AWS_STORAGE_CCR_PRODUCTION_BUCKET_NAME = "kartado-ccr-production-assets"
AWS_STORAGE_CCR_HOMOLOG_BUCKET_NAME = "kartado-ccr-homolog-assets"
AWS_DEFAULT_REGION = "us-east-1"

# Mail addresses configuration
EMAIL_DEFAULT_FROM = "notificacoes@kartado.com.br"
EMAIL_SERVER = "notificacoes@kartado.com.br"

# Mail server configuration
MAILTRAP = {
    "HOST": "smtp.mailtrap.io",
    "PORT": 587,
    "USERNAME": "ab950c795aa41e",
    "PASSWORD": "7b6820ab786e11",
    "USE_SSL": False,
    "USE_TLS": True,
}

MAILTRAP_CCR = {
    "HOST": "smtp.mailtrap.io",
    "PORT": 587,
    "USERNAME": "ab950c795aa41e",
    "PASSWORD": "7b6820ab786e11",
    "USE_SSL": False,
    "USE_TLS": True,
}

MAILTRAP_ENGIE = {
    "HOST": "smtp.mailtrap.io",
    "PORT": 587,
    "USERNAME": "d2f14e0378b514",
    "PASSWORD": "1e08250a4cdc88",
    "USE_SSL": False,
    "USE_TLS": True,
}

AWS_SES = {
    "HOST": "email-smtp.us-east-1.amazonaws.com",
    "PORT": 465,
    "USERNAME": os.environ.get("AWS_SES_USERNAME", ""),
    "PASSWORD": os.environ.get("AWS_SES_PASSWORD", ""),
    "USE_SSL": True,
    "USE_TLS": False,
}

ETHEREAL_MAIL = {
    "HOST": "smtp.ethereal.email",
    "PORT": 587,
    "USERNAME": "norwood.block79@ethereal.email",
    "PASSWORD": "7erWfVX6gj8aUZJHUN",
    "USE_SSL": False,
    "USE_TLS": True,
}

# Gmaps and mapbox api keys
GMAPS_API_KEY = "AIzaSyBefbWY3qUC1ekg0X1dT4UuyMkFc4VZ-No"
MAPBOX_API_KEY = os.environ.get("MAPBOX_API_KEY", "")

# Amplitude
if stage in ("PRODUCTION", "ENGIE_PRODUCTION", "CCR_PRODUCTION"):
    AMPLITUDE_API_KEY = "e7ebde3416940f36abbed4e943d27453"
else:
    AMPLITUDE_API_KEY = "21312bd6eaf7ad99119b5480bc04ea6e"

# Engie APIs
# HIDRO_URL_DEV = "https://servicosdes.engieenergia.com.br/osb/servicos/secured/rest/hidrologia/consultaNivelReservatorioDataHora"
HIDRO_URL = "https://servicos.engieenergia.com.br/osb/servicos/secured/rest/hidrologia/consultaNivelReservatorioDataHora"
HIDRO_USERNAME = "kartado"
# HIDRO_PWD_DEV = "engie@2019"
HIDRO_PWD = "ze0DmjFa"

ENGIE_RH_URL = "https://servicos.engieenergia.com.br/osb/servicos/secured/rest/rh/"

# Engie ARCGIS
ARCGIS_TOKEN = "https://gis.engieenergia.com.br/portal/sharing/rest/generateToken"
ARCGIS_URL = "https://gis.engieenergia.com.br/portal"
ARCGIS_FEATURES = (
    "https://gis.engieenergia.com.br/gis/rest/services/Hosted/Hidros_RG/FeatureServer/"
)
ARCGIS_LOGIN = "integracao.hidros"
ARCGIS_PWD = "int3gr@cao#gis&hid"

# Engie VG Residuos
STAGING_VG_TOKEN = "https://sandbox-login.vgresiduos.com.br/oauth2/token"
STAGING_VG_LOGIN = "6lc6fu4daovkgl5m3lpf8vjv0o"
STAGING_VG_PWD = "1it0udf21bokrl8bar70cosm0keocn7jb1s65hauo4s2jk65iock"
STAGING_VG_BASE_URL = "https://apiv2-sandbox.vgresiduos.com.br/v2/organization-units"

PRODUCTION_VG_TOKEN = "https://login.vgresiduos.com.br/oauth2/token"
PRODUCTION_VG_LOGIN = "685p3g1a6jmftifctsfknqdtag"
PRODUCTION_VG_PWD = "1dv59jl3950udikoi0grv1njjaljtpqrvftavjb1r9g80l461sc7"
PRODUCTION_VG_BASE_URL = "https://apiv2.vgresiduos.com.br/v2/organization-units"

# Engie ECM
ECM_SEARCH_URL_INITIAL_PROD = "http://ecm.tractebelenergia.com.br/cs/idcplg?IdcService=GET_SEARCH_RESULTS&QueryText="
ECM_SEARCH_URL_INITIAL_DES = "http://ecmpreqa.tractebelenergia.com.br/cs/idcplg?IdcService=GET_SEARCH_RESULTS&QueryText="
ECM_SEARCH_URL_FINAL = "&dpTriggerValue=DPSPatrimonioImob&searchFormType=standard&SearchQueryFormat=UNIVERSAL&ftx=&AdvSearch=True&ResultCount=50&SortField=dFormat&SortOrder=Desc"
ECM_SEARCH_EXTERNAL_URL = "https://servicos.engieenergia.com.br/osb/servicos/secured/rest/ecm/pesquisaDocumentosEcm"
ECM_DOWNLOAD_EXTERNAL_URL = "https://servicos.engieenergia.com.br/osb/servicos/secured/rest/ecm/downloadDocumentosEcm"
ECM_LOGIN_TOKEN = "a2FydGFkbzp6ZTBEbWpGYQ=="
ECM_LOGIN_USERNAME = "kartado"
ECM_LOGIN_PWD = "ze0DmjFa"

# Sentry
SENTRY_DATA_SOURCE_NAME = (
    "https://0dacfabeb25e419590dcbfc70c52d303@o138963.ingest.sentry.io/5666988"
)

# Comtele SMS
COMTELE_API_KEY = "e6c00eff-68a4-44ff-a878-ebcc7518fd22"

TESSADEM_API_KEY = config(
    "TESSADEM_API_KEY", "c40bff4dda7c1b90134950ee9161e1928f50a96b"
)
# SIH Integration
SIH_API_BASE_URL = (
    "https://servicos.engieenergia.com.br/osb/servicos/secured/rest/hidrologia"
)
SIH_API_USERNAME = "hidrologia"
SIH_API_PWD = "HlIi0r#L0gy@y__0Rp"

HTMLTOPDF_API_KEY = "Zvr75SDnPhOC70eAgUcYmv9y2u6GxmY1"

# GOTENBERG
GOTENBERG_BASE_URL = os.environ.get(
    "GOTENBERG_BASE_URL",
    "https://gotenberg.kartado.com.br",
)

# Firebase credentials
FIREBASE_CREDENTIALS_BASE64 = os.environ.get("FIREBASE_CREDENTIALS_BASE64", "")

# SQS Configuration for Push Notifications
SQS_ENABLED = os.environ.get("SQS_ENABLED", "false").lower() == "true"

# Forms IA Generator - AWS Secrets Manager Configuration
FORMS_IA_SECRETS = {
    "HOMOLOG": {"name": "kartado/homolog/forms-ia/credentials", "region": "us-east-1"},
    "PRODUCTION": {
        "name": "kartado/production/forms-ia/credentials",
        "region": "us-east-1",
    },
    "CCR_PRODUCTION": {
        "name": "kartado/ccr-production/forms-ia/credentials",
        "region": "sa-east-1",
    },
    "ENGIE_PRODUCTION": {
        "name": "kartado/engie-production/forms-ia/credentials",
        "region": "sa-east-1",
    },
}

# SQL chat IA - AWS Secrets Manager Configuration
SQL_CHAT_SECRETS = {
    "HOMOLOG": {"name": "kartado/homolog/sql-chat/credentials", "region": "us-east-1"},
    "PRODUCTION": {
        "name": "kartado/production/sql-chat/credentials",
        "region": "us-east-1",
    },
    "CCR_PRODUCTION": {
        "name": "kartado/ccr-production/sql-chat/credentials",
        "region": "sa-east-1",
    },
    "ENGIE_PRODUCTION": {
        "name": "kartado/engie-production/sql-chat/credentials",
        "region": "sa-east-1",
    },
}

# Databricks ML - AWS Secrets Manager Configuration
DATABRICKS_SECRETS = {
    "HOMOLOG": {
        "name": "kartado/homolog/databricks/credentials",
        "region": "us-east-1",
    },
    "PRODUCTION": {
        "name": "kartado/production/databricks/credentials",
        "region": "us-east-1",
    },
    "CCR_PRODUCTION": {
        "name": "kartado/ccr-production/databricks/credentials",
        "region": "sa-east-1",
    },
}

POWER_EMBEDDED_SECRETS = {
    "HOMOLOG": {
        "name": "kartado/homolog/power-embedded/credentials",
        "region": "us-east-1",
    },
    "PRODUCTION": {
        "name": "kartado/production/power-embedded/credentials",
        "region": "us-east-1",
    },
    "CCR_PRODUCTION": {
        "name": "kartado/ccr-production/power-embedded/credentials",
        "region": "sa-east-1",
    },
    "ENGIE_PRODUCTION": {
        "name": "kartado/engie-production/power-embedded/credentials",
        "region": "sa-east-1",
    },
}
