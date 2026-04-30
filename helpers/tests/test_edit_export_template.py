import unittest

from helpers.edit_export.edit_export_template import EditTemplate


class TestEditExportTemplate(unittest.TestCase):
    """Test cases for EditTemplate.__filter_inline_options classmethod"""

    def test_filter_inline_options_without_options_filter(self):
        """Test that options are returned as-is when no optionsFilter is present"""
        field = {
            "dataType": "select",
            "selectOptions": {
                "options": [
                    {"name": "Option 1", "value": "1"},
                    {"name": "Option 2", "value": "2"},
                    {"name": "Option 3", "value": "3"},
                ]
            },
        }

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = ["Option 1", "Option 2", "Option 3"]
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_valid_options_filter(self):
        """Test that options are filtered correctly with valid optionsFilter"""
        field = {
            "dataType": "select",
            "selectOptions": {
                "options": [
                    {"name": "Option 1", "value": "1"},
                    {"name": "Option 2", "value": "2"},
                    {"name": "Option 3", "value": "3"},
                    {"name": "Option 4", "value": "4"},
                ],
                "optionsFilter": {
                    "filter": [
                        {"var": "options"},
                        {
                            "in": [
                                {"var": "value"},
                                [
                                    "1",
                                    "3",
                                    "5",
                                ],  # Only values 1 and 3 should be included
                            ]
                        },
                    ]
                },
            },
        }

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = ["Option 1", "Option 3"]  # Only options with values 1 and 3
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_invalid_options_filter_structure(self):
        """Test that all options are returned when optionsFilter has invalid structure"""
        field = {
            "dataType": "select",
            "selectOptions": {
                "options": [
                    {"name": "Option 1", "value": "1"},
                    {"name": "Option 2", "value": "2"},
                ],
                "optionsFilter": {
                    "invalidKey": "invalid"  # Should only contain 'filter' key
                },
            },
        }

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = [
            "Option 1",
            "Option 2",
        ]  # All options returned due to invalid structure
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_invalid_filter_array(self):
        """Test that all options are returned when filter array is invalid"""
        field = {
            "dataType": "select",
            "selectOptions": {
                "options": [
                    {"name": "Option 1", "value": "1"},
                    {"name": "Option 2", "value": "2"},
                ],
                "optionsFilter": {
                    "filter": [{"var": "options"}]  # Should have exactly 2 elements
                },
            },
        }

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = [
            "Option 1",
            "Option 2",
        ]  # All options returned due to invalid filter
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_invalid_first_element(self):
        """Test that all options are returned when first filter element is invalid"""
        field = {
            "dataType": "select",
            "selectOptions": {
                "options": [
                    {"name": "Option 1", "value": "1"},
                    {"name": "Option 2", "value": "2"},
                ],
                "optionsFilter": {
                    "filter": [
                        {"var": "invalid"},  # Should be "options"
                        {"in": [{"var": "value"}, ["1"]]},
                    ]
                },
            },
        }

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = [
            "Option 1",
            "Option 2",
        ]  # All options returned due to invalid first element
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_invalid_second_element(self):
        """Test that all options are returned when second filter element is invalid"""
        field = {
            "dataType": "select",
            "selectOptions": {
                "options": [
                    {"name": "Option 1", "value": "1"},
                    {"name": "Option 2", "value": "2"},
                ],
                "optionsFilter": {
                    "filter": [
                        {"var": "options"},
                        {"invalid": "structure"},  # Should have "in" key
                    ]
                },
            },
        }

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = [
            "Option 1",
            "Option 2",
        ]  # All options returned due to invalid second element
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_invalid_in_array(self):
        """Test that all options are returned when 'in' array is invalid"""
        field = {
            "dataType": "select",
            "selectOptions": {
                "options": [
                    {"name": "Option 1", "value": "1"},
                    {"name": "Option 2", "value": "2"},
                ],
                "optionsFilter": {
                    "filter": [
                        {"var": "options"},
                        {"in": [{"var": "value"}]},  # Should have exactly 2 elements
                    ]
                },
            },
        }

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = [
            "Option 1",
            "Option 2",
        ]  # All options returned due to invalid 'in' array
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_invalid_left_element(self):
        """Test that all options are returned when left element of 'in' array is invalid"""
        field = {
            "dataType": "select",
            "selectOptions": {
                "options": [
                    {"name": "Option 1", "value": "1"},
                    {"name": "Option 2", "value": "2"},
                ],
                "optionsFilter": {
                    "filter": [
                        {"var": "options"},
                        {"in": [{"var": "invalid"}, ["1"]]},  # Should be "value"
                    ]
                },
            },
        }

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = [
            "Option 1",
            "Option 2",
        ]  # All options returned due to invalid left element
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_non_array_whitelist(self):
        """Test that all options are returned when whitelist is not an array"""
        field = {
            "dataType": "select",
            "selectOptions": {
                "options": [
                    {"name": "Option 1", "value": "1"},
                    {"name": "Option 2", "value": "2"},
                ],
                "optionsFilter": {
                    "filter": [
                        {"var": "options"},
                        {
                            "in": [
                                {"var": "value"},
                                "not_an_array",  # Should be an array
                            ]
                        },
                    ]
                },
            },
        }

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = [
            "Option 1",
            "Option 2",
        ]  # All options returned due to invalid whitelist
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_exception(self):
        """Test that empty list is returned when an exception occurs"""
        field = {
            "dataType": "select",
            "selectOptions": None,  # This will cause an exception
        }

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = []  # Empty list due to exception
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_mixed_value_types(self):
        """Test that filtering works with mixed value types (string and integer)"""
        field = {
            "dataType": "select",
            "selectOptions": {
                "options": [
                    {"name": "Option 1", "value": 1},  # Integer
                    {"name": "Option 2", "value": "2"},  # String
                    {"name": "Option 3", "value": 3},  # Integer
                    {"name": "Option 4", "value": "4"},  # String
                ],
                "optionsFilter": {
                    "filter": [
                        {"var": "options"},
                        {
                            "in": [
                                {"var": "value"},
                                [1, "4"],  # Mixed types in whitelist
                            ]
                        },
                    ]
                },
            },
        }

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = ["Option 1", "Option 4"]  # Only options with values 1 and "4"
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_empty_options(self):
        """Test that empty list is returned when options is empty"""
        field = {"dataType": "select", "selectOptions": {"options": []}}

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = []
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_missing_select_options(self):
        """Test that empty list is returned when selectOptions is missing"""
        field = {"dataType": "select"}

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = []
        self.assertEqual(result, expected)

    def test_filter_inline_options_with_empty_whitelist(self):
        """Test that no options are returned when whitelist is empty"""
        field = {
            "dataType": "select",
            "selectOptions": {
                "options": [
                    {"name": "Option 1", "value": "1"},
                    {"name": "Option 2", "value": "2"},
                ],
                "optionsFilter": {
                    "filter": [
                        {"var": "options"},
                        {"in": [{"var": "value"}, []]},  # Empty whitelist
                    ]
                },
            },
        }

        result = EditTemplate._EditTemplate__filter_inline_options(field)
        expected = []  # No options should match empty whitelist
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
