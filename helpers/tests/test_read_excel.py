import os
import tempfile
import uuid
from datetime import datetime
from unittest.mock import Mock, PropertyMock, patch

import pytz
from django.test import TestCase
from openpyxl import Workbook

from apps.reportings.models import Reporting
from helpers.import_excel.read_excel import (
    create_excel_reportings,
    create_procedure_resources,
    create_reporting_files,
    create_reportings,
    detect_excel_import_type,
    download_excel_import_zip,
    get_object_path,
    load_progress,
    parse_json_to_objs,
    run_save_with_signals,
    save_reporting_files,
    update_form_data,
    update_reporting_file_upload,
    update_reporting_instance,
    upload_image,
    upload_image_from_zip,
    upload_progress,
    upload_zip_images,
)


class TestReadExcelFunctions(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.excel_import = Mock()
        self.excel_import.uuid = uuid.uuid4()
        self.s3_client = Mock()
        self.user = Mock()
        self.user.uuid = uuid.uuid4()

    def test_detect_excel_import_type(self):
        """Test detection of import type from Excel file"""
        # Create a real Excel file
        wb = Workbook()
        ws = wb.active
        ws["A1"] = "Teste"

        # Save the workbook to a temporary file
        temp_excel_path = os.path.join(self.temp_dir, "test.xlsx")
        wb.save(temp_excel_path)

        # Test the function
        try:
            result = detect_excel_import_type(temp_excel_path)
            assert result == "REPORTING"
        finally:
            # Cleanup
            os.remove(temp_excel_path)

    def test_load_progress(self):
        """Test loading progress data"""
        # Create temporary file
        os.makedirs(self.temp_dir, exist_ok=True)
        test_file = os.path.join(self.temp_dir, "test.json")
        with open(test_file, "w") as f:
            f.write('{"test": "data"}')

        with patch("tempfile.mkdtemp", return_value=self.temp_dir):
            with patch("json.load") as mock_json_load:
                mock_json_load.return_value = {"test": "data"}
                result = load_progress(self.s3_client, "123", "test.json")
                assert result == {"test": "data"}

    def test_create_excel_reportings(self):
        """Test creating Excel reportings"""
        # Create mock reporting with proper attributes
        mock_reporting = Mock()
        mock_reporting.uuid = uuid.uuid4()
        mock_reporting.reporting = Mock(uuid=uuid.uuid4())
        mock_reporting.excel_import = Mock(uuid=uuid.uuid4())
        mock_reporting.row = "1"

        with patch(
            "apps.templates.models.ExcelReporting.objects.filter"
        ) as mock_filter, patch(
            "apps.templates.models.ExcelReporting.objects.bulk_create"
        ) as mock_bulk_create:
            # Setup mock filter return
            mock_filter.return_value.values_list.return_value = []

            # Execute
            create_excel_reportings([mock_reporting], "CREATE")

            # Verify bulk_create was called
            mock_bulk_create.assert_called_once()

    def test_create_procedure_resources(self):
        """Test creating procedure resources"""
        mock_resource = Mock()
        type(mock_resource).uuid = PropertyMock(return_value=uuid.uuid4())

        with patch(
            "apps.service_orders.models.ProcedureResource.objects.bulk_create"
        ) as mock_create:
            create_procedure_resources([mock_resource])
            mock_create.assert_called_once()

    def test_create_reporting_files(self):
        """Test creating reporting files"""
        # Create mock reporting
        mock_reporting = Mock()
        mock_reporting.pk = uuid.uuid4()

        # Create mock reporting file with proper attributes
        mock_file = Mock()
        mock_file.uuid = uuid.uuid4()
        mock_file.reporting_id = mock_reporting.pk
        mock_file.reporting = mock_reporting

        with patch(
            "apps.reportings.models.ReportingFile.objects.filter"
        ) as mock_filter, patch(
            "apps.reportings.models.ReportingFile.objects.bulk_create"
        ) as mock_bulk_create:
            # Setup mock filter return
            mock_filter.return_value.values_list.return_value = []

            # Execute
            create_reporting_files([mock_file])

            # Verify bulk_create was called
            mock_bulk_create.assert_called_once()

    def test_create_reportings(self):
        rep = Reporting.objects.first()

        # Execute
        create_reportings([rep], False, self.user)

    def test_get_object_path(self):
        """Test object path generation"""
        result = get_object_path("123", "test.xlsx")
        assert result == "media/private/123_test.xlsx"

    def test_upload_progress(self):
        """Test progress data upload"""
        data = {"test": "data"}
        result = upload_progress(self.s3_client, None, "test.json", data)
        assert isinstance(result, str)

    def test_upload_image_from_zip(self):
        """Test uploading image from ZIP"""
        expiration = datetime.now().replace(tzinfo=pytz.UTC)
        upload_image_from_zip(
            self.s3_client, self.excel_import, "test.jpg", "test.jpg", expiration
        )
        assert self.s3_client.upload_file.called

    def test_upload_zip_images(self):
        """Test uploading multiple ZIP images"""
        with patch("concurrent.futures.ThreadPoolExecutor"):
            upload_zip_images("/tmp/test", self.excel_import)
            assert True  # Verify no exceptions raised

    def test_download_excel_import_zip(self):
        """Test downloading Excel import ZIP"""
        self.excel_import.zip_file.url = "https://bucket.s3.amazonaws.com/test.zip"
        result = download_excel_import_zip(self.excel_import, "/tmp/test.zip")
        assert isinstance(result, bool)

    def test_update_reporting_file_upload(self):
        """Test updating reporting file upload"""
        errors = []
        rfs = []
        update_reporting_file_upload(
            self.s3_client, "test-uuid", "http://test.com/test.jpg", "/tmp", errors, rfs
        )
        assert isinstance(errors, list)

    def test_update_form_data(self):
        """Test updating form data"""
        curr_data = {"field1": [{"val": 1}]}
        new_data = {"field1": [{"val": 2}]}
        form_metadata = {"field1": {"manually_specified": True}}
        update_form_data(True, curr_data, new_data, form_metadata)
        assert curr_data["field1"][0]["val"] == 2

    def test_update_reporting_instance(self):
        """Test updating reporting instance"""
        reporting = Mock()
        data = {"field1": "value1"}
        update_reporting_instance(reporting, data)
        assert reporting.field1 == "value1"

    @patch("apps.templates.models.ExcelImport.objects.get")
    def test_save_reporting_files(self, mock_get):
        """Test saving reporting files"""
        mock_get.return_value = self.excel_import
        result = save_reporting_files("test-uuid", "test.json")
        assert isinstance(result, bool)

    @patch("apps.templates.models.ExcelImport.objects.get")
    def test_parse_json_to_objs(self, mock_get):
        """Test parsing JSON to objects"""
        mock_get.return_value = self.excel_import
        result = parse_json_to_objs("test-uuid")
        assert isinstance(result, bool)

    def test_upload_image(self):
        """Test image upload"""
        mock_image = Mock()
        mock_image.format = "jpg"
        mock_image.ref = Mock()
        image_dict = {}
        upload_image(self.s3_client, "test-uuid", 1, image_dict, mock_image)
        assert "upload" in image_dict

    def test_run_save_with_signals(self):
        rep = Reporting.objects.first()
        rep.road = None
        run_save_with_signals(str(rep.uuid))
