import inspect

from django.core.paginator import Paginator as DjangoPaginator
from django.db.models.query import QuerySet
from django.utils.functional import cached_property
from django.utils.inspect import method_has_no_args
from rest_framework_json_api import pagination


class CustomDjangoPaginator(DjangoPaginator):
    @cached_property
    def count(self):
        """Return the total number of objects, across all pages."""
        if isinstance(self.object_list, QuerySet) and "uuid" in [
            a.name for a in self.object_list.model._meta.fields
        ]:
            qs = self.object_list.only("uuid")
        else:
            qs = self.object_list
        c = getattr(qs, "count", None)
        if callable(c) and not inspect.isbuiltin(c) and method_has_no_args(c):
            return c()
        return len(self.object_list)


class CustomPagination(pagination.JsonApiPageNumberPagination):
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = 100000
    django_paginator_class = CustomDjangoPaginator
