from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

pytestmark = pytest.mark.django_db


class TestGetRdoFileUrl(TestCase):
    """Tests for get_rdo_file_url function"""

    @patch("helpers.files.PrivateMediaStorage")
    def test_get_rdo_file_url_with_file(self, mock_storage_class):
        """Test getting RDO file URL when file exists"""
        from helpers.files import get_rdo_file_url

        mock_storage = Mock()
        mock_storage.get_available_name.return_value = "uploads/file.pdf"
        mock_storage.get_post_url.return_value = "https://s3.example.com/file.pdf"
        mock_storage_class.return_value = mock_storage

        mock_obj = Mock()
        mock_obj.upload.name = "uploads/file.pdf"

        result = get_rdo_file_url(mock_obj, field_name="upload")

        assert result == "https://s3.example.com/file.pdf"
        mock_storage.get_available_name.assert_called_once_with("uploads/file.pdf")
        mock_storage.get_post_url.assert_called_once_with("uploads/file.pdf")

    @patch("helpers.files.PrivateMediaStorage")
    def test_get_rdo_file_url_without_file(self, mock_storage_class):
        """Test getting RDO file URL when file doesn't exist"""
        from helpers.files import get_rdo_file_url

        mock_obj = Mock()
        mock_obj.upload = None

        result = get_rdo_file_url(mock_obj, field_name="upload")

        assert result == {}
        mock_storage_class.return_value.get_available_name.assert_not_called()

    @patch("helpers.files.PrivateMediaStorage")
    def test_get_rdo_file_url_with_custom_field_name(self, mock_storage_class):
        """Test getting RDO file URL with custom field name"""
        from helpers.files import get_rdo_file_url

        mock_storage = Mock()
        mock_storage.get_available_name.return_value = "docs/document.pdf"
        mock_storage.get_post_url.return_value = "https://s3.example.com/doc.pdf"
        mock_storage_class.return_value = mock_storage

        mock_obj = Mock()
        mock_obj.document.name = "docs/document.pdf"

        result = get_rdo_file_url(mock_obj, field_name="document")

        assert result == "https://s3.example.com/doc.pdf"
        mock_storage.get_available_name.assert_called_once_with("docs/document.pdf")


class TestGetUrl(TestCase):
    """Tests for get_url function"""

    @patch("helpers.files.PrivateMediaStorage")
    def test_get_url_with_file_not_found(self, mock_storage_class):
        """Test get_url when file is not found"""
        from helpers.files import get_url

        mock_storage = Mock()
        mock_storage.get_available_name.return_value = "file.pdf"
        mock_storage.get_post_url.return_value = "https://s3.example.com/file.pdf"
        mock_storage_class.return_value = mock_storage

        mock_obj = Mock()
        mock_obj.upload.name = "file.pdf"
        type(mock_obj.upload).size = property(
            Mock(side_effect=FileNotFoundError("File not found"))
        )

        result = get_url(mock_obj, field_name="upload")

        assert result == "https://s3.example.com/file.pdf"
        mock_storage.get_post_url.assert_called_once_with("file.pdf")

    @patch("helpers.files.PrivateMediaStorage")
    def test_get_url_with_other_exception(self, mock_storage_class):
        """Test get_url when other exception occurs"""
        from helpers.files import get_url

        mock_obj = Mock()
        type(mock_obj.upload).size = property(Mock(side_effect=ValueError("Error")))

        result = get_url(mock_obj, field_name="upload")

        assert result == {}
        mock_storage_class.assert_not_called()

    @patch("helpers.files.PrivateMediaStorage")
    def test_get_url_with_file_exists(self, mock_storage_class):
        """Test get_url when file exists (no exception)"""
        from helpers.files import get_url

        mock_obj = Mock()
        mock_obj.upload.size = 1024

        result = get_url(mock_obj, field_name="upload")

        assert result == {}
        mock_storage_class.assert_not_called()


class TestCheckEndpoint(TestCase):
    """Tests for check_endpoint function"""

    @patch("helpers.files.sleep")
    def test_check_endpoint_with_existing_file(self, mock_sleep):
        """Test check_endpoint when file exists"""
        from helpers.files import check_endpoint

        mock_file_obj = Mock()
        mock_file_obj.uuid = "test-uuid-123"

        mock_field = Mock()
        mock_field.storage.exists.return_value = True
        mock_field.size = 2048
        mock_field.storage.e_tag.return_value = '"abc123"'
        mock_field.name = "test.pdf"
        mock_file_obj.upload = mock_field

        response = check_endpoint(mock_file_obj, field_name="upload")

        assert response.data["type"] == "FileCheck"
        assert response.data["attributes"]["exists"] is True
        assert response.data["attributes"]["size"] == 2048
        assert response.data["attributes"]["md5"] == "abc123"
        assert response.data["attributes"]["uuid"] == "test-uuid-123"
        assert response.data["attributes"]["deleted"] is False

    @patch("helpers.files.sleep")
    def test_check_endpoint_with_nonexistent_file(self, mock_sleep):
        """Test check_endpoint when file doesn't exist"""
        from helpers.files import check_endpoint

        mock_file_obj = Mock()
        mock_file_obj.uuid = "test-uuid-456"
        mock_file_obj.delete.return_value = (1, {})  # Deleted 1 object

        mock_field = Mock()
        mock_field.storage.exists.return_value = False
        mock_field.name = "missing.pdf"
        mock_file_obj.upload = mock_field

        response = check_endpoint(mock_file_obj, field_name="upload")

        assert mock_sleep.call_count == 5
        mock_file_obj.delete.assert_called_once()
        assert response.data["attributes"]["exists"] is False
        assert response.data["attributes"]["deleted"] is True

    @patch("helpers.files.sleep")
    def test_check_endpoint_with_no_field(self, mock_sleep):
        """Test check_endpoint when field doesn't exist on object"""
        from helpers.files import check_endpoint

        mock_file_obj = Mock()
        mock_file_obj.uuid = "test-uuid-789"
        mock_file_obj.upload = None

        response = check_endpoint(mock_file_obj, field_name="upload")

        assert response.data["attributes"]["exists"] is False
        assert response.data["attributes"]["size"] is None
        assert response.data["attributes"]["md5"] is None
        assert response.data["attributes"]["deleted"] is False

    @patch("helpers.files.sleep")
    def test_check_endpoint_retry_logic(self, mock_sleep):
        """Test that check_endpoint retries up to 5 times"""
        from helpers.files import check_endpoint

        mock_file_obj = Mock()
        mock_file_obj.uuid = "retry-test"
        mock_file_obj.delete.return_value = (1, {})

        mock_field = Mock()
        mock_field.storage.exists.side_effect = [False, False, True]
        mock_field.size = 1024
        mock_field.storage.e_tag.return_value = '"xyz789"'
        mock_field.name = "test.pdf"
        mock_file_obj.upload = mock_field

        response = check_endpoint(mock_file_obj, field_name="upload")

        assert mock_sleep.call_count == 2
        assert response.data["attributes"]["exists"] is True
        assert response.data["attributes"]["deleted"] is False


class TestGetResizedUrl(TestCase):
    """Tests for get_resized_url function"""

    def test_get_resized_url_with_400px(self):
        """Test getting resized URL for 400px"""
        from helpers.files import get_resized_url

        mock_file = Mock()
        mock_file.name = "images/photo.jpg"

        mock_storage = Mock()
        mock_storage._normalize_name.return_value = "images/photo.jpg"
        mock_storage.querystring_expire = 3600
        mock_storage.querystring_auth = True
        mock_storage.bucket.name = "my-bucket"

        mock_connection = Mock()
        mock_connection.meta.client.generate_presigned_url.return_value = (
            "https://s3.example.com/my-bucket-400px/images/photo.jpg?signature=abc"
        )
        mock_storage.connection = mock_connection
        mock_file.storage = mock_storage

        result = get_resized_url(mock_file, size=400)

        assert "my-bucket-400px" in result
        mock_connection.meta.client.generate_presigned_url.assert_called_once()
        call_args = mock_connection.meta.client.generate_presigned_url.call_args
        assert call_args[0][0] == "get_object"
        assert call_args[1]["Params"]["Bucket"] == "my-bucket-400px"

    def test_get_resized_url_with_1000px(self):
        """Test getting resized URL for 1000px"""
        from helpers.files import get_resized_url

        mock_file = Mock()
        mock_file.name = "images/photo.jpg"

        mock_storage = Mock()
        mock_storage._normalize_name.return_value = "images/photo.jpg"
        mock_storage.querystring_expire = 3600
        mock_storage.querystring_auth = True
        mock_storage.bucket.name = "my-bucket"

        mock_connection = Mock()
        mock_connection.meta.client.generate_presigned_url.return_value = (
            "https://s3.example.com/my-bucket-1000px/images/photo.jpg?signature=xyz"
        )
        mock_storage.connection = mock_connection
        mock_file.storage = mock_storage

        result = get_resized_url(mock_file, size=1000)

        assert "my-bucket-1000px" in result
        call_args = mock_connection.meta.client.generate_presigned_url.call_args
        assert call_args[1]["Params"]["Bucket"] == "my-bucket-1000px"

    def test_get_resized_url_with_invalid_size(self):
        """Test that invalid size raises ValueError"""
        from helpers.files import get_resized_url

        mock_file = Mock()

        with self.assertRaises(ValueError) as context:
            get_resized_url(mock_file, size=500)

        assert "Size must be either 400 or 1000" in str(context.exception)

    def test_get_resized_url_with_unsigned_connection(self):
        """Test with unsigned connection when querystring_auth is False"""
        from helpers.files import get_resized_url

        mock_file = Mock()
        mock_file.name = "images/photo.jpg"

        mock_storage = Mock()
        mock_storage._normalize_name.return_value = "images/photo.jpg"
        mock_storage.querystring_expire = 3600
        mock_storage.querystring_auth = False
        mock_storage.bucket.name = "public-bucket"

        mock_unsigned_connection = Mock()
        mock_unsigned_connection.meta.client.generate_presigned_url.return_value = (
            "https://s3.example.com/public-bucket-400px/images/photo.jpg"
        )
        mock_storage.unsigned_connection = mock_unsigned_connection
        mock_file.storage = mock_storage

        result = get_resized_url(mock_file, size=400)

        mock_unsigned_connection.meta.client.generate_presigned_url.assert_called_once()
        assert "public-bucket-400px" in result
