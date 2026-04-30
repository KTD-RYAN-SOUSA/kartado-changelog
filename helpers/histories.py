import copy

from django.apps import apps
from django.db import transaction
from django.utils.timezone import now
from django_bulk_update.helper import bulk_update
from rest_framework_json_api import serializers
from simple_history.utils import (
    get_change_reason_from_object,
    get_history_manager_for_model,
)


def get_histories_by_apps(app_name):
    """
    This function returns number of histories entries per model in app
    """
    result = {}
    models_by_app = list(apps.all_models[app_name])
    models_names = [
        model
        for model in models_by_app
        if "historical" not in model
        if "_" not in model
    ]
    for item in models_names:
        model = apps.get_model(app_label=app_name, model_name=item)
        result[item] = len(model.history.all())

    result["total"] = sum(result.values())
    return result


def as_of(app_label, model_name, datetime):
    """
    This function returns objects as_of certain date
    """
    model = apps.get_model(app_label=app_label, model_name=model_name)
    pk_attr = model._meta.pk.name
    historical_model = model.history.model

    history = historical_model.objects.filter(history_date__lte=datetime)

    all_ids = history.values_list(pk_attr)
    remove_ids = history.filter(history_type="-").values_list(pk_attr)
    accept_ids = all_ids.difference(remove_ids)

    history_final = (
        history.filter(**{pk_attr + "__in": accept_ids})
        .order_by(pk_attr, "-history_date")
        .distinct(pk_attr)
    )

    return history_final


def bulk_update_with_history(
    objs, model, use_django_bulk=False, batch_size=None, user=None, **kwargs
):
    """
    Bulk update the objects specified by objs while also bulk creating
    their history (all in one transaction).
    :param objs: List of objs (not yet saved to the db) of type model
    :param model: Model class that should be created
    :param use_django_bulk: Boolean signal to specify type of update (explained below)
    :param batch_size: Number of objects that should be updated in each batch
    :return: List of objs with IDs

    There are two types of updates:
    - 1) Queryset of objects that are gonna update the same fields with the same values.
        for all objects. This type uses .update()
    - 2) Queryset of objects that are gonna update the same fields with different values
        for each object.
        This type needs to use bulk_update from django_bulk_update.helper
    """

    history_manager = get_history_manager_for_model(model)
    history_model = history_manager.model
    original_objs = copy.copy(objs)

    with transaction.atomic(savepoint=False):
        if use_django_bulk:
            bulk_update(objs, batch_size=batch_size)
        else:
            original_objs.update(**kwargs)
        objs_with_id = model.objects.filter(pk__in=[a.pk for a in objs])
        bulk_history_create(
            history_model,
            objs_with_id,
            history_type="~",
            history_user=user,
            batch_size=batch_size,
        )

    return objs_with_id


def bulk_history_create(
    model, objs, history_type="+", history_user=None, batch_size=None
):
    """
    Bulk create the history for the objects specified by objs
    """

    historical_instances = [
        model(
            history_date=getattr(instance, "_history_date", now()),
            history_user=getattr(instance, "_history_user", history_user),
            history_change_reason=get_change_reason_from_object(instance) or "",
            history_type=history_type,
            **{
                field.attname: getattr(instance, field.attname)
                for field in instance._meta.fields
                if field.name not in model._history_excluded_fields
            }
        )
        for instance in objs
    ]
    if historical_instances:
        if "history_relation_id" in historical_instances[0].__dict__.keys():
            for item in historical_instances:
                item.history_relation_id = item.pk

    return model.objects.bulk_create(historical_instances, batch_size=batch_size)


def add_history_change_reason(instance, initial_data):
    """
    Helper to allow serializer changes to also record the reason the change happened
    on the history.
    """
    change_reason = initial_data.get("history_change_reason", None)
    if change_reason and isinstance(change_reason, str):
        hist = instance.history.first()
        hist.history_change_reason = change_reason
        hist.save()


class HistoricalRecordField(serializers.ListField):
    """
    Field used to create history serializer
    """

    child = serializers.DictField()

    def to_representation(self, data):
        return super(HistoricalRecordField, self).to_representation(data.values())
