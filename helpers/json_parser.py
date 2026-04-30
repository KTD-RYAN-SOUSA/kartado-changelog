from collections import OrderedDict

import inflection
from rest_framework.exceptions import ParseError
from rest_framework_json_api import exceptions, serializers
from rest_framework_json_api.parsers import JSONParser as DefaultJSONParser
from rest_framework_json_api.renderers import JSONRenderer as DefaultJSONRenderer
from rest_framework_json_api.utils import get_resource_name

from helpers.strings import to_camel_case


def format_keys(obj, format_type="camelize"):
    """
    .. warning::

        `format_keys` function and `JSON_API_FORMAT_KEYS` setting are deprecated and will be
        removed in the future.
        Use `format_field_names` and `JSON_API_FORMAT_FIELD_NAMES` instead. Be aware that
        `format_field_names` only formats keys and preserves value.

    Takes either a dict or list and returns it with camelized keys only if
    JSON_API_FORMAT_KEYS is set.

    :format_type: Either 'dasherize', 'camelize', 'capitalize' or 'underscore'
    """

    # if format_type is None:
    #     format_type = json_api_settings.FORMAT_KEYS

    if format_type in ("dasherize", "camelize", "underscore", "capitalize"):

        if isinstance(obj, dict):
            formatted = OrderedDict()
            for key, value in obj.items():
                if format_type == "dasherize":
                    # inflection can't dasherize camelCase
                    key = inflection.underscore(key)
                    formatted[inflection.dasherize(key)] = format_keys(
                        value, format_type
                    )
                elif format_type == "camelize":
                    formatted[inflection.camelize(key, False)] = format_keys(
                        value, format_type
                    )
                elif format_type == "capitalize":
                    formatted[inflection.camelize(key)] = format_keys(
                        value, format_type
                    )
                elif format_type == "underscore":
                    formatted[inflection.underscore(key)] = format_keys(
                        value, format_type
                    )
            return formatted
        if isinstance(obj, list):
            return [format_keys(item, format_type) for item in obj]
        else:
            return obj
    else:
        return obj


# JSONParser = DefaultJSONParser


class JSONParser(DefaultJSONParser):
    @staticmethod
    def parse_attributes(data):
        attributes = data.get("attributes") or dict()
        return format_keys(attributes, "underscore")

    @staticmethod
    def parse_relationships(data):
        relationships = data.get("relationships") or dict()
        relationships = format_keys(relationships, "underscore")

        # Parse the relationships
        parsed_relationships = dict()
        for field_name, field_data in relationships.items():
            field_data = field_data.get("data")
            if isinstance(field_data, dict) or field_data is None:
                parsed_relationships[field_name] = field_data
            elif isinstance(field_data, list):
                parsed_relationships[field_name] = list(
                    relation for relation in field_data
                )
        return parsed_relationships


class JSONRenderer(DefaultJSONRenderer):
    @classmethod
    def extract_attributes(cls, fields, resource):
        data = super(JSONRenderer, cls).extract_attributes(fields, resource)

        return format_keys(data)

    @classmethod
    def extract_relationships(cls, fields, resource, resource_instance):
        data = super(JSONRenderer, cls).extract_relationships(
            fields, resource, resource_instance
        )

        return format_keys(data)


class JSONParserWithUnformattedKeys(DefaultJSONParser):
    @staticmethod
    def parse_attributes(data, keys_to_keep=[]):

        attributes = data.get("attributes") or dict()
        # convert back to python/rest_framework's preferred underscore format
        formatted_object = format_keys(attributes, "underscore")

        # We want to keep some values unformatted.
        # This is useful for JSONField fields
        for key_to_keep in keys_to_keep:
            if (
                key_to_keep in formatted_object
                and to_camel_case(key_to_keep) in attributes
            ):
                formatted_object[key_to_keep] = attributes[to_camel_case(key_to_keep)]

        return formatted_object

    def parse(self, stream, media_type=None, parser_context=None):
        """
        Parses the incoming bytestream as JSON and returns the resulting data
        """
        result = super(DefaultJSONParser, self).parse(
            stream, media_type=media_type, parser_context=parser_context
        )

        if not isinstance(result, dict) or "data" not in result:
            raise ParseError("Received document does not contain primary data")

        data = result.get("data")
        parser_context = parser_context or {}
        view = parser_context.get("view")

        from rest_framework_json_api.views import RelationshipView

        if isinstance(view, RelationshipView):
            # We skip parsing the object as JSON:API Resource Identifier Object and not a regular
            # Resource Object
            if isinstance(data, list):
                for resource_identifier_object in data:
                    if not (
                        resource_identifier_object.get("id")
                        and resource_identifier_object.get("type")
                    ):
                        raise ParseError(
                            "Received data contains one or more malformed JSON:API "
                            "Resource Identifier Object(s)"
                        )
            elif not (data.get("id") and data.get("type")):
                raise ParseError(
                    "Received data is not a valid JSON:API Resource Identifier Object"
                )

            return data

        request = parser_context.get("request")
        method = request and request.method

        # Sanity check
        if not isinstance(data, dict):
            raise ParseError(
                "Received data is not a valid JSON:API Resource Identifier Object"
            )

        # Check for inconsistencies
        if method in ("PUT", "POST", "PATCH"):
            resource_name = get_resource_name(
                parser_context, expand_polymorphic_types=True
            )
            if isinstance(resource_name, str):
                if data.get("type") != resource_name:
                    raise exceptions.Conflict(
                        "The resource object's type ({data_type}) is not the type that "
                        "constitute the collection represented by the endpoint "
                        "({resource_type}).".format(
                            data_type=data.get("type"), resource_type=resource_name
                        )
                    )
            else:
                if data.get("type") not in resource_name:
                    raise exceptions.Conflict(
                        "The resource object's type ({data_type}) is not the type that "
                        "constitute the collection represented by the endpoint "
                        "(one of [{resource_types}]).".format(
                            data_type=data.get("type"),
                            resource_types=", ".join(resource_name),
                        )
                    )
        if not data.get("id") and method in ("PATCH", "PUT"):
            raise ParseError(
                "The resource identifier object must contain an 'id' member"
            )

        if method in ("PATCH", "PUT"):
            lookup_url_kwarg = getattr(view, "lookup_url_kwarg", None) or getattr(
                view, "lookup_field", None
            )
            if lookup_url_kwarg and str(data.get("id")) != str(
                view.kwargs[lookup_url_kwarg]
            ):
                raise exceptions.Conflict(
                    "The resource object's id ({data_id}) does not match url's "
                    "lookup id ({url_id})".format(
                        data_id=data.get("id"), url_id=view.kwargs[lookup_url_kwarg]
                    )
                )

        # Construct the return data
        serializer_class = getattr(view, "serializer_class", None)
        parsed_data = {"id": data.get("id")} if "id" in data else {}
        # TODO remove in next major version 5.0.0 see serializers.ReservedFieldNamesMixin
        if serializer_class is not None:
            if issubclass(serializer_class, serializers.PolymorphicModelSerializer):
                parsed_data["type"] = data.get("type")
        parsed_data.update(self.parse_attributes(data, view.parser_keys_to_keep))
        parsed_data.update(self.parse_relationships(data))
        parsed_data.update(self.parse_metadata(result))
        return parsed_data
