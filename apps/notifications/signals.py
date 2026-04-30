import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.notifications.models import PushNotification
from apps.notifications.services import sqs_notification_service
from helpers.signals import disable_signal_for_loaddata


@receiver(post_save, sender=PushNotification)
@disable_signal_for_loaddata
def publish_push_notification_to_sqs(sender, instance, **kwargs):
    """
    Signal handler to publish push notifications to SQS when cleared.
    This ensures near real-time processing.
    """
    # Skip if not cleared or already sent
    if not instance.cleared or instance.sent:
        return

    try:
        company_id = str(instance.company.uuid) if instance.company else None
        success = sqs_notification_service.publish_notification(
            notification_id=instance.id, company_id=company_id
        )

        if success:
            logging.info(
                f"Successfully published PushNotification {instance.id} to SQS"
            )
        else:
            logging.warning(f"Failed to publish PushNotification {instance.id} to SQS")

    except Exception as e:
        logging.error(
            f"Error publishing PushNotification {instance.id} to SQS: {str(e)}"
        )
        # Don't raise the exception to avoid breaking the normal save flow
        # The notification will still be processed by the fallback polling system
