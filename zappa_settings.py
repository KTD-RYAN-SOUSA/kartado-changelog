"""
Zappa Settings Module

This module loads the zappa_settings.json file and exposes it as Python module attributes.
This is required when using Docker images with Zappa, as the handler expects to import
settings as a Python module, but we have them in JSON format.

The Zappa handler will call: importlib.import_module("zappa_settings")
And expects to find attributes like settings_name, stage_config, etc.
"""

import json
import os

# Get the current environment from ZAPPA_ENVIRONMENT_NAME (set by Github pipeline)
# This variable is passed to the Zappa deploy/update command
STAGE = os.environ.get("ZAPPA_ENVIRONMENT_NAME")
if not STAGE:
    # Fallback: try to extract from Lambda function name if ZAPPA_ENVIRONMENT_NAME is not set
    lambda_function_name = os.environ.get("LAMBDA_FUNCTION_NAME", "")
    if lambda_function_name:
        parts = lambda_function_name.split("-")
        if len(parts) > 2:
            # Get the last meaningful parts and join with underscore
            STAGE = "_".join(parts[-2:]) if len(parts) > 2 else parts[-1]
            STAGE = STAGE.replace("-", "_")

# Load the zappa_settings.json file
settings_file = os.path.join(os.path.dirname(__file__), "zappa_settings.json")

with open(settings_file, "r") as f:
    _settings = json.load(f)

# If we can determine the stage, load that specific configuration
if STAGE and STAGE in _settings:
    stage_config = _settings[STAGE]

    # Expose stage configuration as module-level attributes
    for key, value in stage_config.items():
        # Convert JSON keys to Python attribute names (uppercase)
        attr_name = key.upper()
        globals()[attr_name] = value

    # Also keep the stage name
    STAGE_NAME = STAGE
else:
    # If we can't determine stage, just expose all settings
    # This shouldn't happen in Lambda, but helps with local testing
    ALL_SETTINGS = _settings
    STAGE_NAME = None

# Expose the raw settings dict for debugging
ZAPPA_SETTINGS = _settings

# Set default values for optional Zappa handler attributes
# These may not be in the JSON config, but Zappa handler expects them to exist

if "LOG_LEVEL" not in globals():
    LOG_LEVEL = None

if "REMOTE_ENV" not in globals():
    REMOTE_ENV = None

if "EXCEPTION_HANDLER" not in globals():
    EXCEPTION_HANDLER = None

if "CONTEXT_HEADER_MAPPINGS" not in globals():
    CONTEXT_HEADER_MAPPINGS = {}

if "DEBUG" not in globals():
    DEBUG = False

if "DJANGO_SETTINGS" not in globals():
    DJANGO_SETTINGS = None

if "AWS_REGION" not in globals():
    AWS_REGION = "us-east-1"

if "PROJECT_NAME" not in globals():
    PROJECT_NAME = None

if "API_STAGE" not in globals():
    API_STAGE = STAGE_NAME

if "ENVIRONMENT_VARIABLES" not in globals():
    ENVIRONMENT_VARIABLES = {}

if "BINARY_SUPPORT" not in globals():
    BINARY_SUPPORT = True  # Enable binary support by default for API Gateway

if "ADDITIONAL_TEXT_MIMETYPES" not in globals():
    ADDITIONAL_TEXT_MIMETYPES = None

# Event and authorization related attributes
if "AUTHORIZER_FUNCTION" not in globals():
    AUTHORIZER_FUNCTION = None

if "AWS_EVENT_MAPPING" not in globals():
    AWS_EVENT_MAPPING = {}

if "AWS_BOT_EVENT_MAPPING" not in globals():
    AWS_BOT_EVENT_MAPPING = {}

if "COGNITO_TRIGGER_MAPPING" not in globals():
    COGNITO_TRIGGER_MAPPING = {}

# DO NOT set APP_MODULE or APP_FUNCTION if they don't exist in the JSON
# Zappa uses hasattr() to check for these, and will try to import them if they exist
# even if the value is None, which will cause errors.
# For Django applications, these should not be set at all.
