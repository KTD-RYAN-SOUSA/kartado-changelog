import uuid
from collections import OrderedDict
from unittest.mock import Mock, patch

from django.test import TestCase

from helpers.apps.json_logic import (
    build_updated_logic,
    find_var_name_values,
    get_fields_options,
    update_data_with_possibilities,
)
from helpers.apps.record_filter import get_complex_translation, get_translation
from helpers.strings import keys_to_snake_case


class TestJsonLogic(TestCase):
    def setUp(self):
        """Setup test data"""
        self.company = Mock()
        self.company.id = uuid.uuid4()
        self.form_fields = [
            {
                "apiName": "simpleSelect",
                "dataType": "select",
                "selectOptions": {
                    "options": [
                        {"name": "Option 1", "value": "1"},
                        {"name": "Option 2", "value": "2"},
                    ]
                },
            },
            {
                "apiName": "referenceSelect",
                "dataType": "select",
                "selectOptions": {
                    "reference": {
                        "optionText": "name",
                        "optionValue": "id",
                        "resource": "OccurrenceType",
                    }
                },
            },
            {
                "apiName": "arrayField",
                "dataType": "arrayOfObjects",
                "innerFields": [
                    {
                        "apiName": "innerSelect",
                        "dataType": "select",
                        "selectOptions": {
                            "options": [
                                {"name": "Inner 1", "value": "1"},
                                {"name": "Inner 2", "value": "2"},
                            ]
                        },
                    }
                ],
            },
            {"apiName": "notes", "dataType": "textArea"},
        ]

    def test_get_fields_options(self):
        """Test getting field options from form fields"""

        # Mock OccurrenceType query for reference select
        mock_occurrences = [
            {"name": "Ref 1", "id": "r1"},
            {"name": "Ref 2", "id": "r2"},
        ]

        with patch(
            "apps.occurrence_records.models.OccurrenceType.objects.filter"
        ) as mock_filter:
            mock_filter.return_value.values.return_value = mock_occurrences

            # Test without company (should skip reference fields)
            result = get_fields_options(self.form_fields)

            # Verify simple select options
            assert "simpleSelect" in result
            assert result["simpleSelect"] == {"Option 1": "1", "Option 2": "2"}

            # Verify array field inner options
            assert "arrayField.innerSelect" in result
            assert result["arrayField.innerSelect"] == {
                "Inner 1": "1",
                "Inner 2": "2",
            }

            # Verify reference select is not included when no company
            assert "referenceSelect" not in result

            # Test with company (should include reference fields)
            result_with_company = get_fields_options(self.form_fields, self.company)

            # Verify reference select options are included
            assert "referenceSelect" in result_with_company
            assert result_with_company["referenceSelect"] == {
                "Ref 1": "r1",
                "Ref 2": "r2",
            }

            # Verify result is OrderedDict
            assert isinstance(result, OrderedDict)
            assert isinstance(result_with_company, OrderedDict)

            # Verify non-select field is not included
            assert "notes" not in result
            assert "notes" not in result_with_company

    def test_build_updated_logic(self):
        """Test building updated logic with varName references"""
        # Setup test data
        fields_to_options = OrderedDict(
            {
                "status": {"Active": "1", "Inactive": "0"},
                "risk.level": {"High": "3", "Medium": "2", "Low": "1"},
            }
        )

        data = {"formData": {"status": "1", "risk": [{"level": "3"}, {"level": "2"}]}}

        form_fields = [
            {
                "apiName": "status",
                "dataType": "select",
                "selectOptions": {
                    "options": [
                        {"name": "Active", "value": "1"},
                        {"name": "Inactive", "value": "0"},
                    ]
                },
            },
            {
                "apiName": "risk",
                "dataType": "arrayOfObjects",
                "innerFields": [
                    {
                        "apiName": "level",
                        "dataType": "select",
                        "selectOptions": {
                            "options": [
                                {"name": "High", "value": "3"},
                                {"name": "Medium", "value": "2"},
                                {"name": "Low", "value": "1"},
                            ]
                        },
                    }
                ],
            },
        ]

        # Test 1: Simple varName reference
        logic_simple = {
            "if": [{"==": [{"varName": "formData.status"}, "1"]}, "Active", "Inactive"]
        }
        var_names = ["formData.status"]
        result = build_updated_logic(
            logic_simple, fields_to_options, data, form_fields, var_names
        )
        assert "var" in result["if"][0]["=="][0]
        assert result["if"][0]["=="][0]["var"] == "varNamesOp.status<1>"

        # Test 2: Array of objects varName reference
        logic_array = {"merge": [{"varName": "formData.risk.level"}]}
        var_names = ["formData.risk.level"]
        result = build_updated_logic(
            logic_array, fields_to_options, data, form_fields, var_names
        )
        assert "merge" in result
        assert isinstance(result, dict)  # Check that result is a dictionary
        assert isinstance(result["merge"], list)  # Check that merge contains a list

        # Test 3: Complex nested logic
        logic_complex = {
            "and": [
                {"if": [{"==": [{"varName": "formData.status"}, "1"]}, True, False]},
                {"merge": [{"varName": "formData.risk.level"}]},
            ]
        }
        var_names = ["formData.status", "formData.risk.level"]
        result = build_updated_logic(
            logic_complex, fields_to_options, data, form_fields, var_names
        )

        # Verify complex structure
        assert "and" in result
        assert isinstance(result["and"], list)
        assert len(result["and"]) == 2
        assert "if" in result["and"][0]
        assert "merge" in result["and"][1]

        # Verify simple field transformation
        assert "var" in result["and"][0]["if"][0]["=="][0]
        assert result["and"][0]["if"][0]["=="][0]["var"] == "varNamesOp.status<1>"

        # Test 4: Empty or invalid logic
        result = build_updated_logic({}, fields_to_options, data, form_fields, [])
        assert result == {}

        result = build_updated_logic(None, fields_to_options, data, form_fields, [])
        assert result is None

        # Test 5: Logic with non-varName fields
        logic_mixed = {
            "if": [
                {"==": [{"var": "someField"}, "value"]},
                {"varName": "formData.status"},
                "default",
            ]
        }
        var_names = ["formData.status"]
        result = build_updated_logic(
            logic_mixed, fields_to_options, data, form_fields, var_names
        )
        assert "if" in result
        assert result["if"][0]["=="][0] == {"var": "someField"}
        assert "var" in result["if"][1]
        assert result["if"][1]["var"] == "varNamesOp.status<1>"

    def test_find_var_name_values(self):
        """Test finding varName values in different logic structures"""

        # Test 1: Simple logic with one varName
        logic_simple = {
            "if": [{"==": [{"varName": "formData.status"}, "1"]}, True, False]
        }
        result = find_var_name_values(logic_simple)
        assert len(result) == 1
        assert "formData.status" in result

        # Test 2: Logic with multiple varNames
        logic_multiple = {
            "and": [
                {"==": [{"varName": "formData.status"}, "1"]},
                {"==": [{"varName": "formData.type"}, "2"]},
                {"==": [{"varName": "formData.active"}, "true"]},
            ]
        }
        result = find_var_name_values(logic_multiple)
        assert len(result) == 3
        assert "formData.status" in result
        assert "formData.type" in result
        assert "formData.active" in result

        # Test 3: Nested logic with array fields
        logic_nested = {
            "if": [
                {
                    "merge": [
                        {"varName": "formData.items.status"},
                        {"varName": "formData.items.type"},
                    ]
                },
                {
                    "and": [
                        {"==": [{"varName": "formData.active"}, "true"]},
                        {"==": [{"varName": "formData.verified"}, "1"]},
                    ]
                },
                False,
            ]
        }
        result = find_var_name_values(logic_nested)
        assert len(result) == 4
        assert "formData.items.status" in result
        assert "formData.items.type" in result
        assert "formData.active" in result
        assert "formData.verified" in result

        # Test 4: Empty logic
        logic_empty = {}
        result = find_var_name_values(logic_empty)
        assert len(result) == 0

        # Test 5: Logic without varName
        logic_no_varname = {"if": [{"==": [{"var": "status"}, "1"]}, True, False]}
        data = {"formData": {"status": "1", "risk": [{"level": "3"}, {"level": "2"}]}}
        new_data, var_names = update_data_with_possibilities(
            data, logic_no_varname, get_fields_options(self.form_fields)
        )
        assert len(var_names) == 0
        assert new_data == data

        # Test 6: Logic with mixed var and varName
        logic_mixed = {
            "and": [
                {"==": [{"var": "status"}, "1"]},
                {"==": [{"varName": "formData.type"}, "2"]},
                {"merge": [{"var": "items"}, {"varName": "formData.items.status"}]},
            ]
        }
        result = find_var_name_values(logic_mixed)
        assert len(result) == 2
        assert "formData.type" in result
        assert "formData.items.status" in result

    def test_get_complex_translation(self):
        field = keys_to_snake_case(self.form_fields[0])
        values = ["1", "2"]

        result = get_complex_translation(field, values, [])

        assert result == ["option 1", "option 2"]

        values = "2"

        result = get_complex_translation(field, values, ["Test"])

        assert result == ["Test", "option 2"]

    def test_get_translation(self):

        form_data = {"simple_select": "2"}

        result = get_translation(form_data, self.form_fields, [])

        assert result == ["option 2"]

        form_data = {
            "simple_select": "2",
            "array_field": [
                {"inner_select": "2"},
                {"inner_select": "1"},
                {"inner_select": "2"},
            ],
        }

        result = get_translation(form_data, self.form_fields, [])

        assert result == ["option 2", "inner 2", "inner 1"]
