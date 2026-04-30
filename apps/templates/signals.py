import json
import uuid

from django.apps import apps
from django.conf import settings
from django.contrib.auth import signals as auth_signals
from django.db.models import signals
from django.dispatch import receiver

from helpers.middlewares import get_current_request, get_current_user
from helpers.signals import disable_signal_for_loaddata

from .models import ActionLog, CanvasCard, CanvasList


@receiver(signals.pre_save, sender=CanvasList)
def auto_fill_order_list(sender, instance, **kwargs):
    if instance._state.adding:
        try:
            latest_order = (
                CanvasList.objects.filter(service_order=instance.service_order)
                .latest()
                .order
            )
        except Exception:
            latest_order = 0

        instance.order = latest_order + 1


@receiver(signals.pre_save, sender=CanvasCard)
def auto_fill_order_card(sender, instance, **kwargs):
    if instance._state.adding:
        try:
            latest_order = (
                CanvasCard.objects.filter(canvas_list=instance.canvas_list)
                .latest()
                .order
            )
        except Exception:
            latest_order = 0

        instance.order = latest_order + 1


# ActionLog Signals
@disable_signal_for_loaddata
def user_logged_in(sender, request, user, **kwargs):
    try:
        remote_ip = getattr(request, "META", {}).get("REMOTE_ADDR", "")
        user_agent = getattr(request, "META", {}).get("HTTP_USER_AGENT", "")

        ActionLog.objects.create(
            company_group=user.company_group,
            user=user,
            action="Login",
            user_ip=remote_ip,
            user_agent=user_agent,
            content_object=user,
        )
    except Exception:
        pass


# ActionLog Signals
@disable_signal_for_loaddata
def post_save_action(sender, instance, created, raw, using, update_fields, **kwargs):
    try:
        company_id = None

        # return if loading Fixtures
        if raw:
            return

        # get request and user from middleware
        request = get_current_request()
        user = get_current_user()

        if not request or not user:
            return

        # get all models
        apps_names = list(map(lambda x: x.split(".")[-1], settings.APPS))
        models_dict = {
            item._meta.model_name: item
            for item in apps.get_models()
            if (item._meta.app_label in apps_names)
            and ("historical" not in item._meta.model_name)
            and ("actionlog" not in item._meta.model_name)
            and ("email" not in item._meta.model_name)
            and ("push" not in item._meta.model_name)
        }

        if (
            request.method in ["POST", "PATCH", "PUT"]
            and sender in models_dict.values()
            and not user.is_anonymous
        ):
            action_log = ""
            if getattr(request, "META", {}).get("HTTP_X_ORIGINAL_HEADERS", False):
                try:
                    original_headers = json.loads(
                        getattr(request, "META", {}).get("HTTP_X_ORIGINAL_HEADERS", {})
                    )
                except Exception:
                    original_headers = {}
                remote_ip = original_headers.get("remote_ip", "")
                user_agent = original_headers.get("user_agent", "")
            else:
                remote_ip = getattr(request, "META", {}).get("REMOTE_ADDR", "")
                user_agent = getattr(request, "META", {}).get("HTTP_USER_AGENT", "")

            if "python" in user_agent:
                return

            # get company_id
            try:
                possible_company_id = instance.get_company_id
            except Exception:
                pass
            else:
                if isinstance(possible_company_id, uuid.UUID):
                    company_id = possible_company_id

            # try again to get company_id
            if not company_id:
                try:
                    permission_classes = (
                        request.resolver_match.func.cls.permission_classes
                    )
                    view_actions = request.resolver_match.func.actions
                    action = view_actions[request.method.lower()]
                    permission_class = list(
                        filter(
                            lambda x: hasattr(x, "get_company_id"),
                            permission_classes,
                        )
                    )[0]()
                    get_company_id = permission_class.get_company_id(
                        action=action, request=request, obj=instance
                    )
                    if isinstance(get_company_id, uuid.UUID):
                        company_id = get_company_id
                except Exception:
                    pass

            # create ActionLog
            action_log = "Create" if created else "Update"
            content_object = instance if isinstance(instance.pk, uuid.UUID) else None

            ActionLog.objects.create(
                company_id=company_id,
                company_group=user.company_group,
                user=user,
                action=action_log,
                user_ip=remote_ip,
                user_agent=user_agent,
                content_object=content_object,
            )
    except Exception:
        pass


# ActionLog Signals
@disable_signal_for_loaddata
def post_delete_action(sender, instance, using, **kwargs):
    try:
        company_id = None

        # get request and user from middleware
        request = get_current_request()
        user = get_current_user()

        if not request or not user:
            return

        # get all models
        apps_names = list(map(lambda x: x.split(".")[-1], settings.APPS))
        models_dict = {
            item._meta.model_name: item
            for item in apps.get_models()
            if (item._meta.app_label in apps_names)
            and ("historical" not in item._meta.model_name)
            and ("actionlog" not in item._meta.model_name)
            and ("email" not in item._meta.model_name)
            and ("push" not in item._meta.model_name)
        }

        if (
            request.method == "DELETE"
            and sender in models_dict.values()
            and not user.is_anonymous
        ):
            if getattr(request, "META", {}).get("HTTP_X_ORIGINAL_HEADERS", False):
                try:
                    original_headers = json.loads(
                        getattr(request, "META", {}).get("HTTP_X_ORIGINAL_HEADERS", {})
                    )
                except Exception:
                    original_headers = {}
                remote_ip = original_headers.get("remote_ip", "")
                user_agent = original_headers.get("user_agent", "")
            else:
                remote_ip = getattr(request, "META", {}).get("REMOTE_ADDR", "")
                user_agent = getattr(request, "META", {}).get("HTTP_USER_AGENT", "")

            if "python" in user_agent:
                return

            # get company_id
            try:
                possible_company_id = instance.get_company_id
            except Exception:
                pass
            else:
                if isinstance(possible_company_id, uuid.UUID):
                    company_id = possible_company_id

            # try again to get company_id
            if not company_id:
                try:
                    permission_classes = (
                        request.resolver_match.func.cls.permission_classes
                    )
                    view_actions = request.resolver_match.func.actions
                    action = view_actions[request.method.lower()]
                    permission_class = list(
                        filter(
                            lambda x: hasattr(x, "get_company_id"),
                            permission_classes,
                        )
                    )[0]()
                    get_company_id = permission_class.get_company_id(
                        action=action, request=request, obj=instance
                    )
                    if isinstance(get_company_id, uuid.UUID):
                        company_id = get_company_id
                except Exception:
                    pass

            # create ActionLog
            content_object = instance if isinstance(instance.pk, uuid.UUID) else None

            ActionLog.objects.create(
                company_id=company_id,
                company_group=user.company_group,
                user=user,
                action="Delete",
                user_ip=remote_ip,
                user_agent=user_agent,
                content_object=content_object,
            )
    except Exception:
        pass


# connect ActionLog Signals
auth_signals.user_logged_in.connect(user_logged_in, dispatch_uid="action_log_logged_in")
signals.post_save.connect(post_save_action, dispatch_uid="action_log_post_save")
signals.post_delete.connect(post_delete_action, dispatch_uid="action_log_post_delete")
