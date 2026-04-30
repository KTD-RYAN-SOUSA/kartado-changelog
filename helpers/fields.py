import base64
import json
import re
from collections import OrderedDict
from io import BytesIO

from django.apps import apps
from django.contrib.gis.geos import GeometryCollection, GEOSGeometry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from geojson import Feature, FeatureCollection
from geojson import loads as geojson_loads
from rest_framework.exceptions import ValidationError
from rest_framework.relations import MANY_RELATION_KWARGS
from rest_framework.relations import ManyRelatedField as DRFManyRelatedField
from rest_framework_gis.fields import GeometryField
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import (
    ResourceRelatedField,
    SerializerMethodResourceRelatedField,
)
from rest_framework_json_api.utils import (
    get_resource_type_from_instance,
    get_resource_type_from_queryset,
)
from storages.utils import clean_name

from helpers.nested_objects import reporting_rgetattr

color_re = re.compile("^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
validate_color = RegexValidator(color_re, _("Enter a valid color."), "invalid")


class ColorField(models.CharField):
    """
    Class created to validate string fields with color regex validation
    """

    default_validators = [validate_color]

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 18
        super(ColorField, self).__init__(*args, **kwargs)


class HistoricalRecordField(serializers.ListField):
    """
    Field used to create history serializer
    """

    child = serializers.DictField()

    def to_representation(self, data):
        return super(HistoricalRecordField, self).to_representation(data.values())


class FeatureCollectionField(GeometryField):
    """
    Class created to return a custom field in serializers with complex geometry.
    The class has a __init__ method with:
    - A geometry_field arg that stores geometry data (lat/long and geometry formats) in the model
    - A properties_field arg that stores custom properties for the stored geometries (e.g., custom identificators for each geometry)
    - An optional collection arg that superseeds the geometry_field if is initialized in the class instantiation

    """

    def __init__(self, geometry_field, properties_field, collection=None, **kwargs):
        kwargs["source"] = "*"
        self.geometry_field = geometry_field
        self.properties_field = properties_field
        self.collection = collection
        super().__init__(**kwargs)

    def to_representation(self, data):
        properties = getattr(data, self.properties_field, [])
        collection = (
            self.collection
            if self.collection
            else getattr(data, self.geometry_field, None)
        )
        if collection:
            geometries = geojson_loads(
                str(super(FeatureCollectionField, self).to_representation(collection))
            )["geometries"]

            features = [
                Feature(
                    geometry=a,
                    properties=properties[index] if index < len(properties) else {},
                )
                for index, a in enumerate(geometries)
            ]
            return FeatureCollection(features)
        else:
            return None

    def to_internal_value(self, value):
        if not value or value == {}:
            return {}

        if isinstance(value, GEOSGeometry):
            # Value already has the correct representation
            return value

        if isinstance(value, dict):
            if "type" not in value or value["type"] != "FeatureCollection":
                raise ValidationError("Geometry must be a FeatureCollection")

            json_geometries = [
                feature.get("geometry", None) for feature in value.get("features", [])
            ]
            properties = [
                feature.get("properties", {}) for feature in value.get("features", [])
            ]

            geometries = []
            for index, geometry in enumerate(json_geometries):
                if geometry:
                    try:
                        a = GEOSGeometry(json.dumps(geometry))
                        geometries.append(a)
                    except Exception:
                        del properties[index]

            return {
                self.geometry_field: GeometryCollection(geometries),
                self.properties_field: properties,
            }

        raise ValidationError("Could not parse geometry")

    def run_validation(self, value):
        if not value:
            return {"geometry": None}
        return super(FeatureCollectionField, self).run_validation(value)


class EmptyFileField(serializers.JSONField):
    """
    This field will accept image/file attachment as a string
    encoded and transform it to binary file.
    """

    def _base64_to_binary(self, data):
        """
        Convert given base64 encoded file.
        """
        file = BytesIO()
        if "data" in data.keys():
            decoded_data = base64.b64decode(data["data"])
            file.write(decoded_data)
            file.seek(0)

        return SimpleUploadedFile(
            data["filename"],
            file.read(),
            content_type="application/octet-stream",
        )

    def to_representation(self, value):
        request = self.context.get("request")
        if (
            request is not None
            and "resize" in request.query_params
            and request.query_params["resize"] in ["400", "1000"]
            and value.name.split(".")[-1].lower() in ["jpg", "jpeg", "png"]
        ):
            params = {}
            params["Bucket"] = "{}-{}px".format(
                value.storage.bucket.name,
                request.query_params["resize"],
            )
            params["Key"] = value.storage._normalize_name(clean_name(value.name))
            return value.storage.bucket.meta.client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=3600
            )

        return value.url if value else None

    def to_internal_value(self, data):
        if "filename" not in data.keys():
            msg = 'Incorrect file format, expected {"filename": "file_name.extension"}'
            raise serializers.ValidationError(msg)
        return self._base64_to_binary(data)


class Base64FileField(serializers.JSONField):
    """
    This field will accept image/file attachment as a string
    encoded and transform it to binary file.
    """

    def _base64_to_binary(self, data):
        """
        Convert given base64 encoded file.
        """
        file = BytesIO()
        decoded_data = base64.b64decode(data["data"])
        file.write(decoded_data)
        file.seek(0)
        return SimpleUploadedFile(
            data["filename"],
            file.read(),
            content_type="application/octet-stream",
        )

    def to_representation(self, value):
        return value.url

    def to_internal_value(self, data):
        if not ("filename" in data.keys() and "data" in data.keys()):
            msg = 'Incorrect file format, expected {"filename":"file_name.extension", "data":"FILE DATA"}'
            raise serializers.ValidationError(msg)
        return self._base64_to_binary(data)


class ReportingRelatedField(ResourceRelatedField):
    """
    A class created to return different resource_name for the same model in the database, depending on the
    type_lookup_path and type_lookup_map params.

    Example:
    In Kartado's database, a Inventory and a Reporting are the same model (Reporting). So when we create a Reporting ForeignKey
    in another model, it can be either a Reporting or a Inventory, depending on its' attributes values.
    In order to return the correct type when making an API call, we use this custom class.
    """

    def __init__(self, **kwargs):
        # check for extra_allowed_types manually specified
        self.extra_allowed_types = kwargs.pop("extra_allowed_types", None)
        self.type_lookup_path = kwargs.pop("type_lookup_path", None)
        self.type_lookup_map = kwargs.pop("type_lookup_map", None)
        self.display_only = kwargs.pop("display_only", None)

        super(ReportingRelatedField, self).__init__(**kwargs)

    def to_internal_value(self, data):
        expected_relation_type = get_resource_type_from_queryset(self.get_queryset())
        serializer_resource_type = self.get_resource_type_from_included_serializer()

        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                # show a useful error if they send a `pk` instead of resource object
                self.fail("incorrect_type", data_type=type(data).__name__)
        if not isinstance(data, dict):
            self.fail("incorrect_type", data_type=type(data).__name__)

        if serializer_resource_type is not None:
            expected_relation_type = serializer_resource_type

        if "type" not in data:
            self.fail("missing_type")

        if "id" not in data:
            self.fail("missing_id")

        if data["type"] in self.extra_allowed_types:
            data["type"] = expected_relation_type

        if data["type"] != expected_relation_type:
            self.conflict(
                "incorrect_relation_type",
                relation_type=expected_relation_type,
                received_type=data["type"],
            )

        return super(ResourceRelatedField, self).to_internal_value(data["id"])

    def to_representation(self, value):
        if getattr(self, "pk_field", None) is not None:
            pk = self.pk_field.to_representation(value.pk)
        else:
            pk = value.pk

        if self.type_lookup_path and self.type_lookup_map:
            try:
                lookup_value = reporting_rgetattr(value, self.type_lookup_path)
                resource_type = self.type_lookup_map[lookup_value]
            except Exception:
                resource_type = "Reporting"
        else:
            resource_type = self.get_resource_type_from_included_serializer()
            if resource_type is None or not self._skip_polymorphic_optimization:
                resource_type = get_resource_type_from_instance(value)

        if self.display_only and resource_type != self.display_only:
            return None

        return OrderedDict([("type", resource_type), ("id", str(pk))])

    @classmethod
    def many_init(cls, *args, **kwargs):
        list_kwargs = {"child_relation": cls(*args, **kwargs)}
        for key in kwargs:
            if key in MANY_RELATION_KWARGS:
                list_kwargs[key] = kwargs[key]
        return ManyRelatedFieldWithoutNone(**list_kwargs)


class ManyRelatedFieldWithoutNone(DRFManyRelatedField):
    def to_representation(self, iterable):
        ret = [self.child_relation.to_representation(value) for value in iterable]
        return [a for a in ret if a]


def get_nested_fields(field, instance):
    try:
        field_type = field["type"]
    except Exception:
        return field

    if field_type == "object":
        try:
            model = apps.get_model(field["model"])
            value = model.objects.filter(**field["filters"]).first()
        except Exception as e:
            print("Invalid object specified", e)
            return None
    elif field_type == "relationship":
        try:
            field_type = instance._meta.get_field(field["key"]).get_internal_type()
        except Exception as e:
            print("Field does not exist", e)
            return None
        if field_type == "ForeignKey":
            value = getattr(instance, field["key"])
        elif field_type == "ManyToManyField":
            if "filters" in field:
                value = (
                    getattr(instance, field["key"]).filter(**field["filters"]).first()
                )
            else:
                value = getattr(instance, field["key"]).first()
        else:
            value = None

    if "follow" in field:
        return get_nested_fields(field["follow"], value)
    else:
        return value


class ResourceRelatedFieldWithName(ResourceRelatedField):
    def to_representation(self, value):
        if getattr(self, "pk_field", None) is not None:
            pk = self.pk_field.to_representation(value.pk)
        else:
            pk = value.pk

        resource_type = self.get_resource_type_from_included_serializer()
        if resource_type is None or not self._skip_polymorphic_optimization:
            resource_type = get_resource_type_from_instance(value)

        return OrderedDict(
            [
                ("type", resource_type),
                ("id", str(pk)),
                ("name", getattr(value, "name", "")),
            ]
        )


class SerializerMethodResourceRelatedFieldWithName(
    SerializerMethodResourceRelatedField, ResourceRelatedFieldWithName
):
    def __new__(cls, *args, **kwargs):
        """
        We override this because getting serializer methods
        fails at the base class when many=True
        """
        if kwargs.pop("many", False):
            return cls.many_init(*args, **kwargs)
        return super(ResourceRelatedFieldWithName, cls).__new__(cls, *args, **kwargs)


class OptimizedSerializerMethodResourceRelatedField(
    SerializerMethodResourceRelatedField
):
    def to_representation(self, value):
        """
        Overriding this method when we want to use this field with a relation like "created_by_id" instead of "created_by"
        """
        return value


class ForgivingTimeField(serializers.TimeField):
    """
    This will behave like a TimeField, but it tolerates the value "Invalid date" and converts it to None
    """

    def to_internal_value(self, value):
        if value == "Invalid date":
            return None
        return super().to_internal_value(value)
