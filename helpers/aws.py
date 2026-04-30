import json
import logging
import random
import string
from urllib.request import urlopen

import boto3
from botocore.exceptions import ClientError
from django.http import HttpResponse
from django.views.decorators.http import require_POST

from apps.email_handler.models import QueuedEmail, QueuedEmailEvent
from apps.notifications.models import PushNotification
from apps.notifications.services import sqs_notification_service
from RoadLabsAPI.settings import credentials
from RoadLabsAPI.settings.credentials import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_SESSION_TOKEN,
    DATABRICKS_SECRETS,
    FORMS_IA_SECRETS,
    POWER_EMBEDDED_SECRETS,
    SQL_CHAT_SECRETS,
)

logger = logging.getLogger(__name__)


def send_aws_metrics():
    """
    This function is called on a 5 minute rate by AWS SQS
    """

    # cloudwatch client setup
    cloudwatch = boto3.client(
        "cloudwatch",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        aws_session_token=AWS_SESSION_TOKEN,
        region_name="us-east-1",
    )

    # Emails
    unsent_emails = QueuedEmail.objects.filter(sent=False, cleared=True).count()
    error_emails = QueuedEmail.objects.filter(error=True).count()
    in_progress_emails = QueuedEmail.objects.filter(
        sent=False, in_progress=True
    ).count()

    # Send email data to cloudwatch
    cloudwatch.put_metric_data(
        Namespace="Email Metrics",
        MetricData=[
            {
                "MetricName": "Unsent Emails",
                "Unit": "Count",
                "Value": unsent_emails,
            },
            {
                "MetricName": "Error Emails",
                "Unit": "Count",
                "Value": error_emails,
            },
            {
                "MetricName": "In Progress Emails",
                "Unit": "Count",
                "Value": in_progress_emails,
            },
        ],
    )

    # Push Notifications
    unsent_pushs = PushNotification.objects.filter(sent=False, cleared=True).count()
    in_progress_pushs = PushNotification.objects.filter(
        sent=False, in_progress=True
    ).count()

    # Get SQS metrics
    sqs_metrics = sqs_notification_service.get_queue_metrics()

    # Prepare push notification metrics data
    push_metrics_data = [
        {
            "MetricName": "Unsent Pushs",
            "Unit": "Count",
            "Value": unsent_pushs,
        },
        {
            "MetricName": "In Progress Pushs",
            "Unit": "Count",
            "Value": in_progress_pushs,
        },
    ]

    # Add SQS metrics if available
    if sqs_metrics:
        push_metrics_data.extend(
            [
                {
                    "MetricName": "SQS Messages In Queue",
                    "Unit": "Count",
                    "Value": sqs_metrics.get("messages_in_queue", 0),
                },
                {
                    "MetricName": "SQS Messages In Flight",
                    "Unit": "Count",
                    "Value": sqs_metrics.get("messages_in_flight", 0),
                },
                {
                    "MetricName": "SQS Messages Delayed",
                    "Unit": "Count",
                    "Value": sqs_metrics.get("messages_delayed", 0),
                },
            ]
        )

    # Send push notification data to cloudwatch
    cloudwatch.put_metric_data(
        Namespace="Push Notification Metrics",
        MetricData=push_metrics_data,
    )


@require_POST
def email_events(request):
    """
    Using the handle_bounce function from django-ses
    as base for getting Open and Click email events
    """
    available_events = ["Click", "Open"]

    raw_json = request.body

    try:
        notification = json.loads(raw_json.decode("utf-8"))
    except Exception:
        return HttpResponse()

    notification_type = notification.get("Type", "")

    if notification_type in (
        "SubscriptionConfirmation",
        "UnsubscribeConfirmation",
    ):
        # Process the (un)subscription confirmation.
        # Get the subscribe url and hit the url to confirm the subscription.
        subscribe_url = notification.get("SubscribeURL", "")
        try:
            urlopen(subscribe_url).read()
        except Exception:
            pass

    if notification_type == "Notification":
        try:
            message = json.loads(notification["Message"])
            event_type = message.get("eventType")
            # Use the headers from email body to get QueuedEmail
            email_id = [
                item["value"]
                for item in message["mail"]["headers"]
                if (item["name"] == "X-KARTADO-ID" or item["name"] == "email_uuid")
            ]
            email = QueuedEmail.objects.filter(uuid__in=email_id)[0]
        except Exception:
            pass
        else:
            if event_type in available_events:
                try:
                    properties = message[event_type.lower()]
                except Exception:
                    properties = {}

                # Create QueuedEmailEvent object
                QueuedEmailEvent.objects.create(
                    queued_email=email,
                    company=email.company,
                    event_type=event_type,
                    properties=properties,
                )

    # AWS will consider anything other than 200 to be an error response and
    # resend the SNS request. We don't need that so we return 200 here.
    return HttpResponse()


def upload_to_s3(
    file_path: str,
    bucket_name: str,
    custom_filename: str = None,
    expires_days: int = 365,
) -> str:
    """
    Upload the file with the provided path to a S3 bucket and return the presigned URL.

    Args:
        file_path (str): The local path to the file that's going to be uploaded
        bucket_name (str): The name of the bucket to use for the upload
        custom_filename (str, optional): Custom filename to use inside the bucket. Defaults to the original filename.
        expires_days (int, optional): If you want the file to expire, provide a datetime of when. Defaults to 365 days.

    Returns:
        str: The presigned URL to the uploaded file.
    """

    # Initialize the s3 client
    s3 = boto3.client(
        "s3",
        aws_access_key_id=credentials.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=credentials.AWS_SECRET_ACCESS_KEY,
        aws_session_token=credentials.AWS_SESSION_TOKEN,
    )

    # Process the file name to avoid duplicates
    filename_with_ext = custom_filename or file_path.split("/")[-1]
    filename, extension = filename_with_ext.rsplit(".", 1)
    random_string = "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(7)
    )
    object_name = f"{filename}_{random_string}.{extension}"

    s3.upload_file(
        file_path,
        bucket_name,
        "media/private/" + object_name,
    )

    return object_name


def get_aws_secret(stage: str, secrets_config: dict) -> dict:
    """
    Retrieve credentials from AWS Secrets Manager based on environment.

    Args:
        stage (str): Environment (LOCAL, HOMOLOG, STAGING, PRODUCTION, CCR_PRODUCTION, ENGIE_PRODUCTION)
        secrets_config (dict): Configuration dict mapping stages to secret names and regions
                               (e.g., FORMS_IA_SECRETS, SQL_CHAT_SECRETS)

    Returns:
        dict: Dictionary containing the secret values

    Raises:
        ValueError: If the provided stage is invalid
        ClientError: If there's an error retrieving the secret from AWS
    """

    # LOCAL and STAGING use the same secret as HOMOLOG
    if stage in ("LOCAL", "STAGING"):
        stage = "HOMOLOG"

    if stage in ("ECO_PRODUCTION", "PRODUCTION"):
        stage = "PRODUCTION"

    if stage in ("ENGIE_STAGING", "ENGIE_PRODUCTION"):
        stage = "ENGIE_PRODUCTION"

    if stage in ("CCR_HOMOLOG", "CCR_PRODUCTION"):
        stage = "CCR_PRODUCTION"

    secret_config = secrets_config.get(stage)
    if not secret_config:
        error_msg = (
            f"Invalid stage: {stage}. Valid stages: {list(secrets_config.keys())}"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Create Secrets Manager client
    client = boto3.client(
        "secretsmanager",
        region_name=secret_config["region"],
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        aws_session_token=AWS_SESSION_TOKEN,
    )

    try:
        response = client.get_secret_value(SecretId=secret_config["name"])
        return json.loads(response["SecretString"])
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error(
            f"Error retrieving secret {secret_config['name']}: {error_code} - {str(e)}"
        )
        raise


def get_forms_ia_credentials(stage: str) -> dict:
    return get_aws_secret(stage, FORMS_IA_SECRETS)


def get_sql_chat_credentials(stage: str) -> dict:
    return get_aws_secret(stage, SQL_CHAT_SECRETS)


def get_databricks_credentials(stage: str) -> dict:
    return get_aws_secret(stage, DATABRICKS_SECRETS)


def get_power_embedded_credentials(stage: str) -> dict:
    return get_aws_secret(stage, POWER_EMBEDDED_SECRETS)
