import hashlib
import json
from collections import defaultdict
from contextlib import contextmanager
from functools import wraps
from typing import Union
from unittest import mock

from django.conf import settings
from django.db.models import signals
from django.db.models.signals import (
    post_delete,
    post_init,
    post_migrate,
    post_save,
    pre_delete,
    pre_init,
    pre_migrate,
    pre_save,
)
from rest_framework_json_api import serializers

from apps.companies.models import Company
from apps.occurrence_records.models import OccurrenceRecordWatcher
from apps.service_orders.models import ServiceOrderWatcher
from apps.users.models import UserNotification
from helpers.apps.users import add_debounce_data
from helpers.route_maker import Router
from helpers.strings import get_autonumber_array
from RoadLabsAPI.settings.credentials import GMAPS_API_KEY, MAPBOX_API_KEY


def prevent_signal(signal_name, signal_fn, sender):
    def wrap(fn):
        def wrapped_fn(*args, **kwargs):
            signal = getattr(signals, signal_name)
            signal.disconnect(signal_fn, sender)
            fn(*args, **kwargs)
            signal.connect(signal_fn, sender)

        return wrapped_fn

    return wrap


@contextmanager
def catch_signal(signal):
    """Catch django signal and return the mocked call."""
    handler = mock.Mock()
    signal.connect(handler)
    yield handler
    signal.disconnect(handler)


def disable_signal_for_loaddata(signal_handler):
    """
    Decorator that turns off signal handlers when loading fixture data.
    """

    @wraps(signal_handler)
    def wrapper(*args, **kwargs):
        if kwargs.get("raw"):
            return None

        signal_handler(*args, **kwargs)

    return wrapper


class DisableSignals(object):
    def __init__(self, disabled_signals=None):
        self.stashed_signals = defaultdict(list)
        self.disabled_signals = disabled_signals or [
            pre_init,
            post_init,
            pre_save,
            post_save,
            pre_delete,
            post_delete,
            pre_migrate,
            post_migrate,
        ]

    def __enter__(self):
        for signal in self.disabled_signals:
            self.disconnect(signal)

    def __exit__(self, exc_type, exc_val, exc_tb):
        for signal in list(self.stashed_signals):
            self.reconnect(signal)

    def disconnect(self, signal):
        self.stashed_signals[signal] = signal.receivers
        signal.receivers = []

    def reconnect(self, signal):
        signal.receivers = self.stashed_signals.get(signal, [])
        del self.stashed_signals[signal]


def history_dont_save_geometry_changes(history_instance):
    try:
        geometry_hash_str = history_instance.geometry.__str__()
        geometry_hash = hashlib.md5(geometry_hash_str.encode()).hexdigest()
    except Exception:
        pass
    else:
        history_instance.geometry_hash = geometry_hash
        history_instance.geometry = None


def generic_fill_km_field(instance, company):
    """
    Automate km field on occurrence_records, using a key of damCoordinates on the
    company metadata and the point field.
    """
    fill_km = False

    if instance.point:
        if "damCoordinates" in company.metadata:
            if instance._state.adding:
                fill_km = True
            else:
                previous = instance._meta.model.objects.get(pk=instance.pk)
                if previous.point != instance.point:
                    fill_km = True

    if fill_km:
        marks = {}
        marks["0"] = company.metadata["damCoordinates"]
        marks["1"]["point"] = json.loads(instance.point.json)
        route = Router(GMAPS_API_KEY, MAPBOX_API_KEY)
        route.set_marks(marks)
        route.make_route()

        instance.distance_from_dam = route.length / 1000


def auto_add_number(instance, key_name):
    """
    Automatically fills the `number` field using the proper name formats.
    """

    if instance.number in [None, ""]:
        if hasattr(instance, "occurrence_type") and instance.occurrence_type:
            try:
                occurrence_kind = instance.occurrence_type.occurrence_kind
            except Exception:
                raise serializers.ValidationError(
                    "kartado.error.occurrence_type.occurrence_kind_not_found"
                )
        else:
            occurrence_kind = ""

        number_format = ""

        company = None
        if hasattr(instance, "get_company_id"):
            company_id = instance.get_company_id
            company = Company.objects.get(pk=company_id)
        elif hasattr(instance, "company"):
            company = instance.company

        if company and key_name in company.metadata:
            try:
                number_format = company.metadata[key_name][occurrence_kind]
            except Exception:
                if "default" in company.metadata[key_name]:
                    number_format = company.metadata[key_name]["default"]
                else:
                    raise serializers.ValidationError(
                        "kartado.error.company.invalid_variable_names"
                    )
        else:
            raise serializers.ValidationError(
                "kartado.error.company.invalid_variable_names"
            )

        try:
            instance_type = number_format["type"]
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.company.invalid_variable_names"
            )

        # Get datetime and serial arrays
        data = get_autonumber_array(company.uuid, instance_type)

        # Get company prefix
        if "company_prefix" in company.metadata:
            data["prefixo"] = company.metadata["company_prefix"]
        else:
            data["prefixo"] = "[{}]".format(company.name)

        # Make number
        try:
            number = number_format["format"].format(**data)
        except Exception as e:
            print(e)
            # Fallback
            # UHIT-RG-2018.0001
            number = "{prefixo}-{nome}-{anoCompleto}.{serialAno}".format(**data)

        instance.number = number


def watcher_email_notification(
    notification_area: str,
    watcher_instance: Union[OccurrenceRecordWatcher, ServiceOrderWatcher],
    created: bool,
):
    """
    Determine if watcher creation needs to trigger a new notification
    for the related users and debounces the notification data if true.

    Does not group results of multiple Company instances.

    Args:
        notification_area (str): Which notification is going to be sent.
        watcher_instance (Union[OccurrenceRecordWatcher, ServiceOrderWatcher]): Watcher instance.
        created (bool): If the instance was just created or not.

    Raises:
        NotImplementedError: Raised when unsupported watcher is provided.
    """

    if created and watcher_instance.status_email:
        # Determine type of watcher
        if isinstance(watcher_instance, OccurrenceRecordWatcher):
            watched_instance = watcher_instance.occurrence_record
            url_template = "{}/#/SharedLink/OccurrenceRecord/{}/show?company={}"
            watcher_url_template = "{}/OccurrenceRecordWatcher/{}/Status/"
            watched_instance_name = "Registro"
        elif isinstance(watcher_instance, ServiceOrderWatcher):
            watched_instance = watcher_instance.service_order
            url_template = "{}/#/SharedLink/ServiceOrder/{}/show?company={}"
            watcher_url_template = "{}/ServiceOrderWatcher/{}/Status/"
            watched_instance_name = "Serviço"
        else:
            raise NotImplementedError("No supported watcher was provided")

        # Extract initial data
        company = watched_instance.company
        reg_number = watched_instance.number
        created_by = (
            watcher_instance.created_by.get_full_name()
            if watcher_instance.created_by
            else ""
        )

        # Create URLs
        url = url_template.format(
            settings.FRONTEND_URL, str(watched_instance.uuid), str(company.uuid)
        )
        url_watcher = watcher_url_template.format(
            settings.BACKEND_URL, str(watcher_instance.uuid)
        )

        debounce_data = {
            "url_watcher": url_watcher,
            "url": url,
            "watcher_instance_id": str(watcher_instance.pk),
            "company_id": str(company.pk),
        }

        if watcher_instance.user:
            debounce_data.update(
                {
                    "message": f"Você está recebendo este e-mail porque {created_by} adicionou você "
                    f"à lista de usuários notificados sobre o {watched_instance_name} {reg_number}"
                }
            )
            user_notifs = UserNotification.objects.filter(
                notification=notification_area,
                user=watcher_instance.user,
                companies=company,
            ).only("debounce_data")
            add_debounce_data(
                user_notifs, debounce_data, dedup_key="watcher_instance_id"
            )

        if watcher_instance.firm and watcher_instance.firm.users.exists():
            # Remove instance.user because he was already notified individually in
            # the previous condition (if instance.user is filled).
            if watcher_instance.user:
                firm_users = watcher_instance.firm.users.all().exclude(
                    uuid=watcher_instance.user.uuid
                )
            else:
                firm_users = watcher_instance.firm.users.all()

            firm_name = watcher_instance.firm.name.strip()
            debounce_data.update(
                {
                    "message": f"Você está recebendo este e-mail porque {created_by} adicionou a equipe {firm_name} "
                    f"à lista de equipes notificadas sobre o {watched_instance_name} {reg_number}",
                }
            )
            user_notifs = UserNotification.objects.filter(
                notification=notification_area,
                user__in=firm_users,
                companies=company,
            ).only("debounce_data")
            add_debounce_data(
                user_notifs, debounce_data, dedup_key="watcher_instance_id"
            )


def auto_add_job_number(company):
    instance_type = "job"
    key_name = "{}_name_format".format(instance_type)
    # Get datetime and serial arrays
    data = get_autonumber_array(company.uuid, instance_type)
    # Get company prefix
    if "company_prefix" in company.metadata:
        data["prefixo"] = company.metadata["company_prefix"]
    else:
        data["prefixo"] = "[{}]".format(company.name)
    # Make number
    try:
        if key_name in company.metadata:
            number = company.metadata[key_name].format(**data)
        else:
            raise Exception("Variáveis de nome inválidas!")
    except Exception as e:
        print(e)
        # Fallback
        # UHIT-job-2018.0001
        number = "{prefixo}-{nome}-{anoCompleto}.{serialAno}".format(**data)

    return number
