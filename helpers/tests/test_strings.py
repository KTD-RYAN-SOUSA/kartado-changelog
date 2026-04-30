import unittest
import uuid
from unittest.mock import Mock, patch

from django.test import TestCase

from helpers.strings import (  # Constants; Functions
    COMMON_DOC_TYPE,
    COMMON_IMAGE_TYPE,
    DAY_WEEK,
    ILLEGAL_CHARACTERS,
    MAPS_MONTHS_ENG_TO_PT,
    UF_CODE,
    build_ecm_query,
    check_image_file,
    clean_invalid_characters,
    clean_latin_string,
    clean_string,
    decode_slash,
    deep_keys_to_snake_case,
    deg_to_dms,
    dict_to_casing,
    dict_to_upper_camel_case,
    encode_slash,
    format_km,
    generate_random_string,
    get_all_dict_paths,
    get_obj_from_path,
    get_random_color,
    get_value_from_obj,
    int_set_zero_prefix,
    is_valid_uuid,
    iter_items_to_str,
    keys_to_camel_case,
    keys_to_snake_case,
    minutes_to_hour_str,
    path_from_dict,
    remove_ext_in_filename,
    remove_random_string_file_name_in_upload,
    str_hours_to_int,
    to_camel_case,
    to_flatten_str,
    to_snake_case,
    to_upper_camel_case,
    translate_custom_options,
)


class TestConstantes(TestCase):
    """Tests for constants defined in the strings module"""

    def test_illegal_characters(self):
        """Tests if ILLEGAL_CHARACTERS contains valid control characters"""
        self.assertIsInstance(ILLEGAL_CHARACTERS, list)
        self.assertTrue(len(ILLEGAL_CHARACTERS) > 0)
        # Check if it contains specific control characters
        self.assertIn("\x00", ILLEGAL_CHARACTERS)
        self.assertIn("\x01", ILLEGAL_CHARACTERS)

    def test_common_image_type(self):
        """Tests if COMMON_IMAGE_TYPE contains valid image extensions"""
        self.assertIsInstance(COMMON_IMAGE_TYPE, list)
        self.assertIn("png", COMMON_IMAGE_TYPE)
        self.assertIn("jpg", COMMON_IMAGE_TYPE)
        self.assertIn("jpeg", COMMON_IMAGE_TYPE)

    def test_common_doc_type(self):
        """Tests if COMMON_DOC_TYPE contains valid document extensions"""
        self.assertIsInstance(COMMON_DOC_TYPE, list)
        self.assertIn("txt", COMMON_DOC_TYPE)
        self.assertIn("doc", COMMON_DOC_TYPE)
        self.assertIn("docx", COMMON_DOC_TYPE)

    def test_uf_code(self):
        """Tests if UF_CODE contains correct UF code mappings"""
        self.assertIsInstance(UF_CODE, dict)
        self.assertEqual(UF_CODE["11"], "RO")
        self.assertEqual(UF_CODE["35"], "SP")
        self.assertEqual(UF_CODE["33"], "RJ")

    def test_day_week(self):
        """Tests if DAY_WEEK contains weekdays in Portuguese"""
        self.assertIsInstance(DAY_WEEK, list)
        self.assertEqual(len(DAY_WEEK), 7)
        self.assertIn("Segunda-Feira", DAY_WEEK)
        self.assertIn("Domingo", DAY_WEEK)

    def test_maps_months_eng_to_pt(self):
        """Tests if MAPS_MONTHS_ENG_TO_PT maps months correctly"""
        self.assertIsInstance(MAPS_MONTHS_ENG_TO_PT, dict)
        self.assertEqual(MAPS_MONTHS_ENG_TO_PT["January"], "janeiro")
        self.assertEqual(MAPS_MONTHS_ENG_TO_PT["December"], "dezembro")


class TestStringUtilities(TestCase):
    """Tests for string utility functions"""

    def test_clean_latin_string(self):
        """Tests accent removal from strings"""
        self.assertEqual(clean_latin_string("São Paulo"), "Sao Paulo")
        self.assertEqual(clean_latin_string("João"), "Joao")
        self.assertEqual(clean_latin_string("Ação"), "Acao")
        self.assertEqual(clean_latin_string("normal"), "normal")

    def test_encode_decode_slash(self):
        """Tests slash encoding and decoding"""
        test_string = "path/to/file"
        encoded = encode_slash(test_string)
        self.assertEqual(encoded, "path%2Fto%2Ffile")

        decoded = decode_slash(encoded)
        self.assertEqual(decoded, test_string)

    def test_to_snake_case(self):
        """Tests conversion to snake_case"""
        self.assertEqual(to_snake_case("camelCase"), "camel_case")
        self.assertEqual(to_snake_case("PascalCase"), "pascal_case")
        self.assertEqual(to_snake_case("XMLParser"), "xml_parser")
        self.assertEqual(to_snake_case("simpleword"), "simpleword")

    def test_to_camel_case(self):
        """Tests conversion to camelCase"""
        self.assertEqual(to_camel_case("snake_case"), "snakeCase")
        self.assertEqual(to_camel_case("simple_word"), "simpleWord")
        self.assertEqual(to_camel_case("single"), "single")

    def test_to_flatten_str(self):
        """Tests conversion to flattened string"""
        self.assertEqual(to_flatten_str("camelCase"), "camelcase")
        self.assertEqual(to_flatten_str("snake_case"), "snakecase")
        self.assertEqual(to_flatten_str("kebab-case"), "kebabcase")

    def test_clean_string(self):
        """Tests string cleaning with emojis and line breaks"""
        # Test with emoji
        string_with_emoji = "Hello 😀 World"
        cleaned = clean_string(string_with_emoji)
        self.assertEqual(
            cleaned, "Hello World"
        )  # Emojis are removed, multiple spaces become one

        # Test with line break
        string_with_newline = "Line 1\nLine 2"
        cleaned = clean_string(string_with_newline)
        self.assertEqual(cleaned, "Line 1")  # Only gets the first line

    def test_clean_invalid_characters(self):
        """Tests removal of invalid characters"""
        # Test with string
        dirty_string = "Clean\x00string\x01"
        clean = clean_invalid_characters(dirty_string)
        self.assertEqual(clean, "Cleanstring")

        # Test with dictionary
        dirty_dict = {"key": "value\x00"}
        clean_dict = clean_invalid_characters(dirty_dict)
        self.assertEqual(clean_dict, {"key": "value"})

        # Test with list
        dirty_list = ["item1\x01", "item2"]
        clean_list = clean_invalid_characters(dirty_list)
        self.assertEqual(clean_list, ["item1", "item2"])


class TestCaseConversion(TestCase):
    """Tests for case conversion in dictionaries"""

    def test_keys_to_snake_case(self):
        """Tests conversion of keys to snake_case"""
        input_dict = {"camelCase": "value", "PascalCase": "value2"}
        result = keys_to_snake_case(input_dict)
        expected = {"camel_case": "value", "pascal_case": "value2"}
        self.assertEqual(result, expected)

    def test_keys_to_camel_case(self):
        """Tests conversion of keys to camelCase"""
        input_dict = {"snake_case": "value", "another_key": "value2"}
        result = keys_to_camel_case(input_dict)
        expected = {"snakeCase": "value", "anotherKey": "value2"}
        self.assertEqual(result, expected)

    def test_dict_to_casing_camelize(self):
        """Tests dictionary conversion to camelCase"""
        input_dict = {
            "snake_case": "value",
            "nested_dict": {"inner_key": "inner_value"},
        }
        result = dict_to_casing(input_dict, "camelize")
        expected = {"snakeCase": "value", "nestedDict": {"innerKey": "inner_value"}}
        self.assertEqual(result, expected)

    def test_dict_to_casing_underscore(self):
        """Tests dictionary conversion to snake_case"""
        input_dict = {"camelCase": "value", "nestedDict": {"innerKey": "inner_value"}}
        result = dict_to_casing(input_dict, "underscore")
        expected = {"camel_case": "value", "nested_dict": {"inner_key": "inner_value"}}
        self.assertEqual(result, expected)

    def test_deep_keys_to_snake_case(self):
        """Tests deep conversion of keys to snake_case"""
        input_data = {
            "camelCase": "value",
            "nestedDict": {
                "innerCamelCase": "inner_value",
                "deeperNested": {"veryDeepKey": "deep_value"},
            },
        }
        result = deep_keys_to_snake_case(input_data)
        expected = {
            "camel_case": "value",
            "nested_dict": {
                "inner_camel_case": "inner_value",
                "deeper_nested": {"very_deep_key": "deep_value"},
            },
        }
        self.assertEqual(result, expected)

    def test_to_upper_camel_case(self):
        """Tests conversion of strings to UpperCamelCase"""
        input_list = ["UpperCamelCase", "camelCase", "snake_case", "simpleword"]
        expected = ["UpperCamelCase", "CamelCase", "SnakeCase", "Simpleword"]
        result = [to_upper_camel_case(word) for word in input_list]
        self.assertEqual(result, expected)

    def test_dict_to_upper_camel_case(self):
        """Tests conversion of dicts root keys to UpperCamelCase"""
        input_list = {
            "UpperCamelCase": "value",
            "camelCase": "value",
            "snake_case": "value",
            "simpleword": "value",
        }
        expected = {
            "UpperCamelCase": "value",
            "CamelCase": "value",
            "SnakeCase": "value",
            "Simpleword": "value",
        }
        result = dict_to_upper_camel_case(input_list)
        self.assertEqual(result, expected)


class TestFileUtilities(TestCase):
    """Tests for file-related functions"""

    def test_check_image_file(self):
        """Tests image file verification"""
        self.assertTrue(check_image_file("image.png"))
        self.assertTrue(check_image_file("photo.jpg"))
        self.assertTrue(check_image_file("LOGO.PNG"))
        self.assertFalse(check_image_file("document.pdf"))
        self.assertFalse(check_image_file("script.py"))

    def test_remove_ext_in_filename(self):
        """Tests file extension removal from filename"""
        self.assertEqual(remove_ext_in_filename("file.txt"), "file")
        self.assertEqual(remove_ext_in_filename("image.png"), "image")
        self.assertEqual(remove_ext_in_filename("file.backup.zip"), "file.backup")

    def test_remove_random_string_file_name_in_upload(self):
        """Tests random string removal from upload filename"""
        self.assertEqual(
            remove_random_string_file_name_in_upload("file_abc123"), "file"
        )
        self.assertEqual(
            remove_random_string_file_name_in_upload("document_xyz789"), "document"
        )
        self.assertEqual(
            remove_random_string_file_name_in_upload("singlename"), "singlename"
        )


class TestTimeUtilities(TestCase):
    """Tests for time-related functions"""

    def test_minutes_to_hour_str(self):
        """Tests conversion from minutes to hour string"""
        self.assertEqual(minutes_to_hour_str(90), "01:30")
        self.assertEqual(minutes_to_hour_str(60), "01:00")
        self.assertEqual(minutes_to_hour_str(45), "00:45")
        self.assertEqual(minutes_to_hour_str(125), "02:05")

    def test_str_hours_to_int(self):
        """Tests conversion from hour string to minutes"""
        self.assertEqual(str_hours_to_int("01:30"), 90)
        self.assertEqual(str_hours_to_int("01:00"), 60)
        self.assertEqual(str_hours_to_int("00:45"), 45)
        self.assertEqual(str_hours_to_int("02:05"), 125)
        self.assertEqual(str_hours_to_int(123), 0)  # Test with non-string


class TestDictUtilities(TestCase):
    """Tests for dictionary-related functions"""

    def test_path_from_dict(self):
        """Tests path creation from dictionaries"""
        input_dict = {
            "key1": "value1",
            "key2": {"nested_key": "nested_value"},
            "date_field": "2023-01-01",
        }
        result = path_from_dict(input_dict)
        self.assertIsInstance(result, dict)
        self.assertIn("key1", result)
        self.assertIn("key2__nested_key", result)

    def test_get_all_dict_paths(self):
        """Tests getting all paths from a dictionary"""
        input_dict = {"level1": {"level2": {"level3": "value"}}}
        result = get_all_dict_paths(input_dict)
        self.assertIsInstance(result, list)
        self.assertTrue(any("level1__level2__level3" in path for path in result))

    def test_get_obj_from_path(self):
        """Tests getting objects from paths"""
        input_dict = {"level1": {"level2": {"target": "found"}}}
        result = get_obj_from_path(input_dict, "level1__level2")
        self.assertEqual(result, {"target": "found"})

        # Test with invalid path
        result = get_obj_from_path(input_dict, "invalid__path")
        self.assertEqual(result, [])

    def test_get_value_from_obj(self):
        """Tests getting value from object and path"""
        obj = {
            "options": [
                {"name": "Option 1", "value": "opt1"},
                {"name": "Option 2", "value": "opt2"},
            ]
        }
        result = get_value_from_obj(obj, "options", "opt1")
        self.assertEqual(result, "Option 1")

        # Test with value not found
        result = get_value_from_obj(obj, "options", "opt3")
        self.assertEqual(result, "")


class TestValidationUtilities(TestCase):
    """Tests for validation functions"""

    def test_is_valid_uuid(self):
        """Tests UUID validation"""
        valid_uuid = str(uuid.uuid4())
        self.assertTrue(is_valid_uuid(valid_uuid))

        self.assertFalse(is_valid_uuid("invalid-uuid"))
        self.assertFalse(is_valid_uuid("12345"))
        self.assertFalse(is_valid_uuid(""))

    def test_iter_items_to_str(self):
        """Tests conversion of iterable items to string"""
        input_list = [1, 2.5, True, None]
        result = iter_items_to_str(input_list)
        expected = ["1", "2.5", "True", "None"]
        self.assertEqual(result, expected)


class TestNumberUtilities(TestCase):
    """Tests for number-related functions"""

    def test_int_set_zero_prefix(self):
        """Tests adding zero prefix to numbers"""
        # Function has complex logic - let's test the real behavior
        self.assertEqual(int_set_zero_prefix(5, 3), "005")
        self.assertEqual(int_set_zero_prefix(50, 3), "050")
        self.assertEqual(
            int_set_zero_prefix(500, 3), 500
        )  # Returns original value when no prefix needed
        self.assertEqual(int_set_zero_prefix(5000, 3), 5000)  # Returns original value

    def test_deg_to_dms(self):
        """Tests conversion from decimal degrees to degrees, minutes and seconds"""
        # Test with latitude
        result = deg_to_dms(-23.5505, "lat")
        self.assertIn("23º", result)
        self.assertIn("S", result)

        # Test with longitude
        result = deg_to_dms(-46.6333, "lon")
        self.assertIn("46º", result)
        self.assertIn("W", result)


class TestRandomUtilities(TestCase):
    """Tests for functions that generate random values"""

    def test_get_random_color(self):
        """Tests random color generation"""
        color = get_random_color()
        self.assertTrue(color.startswith("#"))
        self.assertEqual(len(color), 7)  # #RRGGBB

    def test_generate_random_string(self):
        """Tests random string generation"""
        random_str = generate_random_string(10)
        self.assertEqual(len(random_str), 10)

        # Test with different length
        random_str = generate_random_string(5)
        self.assertEqual(len(random_str), 5)

        # Test that generated strings are different
        str1 = generate_random_string(10)
        str2 = generate_random_string(10)
        self.assertNotEqual(str1, str2)


class TestFormatKm(TestCase):
    """Tests for the format_km function"""

    def test_format_km(self):
        """Tests kilometer formatting"""
        # Mock an object with attribute
        mock_reporting = Mock()
        mock_reporting.distance = 1.234

        result = format_km(mock_reporting, "distance", 3)  # With padding 3
        self.assertEqual(result, "001+234")

        # Test with smaller padding
        result = format_km(mock_reporting, "distance", 0)
        self.assertEqual(result, "1+234")

    def test_format_km_exception(self):
        """Tests format_km with exception"""
        mock_reporting = Mock()
        mock_reporting.invalid_field = "not_a_number"

        result = format_km(mock_reporting, "invalid_field")
        self.assertEqual(result, "")


class TestECMUtilities(TestCase):
    """Tests for ECM-related functions"""

    @patch("helpers.strings.settings")
    @patch("helpers.strings.credentials")
    def test_build_ecm_query(self, mock_credentials, mock_settings):
        """Tests ECM query building"""
        mock_settings.ECM_SEARCH_URL_INITIAL = "http://example.com/search?"
        mock_credentials.ECM_SEARCH_URL_FINAL = "&final=true"

        values = [
            {"campo": "field1", "valor": "value1", "operacao": "AND"},
            {"campo": "field2", "valor": "value2", "operacao": "OR"},
        ]

        result = build_ecm_query(values, "registro")
        self.assertIn("field1", result)
        self.assertIn("value1", result)
        self.assertIn("DPSPATIMOBRO", result)


class TestTranslateCustomOptions(TestCase):
    """Tests for custom options translation"""

    def test_translate_custom_options(self):
        """Tests custom options translation"""
        custom_options = {
            "model": {
                "fields": {
                    "field": {
                        "selectoptions": {
                            "options": [
                                {"name": "Option 1", "value": "opt1"},
                                {"name": "Option 2", "value": "opt2"},
                            ]
                        }
                    }
                }
            }
        }

        result = translate_custom_options(custom_options, "model", "field", "opt1")
        self.assertEqual(result, "Option 1")

        # Test with value not found
        result = translate_custom_options(custom_options, "model", "field", "opt3")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
