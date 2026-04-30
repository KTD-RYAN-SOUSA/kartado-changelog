from datetime import datetime

from django.apps import apps


def as_of(app_label, model_name, datetime):
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


def first_histories(app_label, model_name, queryset):
    # model and history_model
    model = apps.get_model(app_label=app_label, model_name=model_name)
    historical_model = model.history.model

    queryset_ids = queryset.values_list("uuid", flat=True)
    history = historical_model.objects.values_list("history_date", "uuid", "pk")
    objects_ids = list(set([item[1] for item in history if item[1] in queryset_ids]))

    # initialize dict with datetime now
    dates = {item: datetime.now() for item in objects_ids}

    # get oldest history by uuid and save history_id in pks dict
    pks = dict()
    for item in history:
        if item[1] in queryset_ids:
            if item[0].replace(tzinfo=None) < dates[item[1]].replace(tzinfo=None):
                dates[item[1]] = item[0]
                pks[item[1]] = item[2]

    # return just histories with ids in pks dict
    first_histories_ids = list(pks.values())

    return historical_model.objects.filter(pk__in=first_histories_ids).distinct()
