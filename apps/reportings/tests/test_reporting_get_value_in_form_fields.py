from unittest.mock import MagicMock, patch

import pytest

from apps.reportings.helpers.get_form_data import get_value_in_form_fields
from helpers.strings import deep_keys_to_snake_case, to_snake_case

pytestmark = pytest.mark.django_db


class TestStringHelpers:
    def test_to_snake_case(self):
        assert to_snake_case("camelCase") == "camel_case"
        assert to_snake_case("anotherCamelCase") == "another_camel_case"

        assert to_snake_case("PascalCase") == "pascal_case"
        assert to_snake_case("AnotherPascalCase") == "another_pascal_case"

        assert to_snake_case("snake_case") == "snake_case"
        assert to_snake_case("another_snake_case") == "another_snake_case"

        assert to_snake_case("mixedCase_with_snake") == "mixed_case_with_snake"

        assert to_snake_case("") == ""

        try:
            to_snake_case(None)
            assert False, "Deveria ter lançado TypeError"
        except TypeError:
            pass

    def test_deep_keys_to_snake_case_with_dict(self):
        input_dict = {"camelCase": "value", "PascalCase": "anotherValue"}
        expected = {"camel_case": "value", "pascal_case": "anotherValue"}
        assert deep_keys_to_snake_case(input_dict) == expected

        input_dict = {
            "outerKey": {"innerCamelCase": "value", "anotherInnerKey": "anotherValue"}
        }
        expected = {
            "outer_key": {
                "inner_camel_case": "value",
                "another_inner_key": "anotherValue",
            }
        }
        assert deep_keys_to_snake_case(input_dict) == expected

        input_dict = {"listKey": [{"itemOneKey": "value1"}, {"itemTwoKey": "value2"}]}
        expected = {
            "list_key": [{"item_one_key": "value1"}, {"item_two_key": "value2"}]
        }
        assert deep_keys_to_snake_case(input_dict) == expected
        assert deep_keys_to_snake_case({}) == {}
        assert deep_keys_to_snake_case(None) is None

    def test_deep_keys_to_snake_case_with_list(self):
        input_list = [{"camelCase": "value1"}, {"PascalCase": "value2"}]
        expected = [{"camel_case": "value1"}, {"pascal_case": "value2"}]
        assert deep_keys_to_snake_case(input_list) == expected

        input_list = [
            {"outerKey": {"innerKey": "value"}},
            [{"nestedListKey": "nestedValue"}],
        ]
        expected = [
            {"outer_key": {"inner_key": "value"}},
            [{"nested_list_key": "nestedValue"}],
        ]
        assert deep_keys_to_snake_case(input_list) == expected

        assert deep_keys_to_snake_case([]) == []


class TestGetValueInFormFields:
    @patch("apps.reportings.models.ReportingFile")
    def test_treatment_images_field(self, mock_reporting_file):
        mock_file1 = MagicMock()
        mock_file1.upload.url = "http://example.com/file1.jpg"
        mock_file2 = MagicMock()
        mock_file2.upload.url = "http://example.com/file2.jpg"

        mock_reporting_file.objects.filter.return_value = [mock_file1, mock_file2]
        result = get_value_in_form_fields("treatment_images", ["id1", "id2"], {})
        mock_reporting_file.objects.filter.assert_called_once_with(
            pk__in=["id1", "id2"]
        )

        assert result == [
            "http://example.com/file1.jpg",
            "http://example.com/file2.jpg",
        ]

    def test_simple_field_types(self):
        form_fields = {
            "fields": [
                {"api_name": "stringField", "data_type": "string"},
                {"api_name": "numberField", "data_type": "number"},
                {"api_name": "floatField", "data_type": "float"},
                {"api_name": "textAreaField", "data_type": "text_area"},
                {"api_name": "booleanField", "data_type": "boolean"},
            ]
        }

        assert (
            get_value_in_form_fields("string_field", "test value", form_fields)
            == "test value"
        )
        assert get_value_in_form_fields("number_field", 123, form_fields) == 123
        assert get_value_in_form_fields("float_field", 123.45, form_fields) == 123.45
        assert (
            get_value_in_form_fields("text_area_field", "multiline\ntext", form_fields)
            == "multiline\ntext"
        )
        assert get_value_in_form_fields("boolean_field", True, form_fields) is True

    def test_select_field_type(self):
        form_fields = {
            "fields": [
                {
                    "api_name": "selectField",
                    "data_type": "select",
                    "select_options": {
                        "options": [
                            {"value": "1", "name": "Option 1"},
                            {"value": "2", "name": "Option 2"},
                            {"value": "3", "name": "Option 3"},
                        ]
                    },
                }
            ]
        }

        assert get_value_in_form_fields("select_field", "1", form_fields) == "Option 1"
        assert get_value_in_form_fields("select_field", "2", form_fields) == "Option 2"
        assert get_value_in_form_fields("select_field", "4", form_fields) is None

    def test_select_multiple_field_type(self):
        form_fields = {
            "fields": [
                {
                    "api_name": "selectMultipleField",
                    "data_type": "select_multiple",
                    "select_options": {
                        "options": [
                            {"value": "1", "name": "Option 1"},
                            {"value": "2", "name": "Option 2"},
                            {"value": "3", "name": "Option 3"},
                        ]
                    },
                }
            ]
        }

        assert (
            get_value_in_form_fields("select_multiple_field", "1", form_fields)
            == "Option 1"
        )
        result = get_value_in_form_fields(
            "select_multiple_field", ["1", "3"], form_fields
        )
        assert isinstance(result, list)
        assert "Option 1" in result
        result_not_found = get_value_in_form_fields(
            "select_multiple_field", ["4"], form_fields
        )
        assert isinstance(result_not_found, list)
        assert len(result_not_found) == 0 or all(
            item is None or item == "" for item in result_not_found
        )

    @patch("apps.occurrence_records.models.OccurrenceType")
    def test_therapy_array_of_objects(self, mock_occurrence_type):
        mock_type = MagicMock()
        mock_type.form_fields = {
            "fields": [
                {
                    "api_name": "severity",
                    "data_type": "select",
                    "select_options": {
                        "options": [
                            {"value": "1", "name": "Low"},
                            {"value": "2", "name": "Medium"},
                        ]
                    },
                }
            ]
        }
        mock_occurrence_type.objects.get.return_value = mock_type

        form_fields = {
            "fields": [{"api_name": "therapy", "data_type": "array_of_objects"}]
        }

        value = [
            {"occurrence_type": "type1", "severity": "1"},
            {"occurrence_type": "type2", "severity": "2"},
        ]

        result = get_value_in_form_fields("therapy", value, form_fields)

        mock_occurrence_type.objects.get.assert_any_call(pk="type1")
        mock_occurrence_type.objects.get.assert_any_call(pk="type2")

        assert result[0]["severity"] == "Low"
        assert result[1]["severity"] == "Medium"

    @patch("apps.reportings.models.ReportingFile")
    def test_inner_images_array(self, mock_reporting_file):
        mock_file1 = MagicMock()
        mock_file1.upload.url = "http://example.com/file1.jpg"
        mock_reporting_file.objects.filter.return_value = [mock_file1]

        form_fields = {
            "fields": [
                {
                    "api_name": "arrayField",
                    "data_type": "array_of_objects",
                    "inner_fields": [
                        {"api_name": "images", "data_type": "inner_images_array"}
                    ],
                }
            ]
        }

        value = [{"images": ["image_id"]}]
        result = get_value_in_form_fields("array_field", value, form_fields)

        mock_reporting_file.objects.filter.assert_called_with(pk__in=["image_id"])

        assert result[0]["images"] == ["http://example.com/file1.jpg"]
