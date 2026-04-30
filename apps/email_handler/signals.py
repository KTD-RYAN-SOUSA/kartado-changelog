from django.dispatch import receiver
from django_ses.signals import bounce_received

from .models import EmailBlacklist


@receiver(bounce_received)
def bounce_handler(sender, *args, **kwargs):
    """
    bounce_obj example:
    https://docs.aws.amazon.com/ses/latest/DeveloperGuide/notification-contents.html#bounce-object
    """
    bounce_obj = kwargs.get("bounce_obj")
    recipients = bounce_obj.get("bouncedRecipients")
    for recipient in recipients:
        try:
            EmailBlacklist.objects.create(
                email=recipient["emailAddress"],
                reason=recipient.get("diagnosticCode", ""),
            )
        except Exception:
            pass
