from unittest.mock import Mock, patch

from django.test import TestCase

from helpers.import_excel.shared_functions import (
    shared_clean_up,
    shared_download_excel_file,
    shared_is_hidden_sheet,
    shared_load_data,
    shared_update_column_errors,
)


class TestSharedFunctions(TestCase):
    """Tests for shared Excel import functions"""

    def test_shared_update_column_errors_without_mapping(self):
        """Test updating column errors without column mapping"""
        # Setup
        item_dict = {"column_errors": ["error1"]}
        column_errors = ["error2", "error3"]

        # Execute
        result = shared_update_column_errors(item_dict, column_errors)

        # Verify
        expected = ["error1", "error2", "error3"]
        self.assertEqual(set(result["column_errors"]), set(expected))

    def test_shared_update_column_errors_with_mapping(self):
        """Test updating column errors with column mapping"""
        # Setup
        item_dict = {"column_errors": ["error1"]}
        column_errors = ["error2", "error3"]
        column_mapping = {"error2": "mapped_error2", "error3": "mapped_error3"}

        # Execute
        result = shared_update_column_errors(item_dict, column_errors, column_mapping)

        # Verify
        expected = ["error1", "mapped_error2", "mapped_error3"]
        self.assertEqual(set(result["column_errors"]), set(expected))

    def test_shared_update_column_errors_empty_initial(self):
        """Test updating column errors with empty initial errors"""
        # Setup
        item_dict = {}
        column_errors = ["error1", "error2"]

        # Execute
        result = shared_update_column_errors(item_dict, column_errors)

        # Verify
        self.assertEqual(set(result["column_errors"]), set(column_errors))

    @patch("helpers.import_excel.shared_functions.boto3.client")
    def test_shared_download_excel_file_success(self, mock_boto3_client):
        """Test successful file download from S3"""
        # Setup
        mock_excel_import = Mock()
        mock_excel_import.excel_file.url = (
            "https://bucket.s3.amazonaws.com/path/file.xlsx"
        )
        mock_excel_import.pk = "123"

        mock_s3 = Mock()
        mock_boto3_client.return_value = mock_s3

        temp_path = "/tmp/test/"

        # Execute
        result = shared_download_excel_file(mock_excel_import, temp_path, mock_s3)

        # Verify
        expected_path = f"{temp_path}file_123.xlsx"
        mock_s3.download_file.assert_called_once_with(
            "bucket", "path/file.xlsx", expected_path
        )
        self.assertEqual(result, expected_path)

    @patch("helpers.import_excel.shared_functions.boto3.client")
    def test_shared_download_excel_file_no_s3_client(self, mock_boto3_client):
        """Test file download when s3_client is not provided"""
        # Setup
        mock_excel_import = Mock()
        mock_excel_import.excel_file.url = (
            "https://bucket.s3.amazonaws.com/path/file.xlsx"
        )
        mock_excel_import.pk = "123"

        mock_s3 = Mock()
        mock_boto3_client.return_value = mock_s3

        temp_path = "/tmp/test/"

        # Execute
        result = shared_download_excel_file(mock_excel_import, temp_path)

        expected_path = f"{temp_path}file_123.xlsx"
        mock_s3.download_file.assert_called_once_with(
            "bucket", "path/file.xlsx", expected_path
        )
        self.assertEqual(result, expected_path)

    def test_shared_download_excel_file_no_file(self):
        """Test download with no excel file"""
        # Setup
        mock_excel_import = Mock()
        mock_excel_import.excel_file = None

        # Execute
        result = shared_download_excel_file(mock_excel_import, "/tmp/test/")

        # Verify
        self.assertEqual(result, "")

    @patch("helpers.import_excel.shared_functions.openpyxl")
    def test_shared_load_data_with_openpyxl(self, mock_openpyxl):
        """Test loading data with openpyxl"""
        # Setup
        mock_workbook = Mock()
        mock_openpyxl.load_workbook.return_value = mock_workbook

        # Execute
        result = shared_load_data("test.xlsx", use_openpyxl=True)

        # Verify
        mock_openpyxl.load_workbook.assert_called_once_with(filename="test.xlsx")
        self.assertEqual(result, mock_workbook)

    @patch("helpers.import_excel.shared_functions.load_workbook")
    def test_shared_load_data_without_openpyxl(self, mock_load_workbook):
        """Test loading data without openpyxl"""
        # Setup
        mock_workbook = Mock()
        mock_load_workbook.return_value = mock_workbook

        # Execute
        result = shared_load_data("test.xlsx", use_openpyxl=False)

        # Verify
        mock_load_workbook.assert_called_once_with(filename="test.xlsx")
        self.assertEqual(result, mock_workbook)

    def test_shared_load_data_exception(self):
        """Test loading data with exception"""
        # Execute
        result = shared_load_data("nonexistent.xlsx")

        # Verify
        self.assertIsNone(result)

    def test_shared_is_hidden_sheet_hidden(self):
        """Test checking hidden sheet"""
        # Setup
        mock_worksheet = Mock()
        mock_worksheet.sheet_state = "hidden"

        # Execute & Verify
        self.assertTrue(shared_is_hidden_sheet(mock_worksheet))

    def test_shared_is_hidden_sheet_very_hidden(self):
        """Test checking very hidden sheet"""
        # Setup
        mock_worksheet = Mock()
        mock_worksheet.sheet_state = "veryHidden"

        # Execute & Verify
        self.assertTrue(shared_is_hidden_sheet(mock_worksheet))

    def test_shared_is_hidden_sheet_visible(self):
        """Test checking visible sheet"""
        # Setup
        mock_worksheet = Mock()
        mock_worksheet.sheet_state = "visible"

        # Execute & Verify
        self.assertFalse(shared_is_hidden_sheet(mock_worksheet))

    @patch("helpers.import_excel.shared_functions.os.path.exists")
    @patch("helpers.import_excel.shared_functions.os.remove")
    @patch("helpers.import_excel.shared_functions.os.listdir")
    @patch("helpers.import_excel.shared_functions.os.rmdir")
    def test_shared_clean_up_success(
        self, mock_rmdir, mock_listdir, mock_remove, mock_exists
    ):
        """Test successful cleanup"""
        # Setup
        mock_exists.return_value = True
        mock_listdir.return_value = []

        # Execute
        shared_clean_up("test.xlsx", "/tmp/test/")

        # Verify
        mock_remove.assert_called_once_with("test.xlsx")
        mock_rmdir.assert_called_once_with("/tmp/test/")

    @patch("helpers.import_excel.shared_functions.os.path.exists")
    @patch("helpers.import_excel.shared_functions.os.remove")
    @patch("helpers.import_excel.shared_functions.logging.error")
    def test_shared_clean_up_exception(
        self, mock_logging_error, mock_remove, mock_exists
    ):
        """Test cleanup with exception"""
        # Setup
        mock_exists.return_value = True
        mock_remove.side_effect = Exception("Test error")

        # Execute
        shared_clean_up("test.xlsx", "/tmp/test/")

        # Verify
        mock_logging_error.assert_called_once_with("Error cleaning up: Test error")
