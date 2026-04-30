import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable, Iterable, Union

import pytz
from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.postgres.search import TrigramBase
from django.core.exceptions import FieldDoesNotExist
from django.db.models import (
    BooleanField,
    DateField,
    DateTimeField,
    F,
    FloatField,
    IntegerField,
    JSONField,
    Q,
    QuerySet,
    TextField,
)
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Trunc
from django.db.models.lookups import Transform
from django.utils import timezone
from django_filters import Filter
from django_filters.fields import DateRangeField
from django_filters.rest_framework import FilterSet
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework_json_api import serializers

from helpers.dates import date_tz
from helpers.strings import (
    dict_to_casing,
    get_obj_from_path,
    path_from_dict,
    to_snake_case,
)


def annotate_datetime(qs, key):
    values = key.split("__")
    lookup = {}
    lookup[key] = Cast(
        KeyTextTransform(values.pop(1), values.pop(0)),
        output_field=models.DateField(),
    )
    return qs.annotate(**lookup)


def filter_history(from_date, to_date, field, history_model, queryset):
    histories = history_model.objects.filter(uuid__in=queryset).values_list(
        "uuid", field, "history_date"
    )

    result = defaultdict(list)
    for item in histories:
        correct_date = item[2].astimezone(pytz.timezone(settings.TIME_ZONE))
        if isinstance(item[0], uuid.UUID) and item[1] is not None:
            if ((correct_date >= from_date) and (correct_date <= to_date)) or (
                (correct_date <= from_date)
                and (all(map(lambda x: x[1] >= from_date, result[item[0]])))
            ):
                result[item[0]].append((item[1] or "none", correct_date))

    obj_ids = []
    for key, value in result.items():
        list_field_ids = [item[0] for item in value]
        if len(list(set(list_field_ids))) > 1:
            obj_ids.append(key)

    return queryset.filter(pk__in=obj_ids).distinct()


def reporting_expired_filter(queryset, value):
    value = value.split(",")

    available_filters = [
        "expired",
        "expired_not_executed",
        "expired_and_executed",
        "expires_in_24_hours",
        "expires_in_48_hours",
        "expires_in_72_hours",
        "expires_in_1_week",
        "executed_within_deadline",
        "executed_over_deadline",
    ]
    if not set(value).issubset(available_filters):
        return queryset

    now = timezone.now()

    filters = Q(uuid__isnull=True)

    if "expired" in value:
        filters = filters | Q(due_at__lte=now)
    if "expired_not_executed" in value:
        filters = filters | Q(due_at__lte=now, executed_at__isnull=True)
    if "expired_and_executed" in value:
        filters = filters | Q(due_at__lte=now, executed_at__isnull=False)
    if "expires_in_24_hours" in value:
        new_time = now + timedelta(days=1)
        filters = filters | Q(due_at__lte=new_time, due_at__gte=now)
    if "expires_in_48_hours" in value:
        new_time = now + timedelta(days=2)
        filters = filters | Q(due_at__lte=new_time, due_at__gte=now)
    if "expires_in_72_hours" in value:
        new_time = now + timedelta(days=3)
        filters = filters | Q(due_at__lte=new_time, due_at__gte=now)
    if "expires_in_1_week" in value:
        new_time = now + timedelta(days=7)
        filters = filters | Q(due_at__lte=new_time, due_at__gte=now)
    if "executed_within_deadline" in value:
        filters = filters | Q(executed_at__date__lte=F("due_at__date"))
    if "executed_over_deadline" in value:
        filters = filters | Q(executed_at__date__gt=F("due_at__date"))

    return queryset.filter(filters).distinct()


class JSONFieldOrderingFilter(OrderingFilter):
    """
    A more powerful version of the OrderingFilter with
    support for ordering using the contents of a JSONField.

    Can handle only one level of nesting (for now).

    IMPORTANT: Make sure to NEVER filter by JSON content
    that doesn't exist. It will cause silent errors.
    See https://gitlab.com/Road-Labs/hidros-backend/-/merge_requests/1257#note_1142234403 # noqa
    """

    # Supported data types
    VALID_FORM_FIELD_TYPES = {
        "number": IntegerField(),
        "float": FloatField(),
        "string": TextField(),
        "text_area": TextField(),
        "timestamp": DateTimeField(),
        "boolean": BooleanField(),
    }

    # NOTE: ALWAYS override this value so you can get proper error messages
    model_name = None

    # Default field used for JSON ordering
    base_json_field_path = "form_data"

    # Default field used to find the json field's data type
    base_type_field_path = "occurrence_type__form_fields__fields"

    def get_order_by_fields(self, request, queryset, view):
        """Returns a list of the fields that are going to be used"""
        ordering = self.get_ordering(request, queryset, view)
        return ordering

    def validate_fields(self, stripped_fields, view, queryset):
        """
        Make sure the base field and inner JSON fields are valid and
        part of the view's ordering_fields
        """

        # Check if the provided json field is valid for the model
        try:
            base_field_is_json = isinstance(
                queryset.model._meta.get_field(self.base_json_field_path),
                JSONField,
            )
        except FieldDoesNotExist:
            raise serializers.ValidationError(
                "kartado.error.{}"
                ".the_base_json_field_{}_does_not_exist_for_this_model".format(
                    self.model_name, self.base_json_field_path
                )
            )
        if not base_field_is_json:
            field_type = type(
                queryset.model._meta.get_field(self.base_json_field_path)
            ).__name__
            raise serializers.ValidationError(
                "kartado.error.{}.the_field_{}_is_a_{}_and_not_a_valid_json_field".format(
                    self.model_name,
                    self.base_json_field_path,
                    to_snake_case(field_type),
                )
            )

    def get_json_fields(self, stripped_fields):
        """
        Returns a list only with the ordering json fields.
        Default path is form_data
        """
        json_fields = []
        for field in stripped_fields:
            if self.base_json_field_path in field:
                if field.count("__") > 1:
                    raise serializers.ValidationError(
                        "kartado.error.{}.the_field_{}_contains_two_or_more_nested_accesses_which_are_not_yet_supported".format(
                            self.model_name, field
                        )
                    )
                json_fields.append(field)

        return json_fields

    def get_type_lookup(self, queryset):
        """
        Returns a lookup dict to determine the proper output_field type.
        Default path is occurrence_type__form_fields__fields
        """

        # Get all possible fields from related occurrence_types
        occurrence_types_fields_list = queryset.values_list(
            self.base_type_field_path, flat=True
        )

        # Convert to snake_case, remove None values and ensure items are lists
        occurrence_types_fields_list = dict_to_casing(
            list(occurrence_types_fields_list), format_type="underscore"
        )
        occurrence_types_fields_list = list(
            filter(
                lambda i: i and isinstance(i, list),
                occurrence_types_fields_list,
            )
        )

        # Structure {api_name: Field()} dict for easy lookup
        api_name_to_type_lookup = {
            to_snake_case(field["api_name"]): get_obj_from_path(
                self.VALID_FORM_FIELD_TYPES, field["data_type"]
            )
            for occurrence_type_fields in occurrence_types_fields_list
            for field in occurrence_type_fields
            if isinstance(field, dict)
            and "data_type" in field
            and "api_name" in field
            and to_snake_case(field["data_type"]) in self.VALID_FORM_FIELD_TYPES
        }

        return api_name_to_type_lookup

    def get_ordered_queryset(
        self, queryset: QuerySet, order_by_fields: list
    ) -> QuerySet:
        """
        Receives the fields that are going to be used for the ordering
        and convert them to F() calls with proper null position management

        Args:
            queryset (QuerySet): The queryset to be ordered
            order_by_fields (list): List of fields used for the ordering

        Returns:
            QuerySet: Ordered queryset
        """

        order_by_args = []
        for field in order_by_fields:
            stripped_field = field.replace("-", "")
            order_by_args.append(
                F(stripped_field).desc(nulls_last=True)
                if field[0] == "-"
                else F(stripped_field).asc(nulls_first=True)
            )
        return queryset.order_by(*order_by_args)

    def get_ordered_annotated_queryset(
        self, queryset, json_fields, order_by_fields, type_lookup
    ):
        """
        Returns the annotated queryset already properly ordered according to
        the json fields
        """

        # Annotated fields will have the prefix ann_ to avoid conflicts
        order_by_fields_with_ann = [
            field.replace(self.base_json_field_path + "__", "ann_")
            for field in order_by_fields
        ]

        # Structure {ann_<field_name>: Cast(KeyTextTransform())}
        ann_json_fields = {}
        for field_path in json_fields:
            field_name = field_path.split("__")[-1].split(".")[-1]
            field_name_with_form_data = field_path.split("__")[-1]

            # Check if provided form_data fields contain supported data types
            if field_name not in type_lookup:
                raise serializers.ValidationError(
                    "Não é possível ordenar o painel por uma das colunas escolhidas, pois não existem apontamentos na lista que possuam valor nessa coluna. Escolha outro campo para ordenação ou altere as condições do painel."
                )

            # Determine the field's data type
            field_data_type = type_lookup[field_name]

            # Add the properly typed future annotation to expression dict
            annotated_field_name = "ann_" + field_name_with_form_data
            ann_json_fields[annotated_field_name] = Cast(
                KeyTextTransform(field_name, self.base_json_field_path),
                output_field=field_data_type,
            )

        annotated_queryset = queryset.annotate(**ann_json_fields)

        return self.get_ordered_queryset(annotated_queryset, order_by_fields_with_ann)

    def filter_queryset(self, request, queryset, view):
        self.model_name = to_snake_case(queryset.model.__name__)
        order_by_fields = self.get_order_by_fields(request, queryset, view)

        if order_by_fields:
            # List of fields without the "-" character for easy processing
            stripped_fields = [field.replace("-", "") for field in order_by_fields]

            self.validate_fields(stripped_fields, view, queryset)

            json_fields = self.get_json_fields(stripped_fields)
            if json_fields:
                type_lookup = self.get_type_lookup(queryset)

                # No type lookup means no supported fields were found
                if not type_lookup:
                    raise serializers.ValidationError(
                        "kartado.error.{}.none_of_the_provided_json_fields_are_from_supported_data_types".format(
                            self.model_name
                        )
                    )

                return self.get_ordered_annotated_queryset(
                    queryset, json_fields, order_by_fields, type_lookup
                )
            else:
                return self.get_ordered_queryset(queryset, order_by_fields)

        # No ordering required
        else:
            return queryset


class KeyFilter(Filter):
    def __init__(self, allow_null=False, **kwargs):
        self.allow_null = allow_null
        super().__init__(**kwargs)

    def filter(self, qs, value):
        if not value:
            return qs

        try:
            value_json = json.loads(value)
        except Exception:
            raise serializers.ValidationError("Filtro json inválido.")

        self.lookup_expr = "icontains"
        paths = path_from_dict(value_json)
        run_datetime_check = False

        query = Q()
        for key, value in paths.items():
            if isinstance(value, list):
                if all(isinstance(item, dict) for item in value):
                    for item in value:
                        key_str = "{}__{}__contains".format(self.field_name, key)
                        query.add(Q(**{key_str: [item]}), Q.AND)
                else:
                    # Using __in does not work properly
                    key_str = "{}__{}__has_any_keys".format(self.field_name, key)
                    query.add(Q(**{key_str: value}), Q.AND)
            elif isinstance(value, (int, float, datetime)):
                # also works for boolean fields
                key_str = "{}__{}".format(self.field_name, key)
                if isinstance(value, (datetime)):
                    run_datetime_check = True
                    key_split = key_str.split("__")
                    if key_split[-1] not in ["gte", "lte", "gt", "lt"]:
                        raise ValidationError("Filtro de data deve ser range.")
                    key_path = "__".join(key_split[0:-1])
                    qs = annotate_datetime(qs, key_path)
                query.add(Q(**{key_str: value}), Q.AND)
            elif value is None:
                if self.allow_null:
                    value = True
                    key_str = "{}__{}__isnull".format(self.field_name, key)
                else:
                    continue
                query.add(Q(**{key_str: value}), Q.AND)
            else:
                key_str = "{}__{}__{}".format(self.field_name, key, self.lookup_expr)
                query.add(Q(**{key_str: value}), Q.AND)
        qs = qs.filter(query)

        # Use this to check errors
        if run_datetime_check:
            try:
                qs.exists()
            except Exception:
                raise ValidationError("O campo especificado não é uma data válida.")

        if self.distinct:
            qs = qs.distinct()
        return qs


def filter_by_obj_id(item, obj_id):
    if isinstance(item, dict):
        if "properties" in item and isinstance(item["properties"], dict):
            properties = {k.lower(): v for k, v in item["properties"].items()}
            if "objectid" in properties:
                if properties["objectid"] == obj_id:
                    return True
    return False


class ListFilter(Filter):
    validator: Union[Callable[[Iterable[str]], bool], None]

    def __init__(self, allow_null=False, validator=None, **kwargs):
        self.allow_null = allow_null
        self.validator = validator
        super().__init__(**kwargs)

    def filter(self, qs, value):
        if not value:
            return qs

        self.lookup_expr = "in"
        values = value.split(",")

        if "null" in values and not self.allow_null:
            raise ValidationError(
                "kartado.error.filters.null_filter_is_not_allowed_for_this_field"
            )

        non_null_values = [v for v in values if v != "null"]
        if self.validator and non_null_values:
            if not self.validator(non_null_values):
                raise serializers.ValidationError(
                    "kartado.error.filters.at_least_one_invalid_filter_value_was_provided"
                )

        has_null = "null" in values and self.allow_null
        has_values = bool(non_null_values)

        if has_null and has_values:
            null_condition = Q(**{f"{self.field_name}__isnull": True})
            values_condition = Q(**{f"{self.field_name}__in": non_null_values})
            return self.get_method(qs)(null_condition | values_condition).distinct()
        elif has_null:
            return self.get_method(qs)(
                **{f"{self.field_name}__isnull": True}
            ).distinct()
        elif has_values:
            return self.get_method(qs)(
                **{f"{self.field_name}__in": non_null_values}
            ).distinct()

        return qs.distinct()


class UUIDListFilter(ListFilter):
    """Same as ListFilter but ensures the list items are valid UUIDs"""

    def __init__(self, **kwargs):
        def validator(values: Iterable[str]) -> bool:
            try:
                return all(str(uuid.UUID(value)) == value for value in values)
            except Exception:
                return False

        super().__init__(validator=validator, **kwargs)


class ListRangeFilter(Filter):
    def filter(self, qs, value):
        if not value:
            return qs

        values = value.split(",")

        if len(values) % 2 != 0:
            raise Exception("O Filtro deve ter um tamanho total par")

        q_filter = Q()
        for i in range(0, len(values), 2):
            range_value = (values[i], values[i + 1])
            q_filter |= Q(**{f"{self.field_name}__range": range_value})

        return self.get_method(qs)(q_filter)


def queryset_with_timezone(qs, current_field, destination_field, is_date=False):
    """
    Given a queryset, return an annotated queryset with destination_field
    to be equal to current_field with settings timezone
    """
    output_field = DateField if is_date else DateTimeField
    kind = "day" if is_date else "second"
    annotate_dict = {
        destination_field: Trunc(current_field, kind, output_field=output_field())
    }
    qs_annotated = qs.annotate(**annotate_dict)
    return qs_annotated


class DateTzFilter(Filter):
    def filter(self, qs, value):
        if not value:
            return qs

        value = date_tz(value)

        return super().filter(qs, value)


class DateFromToRangeCustomFilter(Filter):
    field_class = DateRangeField

    def __init__(self, company_field="", is_date=False, is_null=False, **kwargs):
        self.company_field = company_field
        self.is_date = is_date
        self.is_null = is_null
        super().__init__(**kwargs)

    def filter(self, qs, value):
        if not value:
            return qs

        try:
            company = self.parent.request.query_params["company"]
        except Exception:
            company = ""

        if self.company_field and not company:
            return qs

        if value.start is not None and value.stop is not None:
            self.lookup_expr = "range"
            value = (
                value.start.replace(tzinfo=pytz.UTC),
                value.stop.replace(tzinfo=pytz.UTC),
            )
        elif value.start is not None:
            self.lookup_expr = "gte"
            value = value.start.replace(tzinfo=pytz.UTC)
        elif value.stop is not None:
            self.lookup_expr = "lte"
            value = value.stop.replace(tzinfo=pytz.UTC)

        new_field_name = "new_{}".format(self.field_name)
        lookup = "%s__%s" % (new_field_name, self.lookup_expr)
        qs_annotated = queryset_with_timezone(
            qs, self.field_name, new_field_name, self.is_date
        )
        filter_dict = {lookup: value}
        if self.company_field and company:
            filter_dict[self.company_field] = company
        if self.is_null:
            filter_dict["{}__isnull".format(new_field_name)] = False

        new_qs = self.get_method(qs_annotated)(**filter_dict)

        return new_qs.distinct() if self.distinct else new_qs


class TrigramWordSimilarity(TrigramBase):
    function = "WORD_SIMILARITY"


class Floor(Transform):
    function = "FLOOR"
    lookup_name = "floor"


class FilterSetWithInitialValues(FilterSet):
    """
    Allow use of initial value for a filter field.
    """

    def __init__(self, data=None, *args, **kwargs):
        # if filterset is bound, use initial values as defaults
        if data is not None:
            # get a mutable copy of the QueryDict
            data = data.copy()

            for name, f in self.base_filters.items():
                initial = f.extra.get("initial")

                # filter param is either missing or empty, use initial as default
                if not data.get(name) and initial:
                    data[name] = initial

        super().__init__(data, *args, **kwargs)


class BaseModelFilterSet(FilterSet):
    uuid = UUIDListFilter()
    created_by = UUIDListFilter()
    company = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    updated_at = DateFromToRangeCustomFilter()

    class Meta:
        fields = ["uuid", "created_by", "company", "created_at", "updated_at"]
