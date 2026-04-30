from unittest.mock import Mock

import pytest
from django.test import TestCase

from helpers.forms import (
    clean_form_data,
    form_fields_dict,
    get_api_name,
    get_form_fields,
    get_form_metadata,
    get_topics,
    merge_monitoring_and_therapy_data,
)

pytestmark = pytest.mark.django_db


class TestGetTopics(TestCase):
    """Tests for get_topics function"""

    def test_get_topics_with_names_true(self):
        """Test getting topic names"""
        form_fields = {
            "fields": [
                {
                    "api_name": "inspectionTopics",
                    "selectoptions": {
                        "options": [
                            {"value": "1", "name": "Topic Name1"},
                            {"value": "2", "name": "Topic Name2"},
                            {"value": "3", "name": "Topic Name3"},
                        ]
                    },
                }
            ]
        }
        form_data = {"inspection_topics": ["1", "2"]}

        result = get_topics(form_fields, form_data, names=True)

        assert isinstance(result, list)
        assert "Name1" in result
        assert "Name2" in result
        assert "Name3" not in result

    def test_get_topics_with_names_false(self):
        """Test getting topics grouped by category"""
        form_fields = {
            "fields": [
                {
                    "api_name": "inspectionTopics",
                    "selectoptions": {
                        "options": [
                            {"value": "1", "name": "Category1 Item1"},
                            {"value": "2", "name": "Category1 Item2"},
                            {"value": "3", "name": "Category2 Item3"},
                        ]
                    },
                }
            ]
        }
        form_data = {"inspection_topics": ["1", "2", "3"]}

        result = get_topics(form_fields, form_data, names=False)

        assert isinstance(result, dict)
        assert "Category1" in result
        assert "Category2" in result
        assert "Item1" in result["Category1"]
        assert "Item2" in result["Category1"]
        assert "Item3" in result["Category2"]

    def test_get_topics_with_api_name_camel_case(self):
        """Test with apiName in camelCase"""
        form_fields = {
            "fields": [
                {
                    "apiName": "inspectionTopics",
                    "selectoptions": {
                        "options": [{"value": "1", "name": "Topic Name1"}]
                    },
                }
            ]
        }
        form_data = {"inspection_topics": ["1"]}

        result = get_topics(form_fields, form_data, names=True)

        assert "Name1" in result

    def test_get_topics_with_no_matching_topics(self):
        """Test when no topics match"""
        form_fields = {
            "fields": [
                {
                    "api_name": "inspectionTopics",
                    "selectoptions": {
                        "options": [
                            {"value": "1", "name": "Topic Name1"},
                            {"value": "2", "name": "Topic Name2"},
                        ]
                    },
                }
            ]
        }
        form_data = {"inspection_topics": ["99"]}  # Non-existent topic

        result = get_topics(form_fields, form_data, names=True)

        assert result == []

    def test_get_topics_with_missing_inspection_topics_field(self):
        """Test when inspectionTopics field is missing"""
        form_fields = {"fields": [{"api_name": "otherField"}]}
        form_data = {"inspection_topics": ["1"]}

        result = get_topics(form_fields, form_data, names=True)

        assert result == []

    def test_get_topics_with_empty_form_data(self):
        """Test with empty form_data inspection_topics"""
        form_fields = {
            "fields": [
                {
                    "api_name": "inspectionTopics",
                    "selectoptions": {
                        "options": [{"value": "1", "name": "Topic Name1"}]
                    },
                }
            ]
        }
        form_data = {"inspection_topics": []}

        result = get_topics(form_fields, form_data, names=True)

        assert result == []


class TestGetFormFields(TestCase):
    """Tests for get_form_fields function"""

    def test_get_form_fields_with_valid_occurrence_type(self):
        """Test getting form fields from occurrence type"""
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [{"api_name": "field1"}, {"api_name": "field2"}]
        }

        result = get_form_fields(mock_occurrence_type)

        assert len(result) == 2
        assert result[0]["api_name"] == "field1"
        assert result[1]["api_name"] == "field2"

    def test_get_form_fields_with_exception(self):
        """Test when exception occurs"""
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = None

        result = get_form_fields(mock_occurrence_type)

        assert result == []

    def test_get_form_fields_with_missing_fields_key(self):
        """Test when fields key is missing"""
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {}

        result = get_form_fields(mock_occurrence_type)

        assert result == []


class TestFormFieldsDict(TestCase):
    """Tests for form_fields_dict function"""

    def test_form_fields_dict_with_api_name(self):
        """Test creating dict with api_name"""
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [
                {
                    "api_name": "field1",
                    "data_type": "string",
                    "autofill": True,
                },
                {
                    "api_name": "field2",
                    "data_type": "number",
                    "autofill": False,
                },
            ]
        }

        result = form_fields_dict(mock_occurrence_type)

        assert "field1" in result
        assert result["field1"]["data_type"] == "string"
        assert result["field1"]["autofill"] is True
        assert "field2" in result
        assert result["field2"]["data_type"] == "number"
        assert result["field2"]["autofill"] is False

    def test_form_fields_dict_with_camel_case_keys(self):
        """Test with camelCase keys (apiName, dataType, autoFill)"""
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [
                {
                    "apiName": "field1",
                    "dataType": "string",
                    "autoFill": True,
                }
            ]
        }

        result = form_fields_dict(mock_occurrence_type)

        assert "field1" in result
        assert result["field1"]["data_type"] == "string"
        assert result["field1"]["autofill"] is True

    def test_form_fields_dict_with_auto_fill_variations(self):
        """Test different auto_fill key variations"""
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [{"api_name": "field1", "data_type": "string", "auto_fill": True}]
        }

        result = form_fields_dict(mock_occurrence_type)

        assert result["field1"]["autofill"] is True


class TestGetFormMetadata(TestCase):
    """Tests for get_form_metadata function"""

    def test_get_form_metadata_with_manually_specified_field(self):
        """Test when field is manually specified"""
        form_data = {"field1": "value"}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [
                {
                    "api_name": "field1",
                    "data_type": "string",
                    "autofill": True,
                }
            ]
        }

        result = get_form_metadata(form_data, mock_occurrence_type, form_metadata={})

        assert "field1" in result
        assert result["field1"]["manually_specified"] is True

    def test_get_form_metadata_with_auto_filled_field(self):
        """Test when field is auto-filled (not in form_data)"""
        form_data = {}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [
                {
                    "api_name": "field1",
                    "data_type": "string",
                    "autofill": True,
                }
            ]
        }

        result = get_form_metadata(form_data, mock_occurrence_type)

        assert "field1" in result
        assert result["field1"]["manually_specified"] is False

    def test_get_form_metadata_removes_field_when_autofill_none(self):
        """Test removing field from metadata when autofill is None"""
        form_data = {}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [
                {
                    "api_name": "field1",
                    "data_type": "string",
                    "autofill": None,
                }
            ]
        }
        form_metadata = {"field1": {"manually_specified": True}}

        result = get_form_metadata(form_data, mock_occurrence_type, form_metadata)

        assert "field1" not in result

    def test_get_form_metadata_with_array_of_objects(self):
        """Test that arrayOfObjects data type is skipped"""
        form_data = {"field1": [{"a": 1}]}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [
                {
                    "api_name": "field1",
                    "data_type": "arrayOfObjects",
                    "autofill": True,
                }
            ]
        }

        result = get_form_metadata(form_data, mock_occurrence_type)

        assert "field1" not in result

    def test_get_form_metadata_with_camel_case_api_name(self):
        """Test with camelCase apiName"""
        form_data = {"field_one": "value"}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [
                {
                    "apiName": "fieldOne",
                    "dataType": "string",
                    "autoFill": True,
                }
            ]
        }

        result = get_form_metadata(form_data, mock_occurrence_type)

        assert "field_one" in result


class TestGetApiName(TestCase):
    """Tests for get_api_name function"""

    def test_get_api_name_with_api_name(self):
        """Test getting API name from api_name field"""
        field = {"api_name": "testField"}

        result = get_api_name(field)

        assert result == "test_field"

    def test_get_api_name_with_camel_case_api_name(self):
        """Test getting API name from apiName field (camelCase)"""
        field = {"apiName": "testField"}

        result = get_api_name(field)

        assert result == "test_field"

    def test_get_api_name_with_no_api_name(self):
        """Test when no API name field exists"""
        field = {"other_field": "value"}

        result = get_api_name(field)

        assert result is None

    def test_get_api_name_priority(self):
        """Test that apiName takes priority over api_name"""
        field = {"apiName": "camelCase", "api_name": "snake_case"}

        result = get_api_name(field)

        assert result == "camel_case"


class TestCleanFormData(TestCase):
    """Tests for clean_form_data function"""

    def test_clean_form_data_removes_invalid_fields(self):
        """Test that invalid fields are removed"""
        form_data = {
            "valid_field": "value1",
            "invalid_field": "value2",
            "another_valid": "value3",
        }
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [{"api_name": "validField"}, {"api_name": "anotherValid"}]
        }

        result = clean_form_data(form_data, mock_occurrence_type)

        assert "valid_field" in result
        assert "another_valid" in result
        assert "invalid_field" not in result

    def test_clean_form_data_keeps_only_defined_fields(self):
        """Test that only defined fields are kept"""
        form_data = {"field1": "a", "field2": "b", "field3": "c"}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {"fields": [{"api_name": "field1"}]}

        result = clean_form_data(form_data, mock_occurrence_type)

        assert len(result) == 1
        assert "field1" in result

    def test_clean_form_data_with_no_fields(self):
        """Test when form_fields has no fields key"""
        form_data = {"field1": "value"}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {}

        result = clean_form_data(form_data, mock_occurrence_type)

        assert result == {}

    def test_clean_form_data_with_empty_form_data(self):
        """Test with empty form_data"""
        form_data = {}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {"fields": [{"api_name": "field1"}]}

        result = clean_form_data(form_data, mock_occurrence_type)

        assert result == {}

    def test_clean_form_data_preserves_values(self):
        """Test that field values are preserved"""
        form_data = {"field1": "test_value", "field2": 123}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [{"api_name": "field1"}, {"api_name": "field2"}]
        }

        result = clean_form_data(form_data, mock_occurrence_type)

        assert result["field1"] == "test_value"
        assert result["field2"] == 123


class TestMergeMonitoringAndTherapyData(TestCase):
    """Tests for merge_monitoring_and_therapy_data function"""

    def test_merge_basic(self):
        """Test basic merge functionality works"""
        monitoring_form_data = {"campo1": "A", "campo2": "B", "campo3": "C"}
        therapy_item = {"campo4": "D", "campo5": "E"}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [
                {"api_name": "campo1"},
                {"api_name": "campo2"},
                {"api_name": "campo3"},
                {"api_name": "campo4"},
                {"api_name": "campo5"},
            ]
        }

        result = merge_monitoring_and_therapy_data(
            monitoring_form_data, therapy_item, mock_occurrence_type
        )

        assert result["campo1"] == "A"
        assert result["campo2"] == "B"
        assert result["campo3"] == "C"
        assert result["campo4"] == "D"
        assert result["campo5"] == "E"

    def test_merge_excludes_therapy_array(self):
        """Test that 'therapy' field is excluded from monitoring data"""
        monitoring_form_data = {
            "campo1": "A",
            "therapy": [{"item": "1"}, {"item": "2"}],
        }
        therapy_item = {"campo2": "B"}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [{"api_name": "campo1"}, {"api_name": "campo2"}]
        }

        result = merge_monitoring_and_therapy_data(
            monitoring_form_data, therapy_item, mock_occurrence_type
        )

        assert "therapy" not in result
        assert result["campo1"] == "A"
        assert result["campo2"] == "B"

    def test_merge_therapy_overwrites_monitoring(self):
        """Test that therapy_item values overwrite monitoring values"""
        monitoring_form_data = {"campo1": "original_value", "campo2": "B"}
        therapy_item = {"campo1": "new_value", "campo3": "C"}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [
                {"api_name": "campo1"},
                {"api_name": "campo2"},
                {"api_name": "campo3"},
            ]
        }

        result = merge_monitoring_and_therapy_data(
            monitoring_form_data, therapy_item, mock_occurrence_type
        )

        assert result["campo1"] == "new_value"
        assert result["campo2"] == "B"
        assert result["campo3"] == "C"

    def test_merge_cleans_invalid_fields(self):
        """Test that invalid fields are removed based on occurrence_type"""
        monitoring_form_data = {"valid_field1": "A", "invalid_field": "X"}
        therapy_item = {"valid_field2": "B", "another_invalid": "Y"}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [{"api_name": "valid_field1"}, {"api_name": "valid_field2"}]
        }

        result = merge_monitoring_and_therapy_data(
            monitoring_form_data, therapy_item, mock_occurrence_type
        )

        assert "valid_field1" in result
        assert "valid_field2" in result
        assert "invalid_field" not in result
        assert "another_invalid" not in result

    def test_merge_empty_therapy_item(self):
        """Test handling of empty therapy_item"""
        monitoring_form_data = {"campo1": "A", "campo2": "B"}
        therapy_item = {}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [{"api_name": "campo1"}, {"api_name": "campo2"}]
        }

        result = merge_monitoring_and_therapy_data(
            monitoring_form_data, therapy_item, mock_occurrence_type
        )

        assert result["campo1"] == "A"
        assert result["campo2"] == "B"

    def test_merge_empty_monitoring_data(self):
        """Test handling of empty monitoring_form_data"""
        monitoring_form_data = {}
        therapy_item = {"campo1": "A", "campo2": "B"}
        mock_occurrence_type = Mock()
        mock_occurrence_type.form_fields = {
            "fields": [{"api_name": "campo1"}, {"api_name": "campo2"}]
        }

        result = merge_monitoring_and_therapy_data(
            monitoring_form_data, therapy_item, mock_occurrence_type
        )

        assert result["campo1"] == "A"
        assert result["campo2"] == "B"
