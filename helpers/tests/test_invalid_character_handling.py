from helpers.strings import clean_invalid_characters


class TestCleanInvalidCharacters:
    def test_clean_invalid_characters_dict(self):
        input_data = {"key1": "valid_string", "key2": "invalid\x00string"}
        expected_output = {"key1": "valid_string", "key2": "invalidstring"}
        assert clean_invalid_characters(input_data) == expected_output

    def test_clean_invalid_characters_list(self):
        input_data = ["valid_string", "invalid\x01string"]
        expected_output = ["valid_string", "invalidstring"]
        assert clean_invalid_characters(input_data) == expected_output

    def test_clean_invalid_characters_string(self):
        input_data = "invalid\x02string"
        expected_output = "invalidstring"
        assert clean_invalid_characters(input_data) == expected_output

    def test_clean_invalid_characters_tuple(self):
        input_data = ("valid_bytes", "invalid\x00bytes")
        expected_output = ("valid_bytes", "invalidbytes")
        assert clean_invalid_characters(input_data) == expected_output

    def test_clean_invalid_characters_set(self):
        input_data = {"key1", "valid_string", "invalid\x01bytes"}
        expected_output = {"key1", "valid_string", "invalidbytes"}
        assert clean_invalid_characters(input_data) == expected_output

    def test_clean_invalid_characters_complex_dict(self):
        input_data = {
            "key1": "valid_string",
            "key2": ["valid_list_string", "invalid\x00list_string"],
            "key3": ("valid_tuple_string", "invalid\x01tuple_string"),
            "key4": {"valid_set_string", "invalid\x02set_string"},
            "key5": 12345,
        }
        expected_output = {
            "key1": "valid_string",
            "key2": ["valid_list_string", "invalidlist_string"],
            "key3": ("valid_tuple_string", "invalidtuple_string"),
            "key4": {"valid_set_string", "invalidset_string"},
            "key5": 12345,
        }
        output = clean_invalid_characters(input_data)

        for key in expected_output.keys():
            assert output[key] == expected_output[key], key
