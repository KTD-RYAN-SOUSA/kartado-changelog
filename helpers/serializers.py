import json
import logging
import sys
from datetime import date, datetime, timedelta
from typing import Any, Union
from uuid import UUID

import pytz
from django.contrib.gis.geos.collections import GeometryCollection
from django.contrib.gis.geos.point import Point
from django.db.models import Model
from django.db.models.fields.files import FieldFile
from django.db.models.manager import Manager
from django.forms.models import model_to_dict
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import SerializerMethodResourceRelatedField

from helpers.json_parser import JSONRenderer
from helpers.mixins import EagerLoadingMixin, UUIDMixin


class BaseModelSerializer(serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin):
    _SELECT_RELATED_FIELDS = []
    _PREFETCH_RELATED_FIELDS = ["created_by", "company"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        fields = ["uuid", "created_by", "company", "created_at", "updated_at"]
        read_only_fields = ["uuid", "created_by", "created_at", "updated_at"]
        extra_kwargs = {"company": {"required": True}}


def get_obj_serialized(
    obj,
    serializer=None,
    view=None,
    is_reporting=False,
    is_occurrence_record=False,
    is_inventory=False,
    is_reporting_bi=False,
    is_inventory_bi=False,
    serializer_context=None,
):
    if is_reporting:
        from apps.reportings.serializers import ReportingSerializer
        from apps.reportings.views import ReportingView

        serializer = ReportingSerializer
        view = ReportingView
    if is_reporting_bi:
        from apps.reportings.serializers import LightReportingSerializer
        from apps.reportings.views import ReportingView

        serializer = LightReportingSerializer
        view = ReportingView
    if is_inventory_bi:
        from apps.reportings.serializers import LightReportingSerializer
        from apps.reportings.views import InventoryView

        serializer = LightReportingSerializer
        view = InventoryView
    if is_occurrence_record:
        from apps.occurrence_records.serializers import OccurrenceRecordSerializer
        from apps.occurrence_records.views import OccurrenceRecordView

        serializer = OccurrenceRecordSerializer
        view = OccurrenceRecordView

    if is_inventory:
        from apps.reportings.serializers import ReportingSerializer
        from apps.reportings.views import InventoryView

        serializer = ReportingSerializer
        view = InventoryView

    if serializer and view:
        serializer_instance = (
            serializer(obj, context=serializer_context)
            if serializer_context
            else serializer(obj)
        )
        obj_serialized = json.loads(
            JSONRenderer().render(
                serializer_instance.data, renderer_context={"view": view}
            )
        )

        obj_formatted = {
            "relationships": obj_serialized["data"]["relationships"],
            **obj_serialized["data"]["attributes"],
        }
        return obj_formatted
    else:
        return {}


def get_field_if_provided_or_present(
    field_name: str, attrs: dict, instance: Union[Model, None], many_to_many=False
) -> Union[Any, None]:
    """
    Helper to extract the value of a field if provided in the attributes or
    present in the instance (if the instance exists).
    Returns None if no value can be extracted.

    Args:
        field_name (str): Name of the field being extracted
        attrs (dict): The input attributes coming from the serializer
        instance (Union[Model, None]): Instance of the model being evaluated
        many_to_many (bool, optional): Wether the field is a many to many relation or not. Defaults to False.

    Returns:
        Union[Any, None]: Retrieved field value or None if nothing was retrieved
    """

    if field_name in attrs:
        return attrs[field_name]
    elif instance and many_to_many:
        manager: Manager = getattr(instance, field_name)
        return manager.all()
    elif instance:
        return getattr(instance, field_name)
    else:
        return None


class LabeledChoiceField(serializers.ChoiceField):
    """
    Accepts human readable labels of choices as input and output.
    Extends `serializers.ChoiceField`.
    """

    def to_representation(self, value):
        return self._choices[value]

    def to_internal_value(self, data):
        try:
            internal_value = next(
                choice_value
                for choice_value, choice_label in self._choices.items()
                if choice_label == data
            )
            return internal_value
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.serializers.choice_provided_to_choice_field_was_invalid"
            )


class UUIDSerializerMethodResourceRelatedField(SerializerMethodResourceRelatedField):
    """
    Serializer that returns only the name/pk of the calculated field of any model and not the instance(s).
    This creates an optimization so we can return the response faster and let the frontend map the returned
    values to the actual required information
    """

    def to_representation(self, value):
        return {"type": self.model.__name__, "id": str(value)}


def generic_serializer_instance_model(
    obj,
    url: bool = False,
    exclude_fields: list = [],
):
    exclude_fields.extend(["uuid"])

    obj_dict = model_to_dict(obj)

    fields = obj._meta.get_fields()
    for field in fields:
        # Exclude reverse relationship fields
        field_name = field.name
        if (
            (field.is_relation and not field.auto_created)
            or not hasattr(obj, field_name)
            or (field.is_relation and not obj_dict.get(field_name))
        ):
            continue

        if obj_dict.get(field_name) is None:
            obj_dict[field_name] = getattr(obj, field_name)

    for field in exclude_fields:
        if field in obj_dict:
            obj_dict.pop(field, None)

    # Populate the dictionary with relationship field keys
    for field, value in obj_dict.items():
        if value and (
            isinstance(value, UUID)
            or isinstance(value, (date, timedelta))
            or isinstance(value, (GeometryCollection, Point))
        ):
            obj_dict[field] = str(value)
        elif hasattr(value, "pk"):
            obj_dict[field] = str(value.pk)
        elif isinstance(value, FieldFile):
            if value:
                if url:
                    obj_dict[field] = value.url
                else:
                    obj_dict[field] = value.name
            else:
                obj_dict[field] = ""
        elif isinstance(value, datetime):
            datetime_obj_utc = value.replace(tzinfo=pytz.UTC)
            obj_dict[field] = datetime_obj_utc.isoformat()

        elif isinstance(value, list):
            data_value = []
            for _v in value:
                if hasattr(_v, "pk"):
                    data_value.append(str(_v.pk))
                else:
                    data_value.append(_v)

            obj_dict[field] = data_value

    return obj_dict


BYTE_LIMIT = 1 * 1024 * 1024  # 1 MB


def handle_value_over_size_limit(value):
    if sys.getsizeof(repr(value)) > BYTE_LIMIT:
        logging.warning(
            f"handle_value_over_size_limit: Value provided ({type(value).__name__}) by limited field exceeds the current byte limit. Returning empty value..."
        )

        if isinstance(value, list):
            return []
        elif isinstance(value, dict):
            return {}
        elif isinstance(value, set):
            return set()
        elif isinstance(value, str):
            return ""
        elif isinstance(value, tuple):
            return ()
        else:
            return None

    return value


class LimitedSizeJsonField(serializers.JSONField):
    """
    Serializer field used to limit the max size of a JSONField to "BYTE_LIMIT". This class limits:
    - The return value by replacing the actual value with an empty instance
    - The database value by returning an error if the size bigger than "BYTE_LIMIT"
    """

    def to_internal_value(self, data):
        if sys.getsizeof(repr(data)) > BYTE_LIMIT:
            raise serializers.ValidationError(
                "kartado.error.serializers.provided_json_value_is_bigger_than_accepted_size_limit"
            )

        return super().to_internal_value(data)

    def to_representation(self, value):
        return handle_value_over_size_limit(super().to_representation(value))


class LimitedSizeSerializerMethodField(serializers.SerializerMethodField):
    """
    Serializer field used to limit the representation of an SerializerMethodField, i.e., a field not stored in the database
    """

    def to_representation(self, value):
        return handle_value_over_size_limit(super().to_representation(value))
