#!/usr/bin/env python
import os
import sys

from decouple import config

if "SERVERTYPE" in os.environ and os.environ["SERVERTYPE"] == "AWS Lambda":
    import json
    import os

    json_data = open("zappa_settings.json")
    env_vars = json.load(json_data)["development"]["environment_variables"]
    for key, val in env_vars.items():
        os.environ[key] = val

if __name__ == "__main__":
    # Set settings according to environment
    stage = config("STAGE", default="LOCAL")

    if stage == "STAGING":
        django_settings = "RoadLabsAPI.settings.staging"
    elif stage == "HOMOLOG":
        django_settings = "RoadLabsAPI.settings.homolog"
    elif stage == "PRODUCTION":
        django_settings = "RoadLabsAPI.settings.production"
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
    try:
        from django.core.management import execute_from_command_line

    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    execute_from_command_line(sys.argv)
