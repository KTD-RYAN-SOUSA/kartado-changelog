import uuid

from django.conf import settings
from django.template.loader import render_to_string
from simple_history.utils import bulk_create_with_history

from apps.companies.models import Company, UserInCompany
from apps.email_handler.models import QueuedEmail
from apps.notifications.models import Device, PushNotification, UserPush
from apps.users.models import User
from helpers.histories import bulk_update_with_history


def get_disclaimer(company_group):
    if company_group:
        disclaimer_msg = (
            company_group.metadata["disclaimer"]
            if "disclaimer" in company_group.metadata
            else ""
        )
        mobile_app = company_group.mobile_app
    else:
        disclaimer_msg = ""
        mobile_app = "undefined"

    return disclaimer_msg, mobile_app


def create_single_notification(
    user: User,
    company: Company,
    context: dict,
    template_path: str,
    push: bool = True,
    instance: object = None,
    url: str = "",
    extra_email: dict = {},
    user_notification: str = None,
    can_unsubscribe: bool = True,
    file_download: uuid.UUID = None,
    issuer: uuid.UUID = None,
    body: str = None,
):
    """
    Create a QueuedEmail for a notification and adds it to the notification queue.
    It's also possible to do the equivalent process for PushNotification if the push argument is True.

    Args:
        user (User): The recipient
        company (Company): The associated Company
        context (dict): Data provided to fill the templates
        template_path (str): The path to the template without the extension
        push (bool, optional): If the notification should also be sent on the app. Defaults to True.
        instance (object, optional): The content_object meant to relate the notification to the instance that triggered it. Defaults to None.
        url (str, optional): Url the mobile notification redirects to. Defaults to "".
        extra_email (dict, optional): Extra information that varies according to the specific notification. Defaults to {}.
        user_notification (str, optional): The UserNotification identifier for the unsubscribe URL. Defaults to None.
        can_unsubscribe (bool, optional): If that notification can be unsubscribed. Defaults to True.
    """

    user_in_company = UserInCompany.objects.filter(user=user, company=company).first()

    if not user_in_company or not user_in_company.is_active:
        return

    # Create unsubscribe URLs
    qe_uuid = uuid.uuid4()
    global_unsubscribe_url = (
        "{}/User/{}/Unsubscribe/?qe={}".format(
            settings.BACKEND_URL, str(user.pk), qe_uuid
        )
        if can_unsubscribe
        else None
    )
    usr_notif_config_url = (
        "{}/#/UserNotification/".format(settings.FRONTEND_URL)
        if can_unsubscribe and user_notification
        else None
    )
    usr_notif_unsubscribe_url = (
        "{}/User/{}/UnsubscribeUserNotification/?qe={}&un={}".format(
            settings.BACKEND_URL, str(user.pk), qe_uuid, user_notification
        )
        if can_unsubscribe and user_notification
        else None
    )

    context = {
        **context,
        "unsubscribe_url": global_unsubscribe_url,
        "usr_notif_config_url": usr_notif_config_url,
        "usr_notif_unsubscribe_url": usr_notif_unsubscribe_url,
    }

    # Update zip link to include token and email ID
    if file_download:
        zip_file_url = context["zip_file_url"]
        context["zip_file_url"] = f"{zip_file_url}?access_token={user.pk}&qe={qe_uuid}"

    # Create queued email
    # NOTE: If UserNotification instance, send email only if not sending
    # push since they are separate in this system.
    if user_notification is None or not push:
        # Render email text
        email_html_message = render_to_string(template_path + ".html", context)
        email_plaintext_message = render_to_string(template_path + ".txt", context)

        create_email_fields = {
            "title": context["title"],
            "content_plain_text": email_plaintext_message,
            "content_html": email_html_message,
            "company": company,
            "content_object": instance,
            "custom_headers": {
                "List-Unsubscribe": "<mailto: notification-unsubscribe@kartado.com.br?subject={} {}>, <{}>".format(
                    settings.BACKEND_URL, str(user.pk), global_unsubscribe_url
                )
            },
        }
        queue = QueuedEmail.objects.create(
            uuid=qe_uuid,
            file_download_id=file_download,
            issuer_id=issuer,
            **{**create_email_fields, **extra_email},
        )
        queue.send_to_users.add(user)
        queue.cleared = True
        bulk_update_with_history([queue], QueuedEmail, use_django_bulk=True)

    # Create queued push notifications
    if push:
        user_push_list = []
        push_devices = Device.objects.filter(device_users=user)

        create_push_fields = {
            "badge_count": 1,
            "context": "url_alert",
            "context_id": "none",
            "has_new_content": True,
            "message": context["title"],
            "body": body,
            "sound": "default",
            "company": company,
        }
        if url:
            create_push_fields["extra_payload"] = {"url": url}

        push = PushNotification.objects.create(**create_push_fields)
        push.devices.add(*push_devices)
        push.cleared = True
        push.save()

        user_push_list.append(UserPush(user=user, push_message=push))

        bulk_create_with_history(user_push_list, UserPush)


def create_notifications(
    send_to,
    company,
    context,
    template_path,
    push=True,
    instance=None,
    url="",
    extra_email={},
    user_notification: str = None,
    can_unsubscribe: bool = True,
    file_download: uuid.UUID = None,
    issuer: uuid.UUID = None,
    body: str = None,
):
    # Clear send_to
    send_to = list(set([user for user in send_to if user]))

    # Get disclaimer message and mobile_app type
    disclaimer_msg, mobile_app = get_disclaimer(company.company_group)
    context = {
        **context,
        "disclaimer": disclaimer_msg,
        "mobile_app": mobile_app,
    }

    for user in send_to:
        create_single_notification(
            user,
            company,
            context,
            template_path,
            push,
            instance,
            url,
            extra_email,
            user_notification,
            can_unsubscribe,
            file_download=file_download,
            issuer=issuer,
            body=body,
        )


def create_push_notifications(users, message, company, instance, url=None, body=None):
    for user in users:
        push_devices = Device.objects.filter(device_users=user)

        create_push_fields = {
            "badge_count": 1,
            "context": "url_alert",
            "context_id": "none",
            "has_new_content": True,
            "message": message,
            "body": body,
            "sound": "default",
            "company": company,
        }
        if url:
            create_push_fields["extra_payload"] = {"url": url}

        push = PushNotification.objects.create(**create_push_fields)
        push.devices.add(*push_devices)
        push.cleared = True
        push.save()

        UserPush.objects.create(user=user, push_message=push)


def create_password_notifications(
    send_to, context, template_path, add_disclaimer=False, company_group=None
):
    if add_disclaimer:
        disclaimer_msg, mobile_app = get_disclaimer(company_group)
        context = {
            **context,
            "disclaimer": disclaimer_msg,
            "mobile_app": mobile_app,
        }

    # Render email text
    email_plaintext_message = render_to_string(template_path + ".txt", context).replace(
        "&amp;", "&"
    )

    # Create queued email
    queue = QueuedEmail.objects.create(
        title=context["title"],
        content_plain_text=email_plaintext_message,
        content_object=send_to,
        send_anyway=True,
    )
    queue.send_to_users.add(send_to)
    queue.cleared = True
    queue.save()
