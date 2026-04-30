"""
WSGI config for RoadLabsAPI project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/2.0/howto/deployment/wsgi/
"""

import os

from decouple import config
from django.core.wsgi import get_wsgi_application

# Set settings according to environment
stage = config("STAGE", default="LOCAL")

if stage == "STAGING":
    django_settings = "RoadLabsAPI.settings.staging"
elif stage == "PRODUCTION":
    django_settings = "RoadLabsAPI.settings.production"
elif stage == "HOMOLOG":
    django_settings = "RoadLabsAPI.settings.homolog"
elif stage == "ENGIE_STAGING":
    django_settings = "RoadLabsAPI.settings.engie.staging"
elif stage == "ENGIE_PRODUCTION":
    django_settings = "RoadLabsAPI.settings.engie.production"
elif stage == "CCR_HOMOLOG":
    django_settings = "RoadLabsAPI.settings.ccr.homolog"
elif stage == "CCR_PRODUCTION":
    django_settings = "RoadLabsAPI.settings.ccr.production"
elif stage == "LOCAL":
    django_settings = "RoadLabsAPI.settings.development"
else:
    raise (Exception("Unknown env!"))


os.environ.setdefault("DJANGO_SETTINGS_MODULE", django_settings)

application = get_wsgi_application()
