import json

import sentry_sdk
from django.utils import timezone
from requests.models import PreparedRequest, Response

from apps.companies.models import Company
from apps.users.models import User


def log_api_usage(
    api_name: str,
    company: Company,
    user: User,
    response: Response,
):
    """
    Log the usage of a supported API for expense analysis.

    WARN: This helper assumes a UTF-8 encoded JSON serializable body.

    Args:
        api_name (str): Name of the API being logged
        company (Company): Company related to the usage
        user (User): User related to the usage
        response (Response): Response object returned by the API call

    Raises:
        AssertionError: Raised when the provided API name doesn't match any in the supported list
    """

    # To fix circular import :(
    from apps.templates.models import Log

    SUPPORTED_APIS = ["TESSADEM"]

    # To ensure uniformity
    api_name_upper = api_name.upper()

    # Ensure the api_name is supported
    assert api_name_upper in SUPPORTED_APIS, "Please provide a supported api name"

    request: PreparedRequest = response.request
    company_id = str(company.pk)
    user_id = str(user.pk)

    # Attempt to decode both the input and output
    request_body = json.loads(request.body.decode()) if request.body else None
    response_body = json.loads(response.content.decode()) if response.content else None

    log_fields = {
        "company": company,
        "date": timezone.now(),
        "description": {
            "company_uuid": company_id,
            "user_uuid": user_id,
            "type": api_name_upper,
            "request": {
                "type": request.method,
                "url": request.url,
                "body": request_body,
            },
            "response": {
                "body": response_body,
                "headers": dict(response.headers) if response.headers else None,
                "status_code": response.status_code,
            },
        },
    }

    # Create the log with the structured data
    try:
        Log.objects.create(**log_fields)
    except Exception as e:
        # Capture without blocking the API call
        sentry_sdk.capture_exception(e)
