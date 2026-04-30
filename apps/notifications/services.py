import json
import logging
from typing import Dict, Optional

import boto3
import sentry_sdk
from django.conf import settings
from django.utils import timezone

from RoadLabsAPI.settings import credentials


class SQSNotificationService:
    """
    Service to handle SQS operations for push notifications.
    Implements the event-driven architecture for notification processing.
    """

    def __init__(self):
        self.sqs_client = None
        self.queue_url = getattr(settings, "SQS_PUSH_NOTIFICATIONS_QUEUE_URL", "")
        self.dlq_url = getattr(settings, "SQS_PUSH_NOTIFICATIONS_DLQ_URL", "")
        self.enabled = getattr(credentials, "SQS_ENABLED", False)
        self._initialize_client()

    def _initialize_client(self):
        """Initialize SQS client with AWS credentials"""
        if not self.enabled:
            logging.info("SQS is disabled. Skipping client initialization.")
            return

        try:
            self.sqs_client = boto3.client(
                "sqs",
                aws_access_key_id=credentials.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=credentials.AWS_SECRET_ACCESS_KEY,
                aws_session_token=credentials.AWS_SESSION_TOKEN,
                region_name=getattr(settings, "SQS_REGION", "us-east-1"),
            )
            logging.info("SQS client initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize SQS client: {str(e)}")
            sentry_sdk.capture_exception(e)
            self.enabled = False

    def publish_notification(
        self, notification_id: int, company_id: Optional[int] = None
    ) -> bool:
        """
        Publish a push notification to SQS queue.

        Args:
            notification_id (int): ID of the PushNotification to process
            company_id (Optional[int]): Company ID for additional context

        Returns:
            bool: True if successfully published, False otherwise
        """
        if not self.enabled or not self.sqs_client:
            logging.warning(
                "SQS is disabled or client not initialized. Skipping publish."
            )
            return False

        try:
            message_body = {
                "notification_id": notification_id,
                "company_id": company_id,
                "created_at": str(settings.USE_TZ and timezone.now() or timezone.now()),
                "retry_count": 0,
            }

            # Add message attributes for better filtering and routing
            message_attributes = {
                "notification_type": {
                    "StringValue": "push_notification",
                    "DataType": "String",
                },
                "notification_id": {
                    "StringValue": str(notification_id),
                    "DataType": "String",
                },
            }

            if company_id:
                message_attributes["company_id"] = {
                    "StringValue": str(company_id),
                    "DataType": "String",
                }

            # Prepare message parameters
            message_params = {
                "QueueUrl": self.queue_url,
                "MessageBody": json.dumps(message_body),
                "MessageAttributes": message_attributes,
            }

            # Add MessageGroupId only for FIFO queues
            if self.queue_url.endswith(".fifo"):
                message_params["MessageGroupId"] = f"notification_{notification_id}"

            response = self.sqs_client.send_message(**message_params)

            logging.info(
                f"Successfully published notification {notification_id} to SQS. MessageId: {response.get('MessageId')}"
            )
            return True

        except Exception as e:
            logging.error(
                f"Failed to publish notification {notification_id} to SQS: {str(e)}"
            )
            sentry_sdk.capture_exception(e)
            return False

    def get_queue_metrics(self) -> Dict[str, int]:
        """
        Get queue metrics for monitoring.

        Returns:
            Dict with queue metrics
        """
        if not self.enabled or not self.sqs_client:
            return {}

        try:
            response = self.sqs_client.get_queue_attributes(
                QueueUrl=self.queue_url,
                AttributeNames=[
                    "ApproximateNumberOfMessages",
                    "ApproximateNumberOfMessagesNotVisible",
                    "ApproximateNumberOfMessagesDelayed",
                ],
            )

            attributes = response.get("Attributes", {})
            return {
                "messages_in_queue": int(
                    attributes.get("ApproximateNumberOfMessages", 0)
                ),
                "messages_in_flight": int(
                    attributes.get("ApproximateNumberOfMessagesNotVisible", 0)
                ),
                "messages_delayed": int(
                    attributes.get("ApproximateNumberOfMessagesDelayed", 0)
                ),
            }

        except Exception as e:
            logging.error(f"Failed to get queue metrics: {str(e)}")
            sentry_sdk.capture_exception(e)
            return {}


# Global instance to be used across the application
sqs_notification_service = SQSNotificationService()
