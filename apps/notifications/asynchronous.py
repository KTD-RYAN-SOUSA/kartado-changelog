import json
import logging
import time

import psycopg2
import sentry_sdk
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.utils import timezone
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from apps.notifications.strategies.firebase import FirebaseNotificationService
from helpers.histories import bulk_update_with_history
from RoadLabsAPI.settings import credentials

from .models import Notification, PushNotification, UserPush


def send_queued_notifications(model_class):
    """
    Process queued notifications for any model inheriting from Notification.
    Supports custom initialization like Firebase for push notifications.
    """
    if not isinstance(model_class, type):
        raise TypeError(
            f"Expected a class type, got instance of '{type(model_class).__name__}'."
        )

    if not issubclass(model_class, Notification):
        raise TypeError(f"{model_class.__name__} must be a subclass of Notification.")

    MAX_NOTIFICATIONS = 30

    qs = model_class.objects.filter(
        sent=False, in_progress=False, cleared=True
    ).order_by("created_at")[:MAX_NOTIFICATIONS]

    queue = list(qs)
    queue_pks = qs.values_list("pk", flat=True)

    # Mark in progress
    bulk_update_with_history(
        objs=model_class.objects.filter(pk__in=queue_pks),
        model=model_class,
        in_progress=True,
    )

    # Init context
    context = {}

    if hasattr(model_class, "requires_firebase") and model_class.requires_firebase:
        FIREBASE_CREDENTIALS_BASE64 = credentials.FIREBASE_CREDENTIALS_BASE64
        context["firebase_token"] = FirebaseNotificationService.initialize(
            firebase_credentials_base64=FIREBASE_CREDENTIALS_BASE64
        )

    # Process each notification
    for notification in queue:
        notification.process(**context)


def process_sqs_push_notification(event, context):
    """
    Process push notifications from SQS events.

    This function is triggered by SQS messages containing notification IDs.
    It processes notifications one by one, ensuring idempotency and proper error handling.

    Args:
        event: AWS Lambda event containing SQS messages
        context: AWS Lambda context (unused)
    """
    processed_count = 0
    failed_count = 0

    # Initialize Firebase token once for all notifications in this batch
    firebase_context = {}
    try:
        FIREBASE_CREDENTIALS_BASE64 = credentials.FIREBASE_CREDENTIALS_BASE64
        firebase_context["firebase_token"] = FirebaseNotificationService.initialize(
            firebase_credentials_base64=FIREBASE_CREDENTIALS_BASE64
        )
    except Exception as e:
        logging.error(f"Failed to initialize Firebase: {str(e)}")
        sentry_sdk.capture_exception(e)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to initialize Firebase"}),
        }

    # Process each SQS record
    for record in event.get("Records", []):
        try:
            # Parse message body
            message_body = json.loads(record["body"])
            notification_id = message_body.get("notification_id")

            if not notification_id:
                logging.warning(f"Missing notification_id in SQS message: {record}")
                failed_count += 1
                continue

            # Get the notification from database
            try:
                notification = PushNotification.objects.get(id=notification_id)
            except PushNotification.DoesNotExist:
                logging.warning(f"PushNotification {notification_id} not found")
                failed_count += 1
                continue

            # Check if already processed (idempotency)
            if notification.sent:
                logging.info(
                    f"PushNotification {notification_id} already sent, skipping"
                )
                processed_count += 1
                continue

            # Check if notification is ready to be processed
            if not notification.cleared or notification.in_progress:
                logging.info(
                    f"PushNotification {notification_id} not ready for processing"
                )
                continue

            # Mark as in progress to prevent duplicate processing
            notification.in_progress = True
            notification.save(update_fields=["in_progress"])

            # Process the notification
            try:
                notification.process(**firebase_context)
                processed_count += 1
                logging.info(
                    f"Successfully processed PushNotification {notification_id}"
                )
            except Exception as e:
                logging.error(
                    f"Failed to process PushNotification {notification_id}: {str(e)}"
                )
                sentry_sdk.capture_exception(e)

                # Reset in_progress flag so it can be retried
                notification.in_progress = False
                notification.save(update_fields=["in_progress"])
                failed_count += 1

        except Exception as e:
            logging.error(f"Error processing SQS record: {str(e)}")
            sentry_sdk.capture_exception(e)
            failed_count += 1

    # Log summary
    total_records = len(event.get("Records", []))
    logging.info(
        f"SQS processing summary: {processed_count} processed, {failed_count} failed, {total_records} total"
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "processed": processed_count,
                "failed": failed_count,
                "total": total_records,
            }
        ),
    }


def send_queued_push_notifications():
    """
    Fallback function for processing push notifications via polling.

    This function is kept for backward compatibility and as a safety net
    in case the SQS-based processing fails.
    """
    send_queued_notifications(PushNotification)


def delete_old_queued_push():

    start_time = time.perf_counter()
    OBJECT_LIMIT = 20000
    queued_qs_len = 0
    user_qs_len = 0

    now = timezone.now()
    six_months_ago = now - relativedelta(months=6)
    db = settings.DATABASES["default"]
    conn = psycopg2.connect(
        user=db["USER"],
        password=db["PASSWORD"],
        database=db["NAME"],
        host=db["HOST"],
        port=db["PORT"],
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    qs = PushNotification.objects.filter(
        in_progress=False, sent=True, created_at__lt=six_months_ago
    ).order_by("created_at")[:OBJECT_LIMIT]
    if qs.exists():

        user_qs = UserPush.objects.filter(push_message__in=qs)

        if user_qs.exists():
            new_qs = tuple(user_qs.values_list("uuid", flat=True))
            user_qs_len = len(new_qs)
            s_list = ""
            for item in range(user_qs_len):
                s_list += "%s, "
            cur.execute(
                f"DELETE FROM notifications_userpush WHERE notifications_userpush.uuid IN ({s_list[:-2]}) ;",
                [*new_qs],
            )

        new_qs = tuple(
            PushNotification.objects.filter(pk__in=qs).values_list("id", flat=True)
        )

        queued_qs_len = len(new_qs)
        s_list = ""
        for item in range(queued_qs_len):
            s_list += "%s, "

        cur.execute(
            f"DELETE FROM notifications_pushnotification_devices WHERE notifications_pushnotification_devices.pushnotification_id ({s_list[:-2]}) ;",
            [*new_qs],
        )

        cur.execute(
            f"DELETE FROM notifications_pushnotification WHERE notifications_pushnotification.id IN ({s_list[:-2]}) ;",
            [*new_qs],
        )

    end_time = time.perf_counter()
    logging.info(
        f"{str(round(end_time - start_time, 3))} seconds elapsed and {str(queued_qs_len + user_qs_len)} objects deleted"
    )

    conn.close()
