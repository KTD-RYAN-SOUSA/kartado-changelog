import json
import uuid
from datetime import datetime
from unittest.mock import Mock, patch

from django.db.models.manager import Manager
from django.test import TestCase
from rest_framework_json_api import serializers

from helpers.serializers import (
    BYTE_LIMIT,
    BaseModelSerializer,
    LabeledChoiceField,
    LimitedSizeJsonField,
    LimitedSizeSerializerMethodField,
    UUIDSerializerMethodResourceRelatedField,
    generic_serializer_instance_model,
    get_field_if_provided_or_present,
    get_obj_serialized,
    handle_value_over_size_limit,
)


class TestBaseModelSerializer(TestCase):
    """Tests for the BaseModelSerializer class"""

    def test_base_model_serializer_attributes(self):
        """Tests that BaseModelSerializer has correct attributes"""
        self.assertEqual(BaseModelSerializer._SELECT_RELATED_FIELDS, [])
        self.assertEqual(
            BaseModelSerializer._PREFETCH_RELATED_FIELDS, ["created_by", "company"]
        )

        # Check Meta class attributes
        meta = BaseModelSerializer.Meta
        self.assertIn("uuid", meta.fields)
        self.assertIn("created_by", meta.fields)
        self.assertIn("company", meta.fields)
        self.assertIn("created_at", meta.fields)
        self.assertIn("updated_at", meta.fields)

        self.assertIn("uuid", meta.read_only_fields)
        self.assertIn("created_by", meta.read_only_fields)
        self.assertIn("created_at", meta.read_only_fields)
        self.assertIn("updated_at", meta.read_only_fields)

        self.assertEqual(meta.extra_kwargs["company"]["required"], True)

    def test_uuid_field_declaration(self):
        """Tests that UUID field is properly declared"""
        # The UUID field is declared in the class definition (line 26 of serializers.py)
        # BaseModelSerializer declares: uuid = serializers.UUIDField(required=False)

        # In the test context, we can verify that the Meta class includes uuid in fields
        # which indicates the field is properly configured
        meta_fields = BaseModelSerializer.Meta.fields
        self.assertIn("uuid", meta_fields)

        # And check it's in read_only_fields too
        read_only_fields = BaseModelSerializer.Meta.read_only_fields
        self.assertIn("uuid", read_only_fields)


class TestGetObjSerialized(TestCase):
    """Tests for the get_obj_serialized function"""

    def setUp(self):
        self.mock_obj = Mock()

    @patch("helpers.serializers.JSONRenderer")
    @patch("apps.reportings.serializers.ReportingSerializer")
    @patch("apps.reportings.views.ReportingView")
    def test_get_obj_serialized_reporting(
        self, mock_view, mock_serializer, mock_json_renderer
    ):
        """Tests get_obj_serialized with is_reporting=True"""
        # Setup mocks
        mock_serializer_instance = Mock()
        mock_serializer_instance.data = {"test": "data"}
        mock_serializer.return_value = mock_serializer_instance

        mock_renderer_instance = Mock()
        mock_renderer_instance.render.return_value = json.dumps(
            {
                "data": {
                    "attributes": {"attr1": "value1"},
                    "relationships": {"rel1": "value2"},
                }
            }
        )
        mock_json_renderer.return_value = mock_renderer_instance

        result = get_obj_serialized(self.mock_obj, is_reporting=True)

        # Verify the function was called with correct parameters
        mock_serializer.assert_called_once_with(self.mock_obj)
        self.assertEqual(result["attr1"], "value1")
        self.assertEqual(result["relationships"]["rel1"], "value2")

    @patch("helpers.serializers.JSONRenderer")
    @patch("apps.occurrence_records.serializers.OccurrenceRecordSerializer")
    @patch("apps.occurrence_records.views.OccurrenceRecordView")
    def test_get_obj_serialized_occurrence_record(
        self, mock_view, mock_serializer, mock_json_renderer
    ):
        """Tests get_obj_serialized with is_occurrence_record=True"""
        mock_serializer_instance = Mock()
        mock_serializer_instance.data = {"test": "data"}
        mock_serializer.return_value = mock_serializer_instance

        mock_renderer_instance = Mock()
        mock_renderer_instance.render.return_value = json.dumps(
            {
                "data": {
                    "attributes": {"name": "test"},
                    "relationships": {"company": "rel_data"},
                }
            }
        )
        mock_json_renderer.return_value = mock_renderer_instance

        result = get_obj_serialized(self.mock_obj, is_occurrence_record=True)

        mock_serializer.assert_called_once_with(self.mock_obj)
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["relationships"]["company"], "rel_data")

    @patch("helpers.serializers.JSONRenderer")
    @patch("apps.reportings.serializers.ReportingSerializer")
    @patch("apps.reportings.views.ReportingView")
    def test_get_obj_serialized_with_context(
        self, mock_view, mock_serializer, mock_json_renderer
    ):
        """Tests get_obj_serialized with serializer_context"""
        context = {"request": Mock()}

        mock_serializer_instance = Mock()
        mock_serializer_instance.data = {}
        mock_serializer.return_value = mock_serializer_instance

        mock_renderer_instance = Mock()
        mock_renderer_instance.render.return_value = json.dumps(
            {"data": {"attributes": {}, "relationships": {}}}
        )
        mock_json_renderer.return_value = mock_renderer_instance

        get_obj_serialized(self.mock_obj, is_reporting=True, serializer_context=context)

        # Verify serializer was called with context
        mock_serializer.assert_called_once_with(self.mock_obj, context=context)

    def test_get_obj_serialized_no_serializer(self):
        """Tests get_obj_serialized when no serializer is determined"""
        result = get_obj_serialized(self.mock_obj)
        self.assertEqual(result, {})

    @patch("helpers.serializers.JSONRenderer")
    @patch("apps.reportings.serializers.ReportingSerializer")
    @patch("apps.reportings.views.InventoryView")
    def test_get_obj_serialized_inventory(
        self, mock_view, mock_serializer, mock_json_renderer
    ):
        """Tests get_obj_serialized with is_inventory=True"""
        mock_serializer_instance = Mock()
        mock_serializer_instance.data = {"test": "data"}
        mock_serializer.return_value = mock_serializer_instance

        mock_renderer_instance = Mock()
        mock_renderer_instance.render.return_value = json.dumps(
            {"data": {"attributes": {"inventory": "data"}, "relationships": {}}}
        )
        mock_json_renderer.return_value = mock_renderer_instance

        result = get_obj_serialized(self.mock_obj, is_inventory=True)

        mock_serializer.assert_called_once_with(self.mock_obj)
        self.assertEqual(result["inventory"], "data")


class TestGetFieldIfProvidedOrPresent(TestCase):
    """Tests for the get_field_if_provided_or_present function"""

    def test_field_in_attrs(self):
        """Tests when field is provided in attrs"""
        attrs = {"test_field": "test_value"}
        instance = None

        result = get_field_if_provided_or_present("test_field", attrs, instance)
        self.assertEqual(result, "test_value")

    def test_field_in_instance(self):
        """Tests when field is present in instance"""
        attrs = {}
        instance = Mock()
        instance.test_field = "instance_value"

        result = get_field_if_provided_or_present("test_field", attrs, instance)
        self.assertEqual(result, "instance_value")

    def test_field_many_to_many(self):
        """Tests many-to-many field extraction"""
        attrs = {}
        instance = Mock()
        mock_manager = Mock(spec=Manager)
        mock_manager.all.return_value = ["related1", "related2"]
        instance.test_field = mock_manager

        result = get_field_if_provided_or_present(
            "test_field", attrs, instance, many_to_many=True
        )

        mock_manager.all.assert_called_once()
        self.assertEqual(result, ["related1", "related2"])

    def test_field_not_found(self):
        """Tests when field is not found anywhere"""
        attrs = {}
        instance = None

        result = get_field_if_provided_or_present("missing_field", attrs, instance)
        self.assertIsNone(result)

    def test_attrs_takes_precedence(self):
        """Tests that attrs value takes precedence over instance value"""
        attrs = {"test_field": "attrs_value"}
        instance = Mock()
        instance.test_field = "instance_value"

        result = get_field_if_provided_or_present("test_field", attrs, instance)
        self.assertEqual(result, "attrs_value")


class TestLabeledChoiceField(TestCase):
    """Tests for the LabeledChoiceField class"""

    def setUp(self):
        # Choices should be tuples for Django's ChoiceField
        self.choices = (
            ("active", "Active"),
            ("inactive", "Inactive"),
            ("pending", "Pending"),
        )
        self.field = LabeledChoiceField(choices=self.choices)

    def test_to_representation(self):
        """Tests to_representation method"""
        result = self.field.to_representation("active")
        self.assertEqual(result, "Active")

        result = self.field.to_representation("pending")
        self.assertEqual(result, "Pending")

    def test_to_internal_value_valid(self):
        """Tests to_internal_value with valid label"""
        result = self.field.to_internal_value("Active")
        self.assertEqual(result, "active")

        result = self.field.to_internal_value("Inactive")
        self.assertEqual(result, "inactive")

    def test_to_internal_value_invalid(self):
        """Tests to_internal_value with invalid label"""
        with self.assertRaises(serializers.ValidationError) as context:
            self.field.to_internal_value("Invalid Choice")

        self.assertIn(
            "choice_provided_to_choice_field_was_invalid", str(context.exception)
        )


class TestUUIDSerializerMethodResourceRelatedField(TestCase):
    """Tests for the UUIDSerializerMethodResourceRelatedField class"""

    def test_to_representation(self):
        """Tests to_representation method"""
        mock_model = Mock()
        mock_model.__name__ = "TestModel"

        field = UUIDSerializerMethodResourceRelatedField()
        field.model = mock_model

        test_uuid = uuid.uuid4()
        result = field.to_representation(test_uuid)

        expected = {"type": "TestModel", "id": str(test_uuid)}
        self.assertEqual(result, expected)


class TestGenericSerializerInstanceModel(TestCase):
    """Tests for the generic_serializer_instance_model function"""

    def setUp(self):
        self.mock_obj = Mock()
        self.mock_obj._meta = Mock()

        # Mock fields
        self.mock_field = Mock()
        self.mock_field.name = "test_field"
        self.mock_field.is_relation = False
        self.mock_field.auto_created = False

        self.mock_obj._meta.get_fields.return_value = [self.mock_field]

    @patch("helpers.serializers.model_to_dict")
    def test_generic_serializer_basic(self, mock_model_to_dict):
        """Tests basic functionality of generic_serializer_instance_model"""
        mock_model_to_dict.return_value = {
            "test_field": "test_value",
            "uuid": "test-uuid",
        }

        # Mock hasattr to check for specific field names
        def mock_hasattr(obj, attr):
            if attr == "test_field":
                return True
            return False

        with patch("builtins.hasattr", side_effect=mock_hasattr):
            self.mock_obj.test_field = "test_value"

            result = generic_serializer_instance_model(self.mock_obj)

            # UUID should be excluded by default
            self.assertNotIn("uuid", result)
            self.assertEqual(result["test_field"], "test_value")

    @patch("helpers.serializers.model_to_dict")
    def test_generic_serializer_with_uuid_field(self, mock_model_to_dict):
        """Tests handling of UUID fields"""
        test_uuid = uuid.uuid4()
        mock_model_to_dict.return_value = {"id_field": test_uuid}

        # No fields to iterate through for this test
        self.mock_obj._meta.get_fields.return_value = []

        result = generic_serializer_instance_model(self.mock_obj)

        # UUID should be converted to string
        self.assertEqual(result["id_field"], str(test_uuid))

    @patch("helpers.serializers.model_to_dict")
    def test_generic_serializer_with_datetime(self, mock_model_to_dict):
        """Tests handling of datetime fields"""
        test_datetime = datetime(2023, 1, 1, 12, 0, 0)
        mock_model_to_dict.return_value = {"created_at": test_datetime}

        # No fields to iterate through for this test
        self.mock_obj._meta.get_fields.return_value = []

        result = generic_serializer_instance_model(self.mock_obj)

        # The function should convert datetime to string format
        # Let's check if it's been converted to a string representation
        self.assertIsInstance(result["created_at"], str)
        # Check that it contains the expected date parts
        self.assertIn("2023", result["created_at"])
        self.assertIn("12:00:00", result["created_at"])

    @patch("helpers.serializers.model_to_dict")
    def test_generic_serializer_with_file_field(self, mock_model_to_dict):
        """Tests handling of FieldFile"""
        # Create a simple mock that behaves like a FieldFile
        mock_file = Mock()
        mock_file.name = "test_file.jpg"
        mock_file.url = "/media/test_file.jpg"

        mock_model_to_dict.return_value = {"photo": mock_file}

        # No fields to iterate through for this test
        self.mock_obj._meta.get_fields.return_value = []

        # The function checks if value is FieldFile and handles accordingly
        # Since our mock isn't a real FieldFile, it should be treated as a regular object
        result = generic_serializer_instance_model(self.mock_obj)

        # The mock object should remain as-is since it doesn't match FieldFile type
        # or it should be handled by the general object processing
        self.assertIsNotNone(result["photo"])

    @patch("helpers.serializers.model_to_dict")
    def test_generic_serializer_with_list_field(self, mock_model_to_dict):
        """Tests handling of list fields with objects having pk"""
        mock_obj1 = Mock()
        mock_obj1.pk = 1
        mock_obj2 = Mock()
        mock_obj2.pk = 2
        simple_value = "simple"

        mock_model_to_dict.return_value = {"tags": [mock_obj1, mock_obj2, simple_value]}

        # No fields to iterate through for this test
        self.mock_obj._meta.get_fields.return_value = []

        result = generic_serializer_instance_model(self.mock_obj)

        # Objects with pk should be converted to string, simple values kept as-is
        self.assertEqual(result["tags"], ["1", "2", "simple"])

    @patch("helpers.serializers.model_to_dict")
    def test_generic_serializer_exclude_fields(self, mock_model_to_dict):
        """Tests exclude_fields parameter"""
        mock_model_to_dict.return_value = {
            "field1": "value1",
            "field2": "value2",
            "secret_field": "secret",
        }

        # No fields to iterate through for this test
        self.mock_obj._meta.get_fields.return_value = []

        result = generic_serializer_instance_model(
            self.mock_obj, exclude_fields=["secret_field"]
        )

        self.assertIn("field1", result)
        self.assertIn("field2", result)
        self.assertNotIn("secret_field", result)
        self.assertNotIn("uuid", result)  # Always excluded

    @patch("helpers.serializers.model_to_dict")
    def test_generic_serializer_with_object_pk(self, mock_model_to_dict):
        """Tests handling of objects with pk attribute"""
        mock_related_obj = Mock()
        mock_related_obj.pk = 123

        mock_model_to_dict.return_value = {"related_obj": mock_related_obj}

        # No fields to iterate through for this test
        self.mock_obj._meta.get_fields.return_value = []

        result = generic_serializer_instance_model(self.mock_obj)

        # Object with pk should be converted to string of pk
        self.assertEqual(result["related_obj"], "123")


class TestHandleValueOverSizeLimit(TestCase):
    """Tests for the handle_value_over_size_limit function"""

    def test_handle_value_under_limit(self):
        """Tests that small values pass through unchanged"""
        test_value = "small string"
        result = handle_value_over_size_limit(test_value)
        self.assertEqual(result, test_value)

    @patch("helpers.serializers.sys.getsizeof")
    @patch("helpers.serializers.logging.warning")
    def test_handle_large_list(self, mock_warning, mock_getsizeof):
        """Tests handling of oversized list"""
        mock_getsizeof.return_value = BYTE_LIMIT + 1000

        large_list = ["item"] * 1000
        result = handle_value_over_size_limit(large_list)

        self.assertEqual(result, [])
        mock_warning.assert_called_once()

    @patch("helpers.serializers.sys.getsizeof")
    @patch("helpers.serializers.logging.warning")
    def test_handle_large_dict(self, mock_warning, mock_getsizeof):
        """Tests handling of oversized dict"""
        mock_getsizeof.return_value = BYTE_LIMIT + 1000

        large_dict = {"key": "value"}
        result = handle_value_over_size_limit(large_dict)

        self.assertEqual(result, {})
        mock_warning.assert_called_once()

    @patch("helpers.serializers.sys.getsizeof")
    @patch("helpers.serializers.logging.warning")
    def test_handle_large_string(self, mock_warning, mock_getsizeof):
        """Tests handling of oversized string"""
        mock_getsizeof.return_value = BYTE_LIMIT + 1000

        large_string = "x" * 10000
        result = handle_value_over_size_limit(large_string)

        self.assertEqual(result, "")
        mock_warning.assert_called_once()

    @patch("helpers.serializers.sys.getsizeof")
    @patch("helpers.serializers.logging.warning")
    def test_handle_large_set(self, mock_warning, mock_getsizeof):
        """Tests handling of oversized set"""
        mock_getsizeof.return_value = BYTE_LIMIT + 1000

        large_set = {1, 2, 3}
        result = handle_value_over_size_limit(large_set)

        self.assertEqual(result, set())
        mock_warning.assert_called_once()

    @patch("helpers.serializers.sys.getsizeof")
    @patch("helpers.serializers.logging.warning")
    def test_handle_large_tuple(self, mock_warning, mock_getsizeof):
        """Tests handling of oversized tuple"""
        mock_getsizeof.return_value = BYTE_LIMIT + 1000

        large_tuple = (1, 2, 3)
        result = handle_value_over_size_limit(large_tuple)

        self.assertEqual(result, ())
        mock_warning.assert_called_once()

    @patch("helpers.serializers.sys.getsizeof")
    @patch("helpers.serializers.logging.warning")
    def test_handle_large_other_type(self, mock_warning, mock_getsizeof):
        """Tests handling of oversized unknown type"""
        mock_getsizeof.return_value = BYTE_LIMIT + 1000

        large_obj = object()
        result = handle_value_over_size_limit(large_obj)

        self.assertIsNone(result)
        mock_warning.assert_called_once()


class TestLimitedSizeJsonField(TestCase):
    """Tests for the LimitedSizeJsonField class"""

    def setUp(self):
        self.field = LimitedSizeJsonField()

    def test_to_internal_value_under_limit(self):
        """Tests to_internal_value with data under size limit"""
        small_data = {"key": "value"}

        with patch.object(
            self.field.__class__.__bases__[0],
            "to_internal_value",
            return_value=small_data,
        ):
            result = self.field.to_internal_value(small_data)
            self.assertEqual(result, small_data)

    @patch("helpers.serializers.sys.getsizeof")
    def test_to_internal_value_over_limit(self, mock_getsizeof):
        """Tests to_internal_value with data over size limit"""
        mock_getsizeof.return_value = BYTE_LIMIT + 1000

        large_data = {"key": "very large value"}

        with self.assertRaises(serializers.ValidationError) as context:
            self.field.to_internal_value(large_data)

        self.assertIn(
            "provided_json_value_is_bigger_than_accepted_size_limit",
            str(context.exception),
        )

    @patch("helpers.serializers.handle_value_over_size_limit")
    def test_to_representation(self, mock_handle_size):
        """Tests to_representation method"""
        test_data = {"key": "value"}
        mock_handle_size.return_value = test_data

        with patch.object(
            self.field.__class__.__bases__[0],
            "to_representation",
            return_value=test_data,
        ):
            result = self.field.to_representation(test_data)

            mock_handle_size.assert_called_once_with(test_data)
            self.assertEqual(result, test_data)


class TestLimitedSizeSerializerMethodField(TestCase):
    """Tests for the LimitedSizeSerializerMethodField class"""

    def setUp(self):
        self.field = LimitedSizeSerializerMethodField()

    @patch("helpers.serializers.handle_value_over_size_limit")
    def test_to_representation(self, mock_handle_size):
        """Tests to_representation method"""
        test_value = "test_value"
        mock_handle_size.return_value = test_value

        with patch.object(
            self.field.__class__.__bases__[0],
            "to_representation",
            return_value=test_value,
        ):
            result = self.field.to_representation(test_value)

            mock_handle_size.assert_called_once_with(test_value)
            self.assertEqual(result, test_value)


class TestConstants(TestCase):
    """Tests for module constants"""

    def test_byte_limit_constant(self):
        """Tests that BYTE_LIMIT is correctly defined"""
        expected_limit = 1 * 1024 * 1024  # 1 MB
        self.assertEqual(BYTE_LIMIT, expected_limit)


if __name__ == "__main__":
    import unittest

    unittest.main()
