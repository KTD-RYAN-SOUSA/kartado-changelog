import logging

from django_bulk_update.helper import bulk_update

from apps.users.models import UserNotification
from helpers.apps.users import queue_debounced_user_notification


def generate_debounced_notifications():
    """
    Generate notifications from UserNotification debounce

    This function is called on a 1 minute rate by AWS SQS
    """

    logging.info(
        "generate_debounced_notifications: Starting to queue debounced notifications"
    )

    MAX_NOTIF = 10  # Max per minute

    usr_notifs = UserNotification.objects.filter(
        in_progress=False, debounce_data__isnull=False
    ).order_by("last_checked")[:MAX_NOTIF]

    # Done to avoid QuerySet lazy loading hiding items after flag change
    usr_notifs_queue = list(usr_notifs)

    # Set all of the selected notifications for this call as in progress to avoid duplicate executions
    # NOTE: .update() cannot be used on slices of QuerySets
    for user_notif in usr_notifs_queue:
        user_notif.in_progress = True
    bulk_update(usr_notifs_queue, update_fields=["in_progress"])

    # Process the notification
    upd_usr_notifs = []
    for user_notif in usr_notifs_queue:
        upd_usr_notif = queue_debounced_user_notification(user_notif)
        upd_usr_notifs.append(upd_usr_notif)

    bulk_update(
        usr_notifs_queue,
        update_fields=["debounce_data", "last_notified", "last_checked", "in_progress"],
    )

    logging.info(
        f"generate_debounced_notifications: Finished queueing of {len(usr_notifs_queue)} notifications"
    )
