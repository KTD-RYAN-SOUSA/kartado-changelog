from datetime import datetime

import sentry_sdk
from rest_framework.pagination import PageNumberPagination

from helpers.dates import date_tz


class Synchronization:
    next_page = None
    data = dict()

    def __init__(self, request, last_pulled_at):
        self.request = request
        self.today = date_tz(datetime.today().strftime("%Y%m%d, %H:%M:%S"))
        self.last_pulled_at = last_pulled_at
        self.last_pulled_date = self.timestamp_date()
        self.company = request.query_params.get("company")

    def add_model(self, name, object_list, serializer):
        self.data[name] = {"created": [], "updated": [], "deleted": []}
        try:
            self.data[name]["created"] = self.created(object_list, serializer)
            self.data[name]["updated"] = self.updated(object_list, serializer)
            self.data[name]["deleted"] = self.deleted(object_list)
        except Exception as e:
            sentry_sdk.capture_exception(e)

    def timestamp_date(self):
        _timestamp = datetime.fromtimestamp(self.last_pulled_at)
        _timestamp = _timestamp.strftime("%Y%m%d, %H:%M:%S")
        return date_tz(_timestamp)

    def mount_list(self, object_list, serializer):
        try:
            paginator = PageNumberPagination()
            paginator.page_size = self.request.query_params.get("page_size", 2000)
            paginator.paginate_queryset(object_list, self.request)
        except Exception:
            # Page of records not exists to the model
            return []
        else:
            _serializer = serializer(paginator.page.object_list, many=True)
            data = paginator.get_paginated_response(_serializer.data).data

            if not self.next_page and paginator.page.has_next():
                self.next_page = data.get("next", None)

            return data.get("results", [])

    def created(self, object_list, serializer):
        if self.last_pulled_at == 0:
            reporting_created = object_list.filter(created_at__lte=self.today).order_by(
                "created_at"
            )
        else:
            reporting_created = object_list.filter(
                created_at__gte=self.last_pulled_date
            ).order_by("created_at")
        return self.mount_list(reporting_created, serializer)

    def updated(self, object_list, serializer):
        if self.last_pulled_at == 0:
            return []
        reporting_updated = object_list.filter(
            created_at__lte=self.last_pulled_date,
            updated_at__gt=self.last_pulled_date,
        ).order_by("updated_at")
        return self.mount_list(reporting_updated, serializer)

    def deleted(self, object_list):
        if self.last_pulled_at == 0 or not self.company:
            return []

        return (
            object_list.model.history.filter(
                company=self.company,
                history_type="-",
                created_at__lte=self.last_pulled_date,
                history_date__gt=self.last_pulled_date,
            )
            .order_by("history_date")
            .values("uuid")
        )

    def get_created(self, name):
        return self.data[name]["created"]

    def get_updated(self, name):
        return self.data[name]["updated"]

    def get_deleted(self, name):
        return [d["uuid"] for d in self.data[name]["deleted"]]

    def get_changes(self):
        data = {}
        for k in self.data.keys():
            data[k] = {
                "created": self.get_created(k),
                "updated": self.get_updated(k),
                "deleted": self.get_deleted(k),
            }
        return data

    def get_timestamp(self):
        return int(self.today.timestamp())
