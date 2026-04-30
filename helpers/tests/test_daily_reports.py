from datetime import time
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.daily_reports.models import (
    DailyReportExport,
    MultipleDailyReport,
    MultipleDailyReportFile,
)
from helpers.apps.daily_reports import generate_exported_file, parse_extra_hours_to_list
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


def mock_get_obj_from_path(metadata, path, separator="__", default_return=[]):
    if path == "can_view_digital_signature":
        return True
    return default_return


class TestDailyReportExport(TestBase):
    model = "Helpers"

    @pytest.mark.django_db
    def test_generate_exported_with_compiled_file(self):
        """Test the generate_exported function of a DailyReportExport with complied equal True."""

        multiple_daily_report = MultipleDailyReport.objects.first()

        # Create DailyReportExport with is_compiled equal True
        daily_report_export = DailyReportExport.objects.create(
            created_by=self.user,
            is_compiled=True,
            format="EXCEL",
            done=False,
            error=False,
            sort="date",
            order="asc",
        )

        # Add ManyToMany relationships
        daily_report_export.multiple_daily_reports.add(multiple_daily_report)

        # Create fake file
        test_file = SimpleUploadedFile(
            "test.pdf", b"arquivo de teste", content_type="application/pdf"
        )

        # Create MultipleDailyReportFile
        MultipleDailyReportFile.objects.create(
            multiple_daily_report=multiple_daily_report,
            description="Arquivo de teste",
            md5="abc123def456",
            upload=test_file,
            uploaded_at=timezone.now(),
            datetime=timezone.now(),
            created_by=self.user,
            kind="durante",
        )

        generate_exported_file(str(daily_report_export.uuid))

        # Refresh DailyReportExport
        daily_report_export.refresh_from_db()

        assert daily_report_export.done is True
        assert daily_report_export.error is False

    @patch("helpers.apps.daily_reports.os.rmdir")
    def test_generate_exported_with_non_compiled_file(self, mock_rmdir):
        """Test the generate_exported function of a DailyReportExport with complied equal False."""

        mock_rmdir.return_value = None

        multiple_daily_report = MultipleDailyReport.objects.first()

        # Create DailyReportExport with is_compiled equal False
        daily_report_export = DailyReportExport.objects.create(
            created_by=self.user,
            is_compiled=False,
            format="EXCEL",
            done=False,
            error=False,
            sort="date",
            order="asc",
        )

        # Add ManyToMany relationships
        daily_report_export.multiple_daily_reports.add(multiple_daily_report)

        # Create fake file
        test_file = SimpleUploadedFile(
            "test.pdf", b"arquivo de teste", content_type="application/pdf"
        )

        # Create MultipleDailyReportFile
        MultipleDailyReportFile.objects.create(
            multiple_daily_report=multiple_daily_report,
            description="Arquivo de teste",
            md5="abc123def456",
            upload=test_file,
            uploaded_at=timezone.now(),
            datetime=timezone.now(),
            created_by=self.user,
            kind="durante",
        )

        generate_exported_file(str(daily_report_export.uuid))

        # Refresh DailyReportExport
        daily_report_export.refresh_from_db()

        assert daily_report_export.done is True
        assert daily_report_export.error is False

    @patch("helpers.apps.daily_reports.ImageFont")
    @patch("openpyxl.drawing.image.Image")
    @patch("helpers.apps.daily_reports.NamedTemporaryFile")
    @patch("helpers.apps.daily_reports.requests.post")
    def test_generate_exported_with_non_compiled_pdf_file(
        self, mock_requests_post, mock_temp_file, mock_image, mock_image_font
    ):
        """Test the generate_exported function of a DailyReportExport with complied equal False and format equal PDF."""

        multiple_daily_report = MultipleDailyReport.objects.first()

        # Create DailyReportExport with is_compiled equal False
        daily_report_export = DailyReportExport.objects.create(
            created_by=self.user,
            is_compiled=False,
            format="PDF",
            done=False,
            error=False,
            sort="date",
            order="asc",
        )

        # Add ManyToMany relationships
        daily_report_export.multiple_daily_reports.add(multiple_daily_report)

        # Create fake file
        test_file = SimpleUploadedFile(
            "test.pdf", b"arquivo de teste 2", content_type="application/pdf"
        )

        # Create MultipleDailyReportFile
        MultipleDailyReportFile.objects.create(
            multiple_daily_report=multiple_daily_report,
            description="Arquivo de teste 2",
            md5="abc123def456",
            upload=test_file,
            uploaded_at=timezone.now(),
            datetime=timezone.now(),
            created_by=self.user,
            kind="durante",
        )

        # Mock Image class from openpyxl to avoid PIL/Pillow font issues
        mock_image_instance = MagicMock()
        mock_image.return_value = mock_image_instance

        # Mock ImageFont from PIL to avoid _imagingft C module issues
        mock_font = MagicMock()
        mock_image_font.truetype.return_value = mock_font

        # Mock NamedTemporaryFile to avoid file system issues
        mock_temp_file_instance = MagicMock()
        mock_temp_file_instance.name = "/tmp/fake_temp_file"
        mock_temp_file_instance.read.return_value = b"fake file content"
        mock_temp_file.return_value.__enter__.return_value = mock_temp_file_instance

        # Mock the Gotenberg response for PDF conversion
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake pdf content"
        mock_requests_post.return_value = mock_response

        generate_exported_file(str(daily_report_export.uuid))

        # Refresh DailyReportExport
        daily_report_export.refresh_from_db()

        assert daily_report_export.done is True
        assert daily_report_export.error is False

    @patch("helpers.apps.daily_reports.NamedTemporaryFile")
    @patch("helpers.apps.daily_reports.Image")
    @patch("helpers.apps.daily_reports.requests.get")
    @patch(
        "helpers.apps.daily_reports.get_obj_from_path",
        side_effect=mock_get_obj_from_path,
    )
    def test_error_generate_exported_with_non_compiled_file_with_images(
        self, mock_get_obj_from_path, mock_response_get, mock_image, mock_temp_file
    ):
        """Test the generate_exported function of a DailyReportExport with complied equal False and mock images content"""

        multiple_daily_report = MultipleDailyReport.objects.first()

        # Create DailyReportExport with is_compiled equal False
        daily_report_export = DailyReportExport.objects.create(
            created_by=self.user,
            is_compiled=False,
            format="EXCEL",
            done=False,
            error=False,
            sort="date",
            order="asc",
        )

        # Add ManyToMany relationships
        daily_report_export.multiple_daily_reports.add(multiple_daily_report)

        # Create fake file
        test_file = SimpleUploadedFile(
            "test.pdf", b"arquivo de teste 2", content_type="application/pdf"
        )

        # Create MultipleDailyReportFile
        MultipleDailyReportFile.objects.create(
            multiple_daily_report=multiple_daily_report,
            description="Arquivo de teste 2",
            md5="abc123def456",
            upload=test_file,
            uploaded_at=timezone.now(),
            datetime=timezone.now(),
            created_by=self.user,
            kind="durante",
        )

        # Create binary image data and mock Image class
        binary_content = b"fake image data"

        # Create a mock for the Image class that won't try to open a real file
        mock_image_instance = MagicMock()
        mock_image.return_value = mock_image_instance

        # Create mock response with binary content
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = binary_content

        # Configure the mock_response_get to return our properly configured mock_response
        mock_response_get.return_value = mock_response

        generate_exported_file(str(daily_report_export.uuid))

        # Refresh DailyReportExport
        daily_report_export.refresh_from_db()

        assert daily_report_export.done is True
        assert daily_report_export.error is True

    @patch("helpers.apps.daily_reports.NamedTemporaryFile")
    @patch("helpers.apps.daily_reports.Image")
    @patch("helpers.apps.daily_reports.requests.get")
    @patch(
        "helpers.apps.daily_reports.get_obj_from_path",
        side_effect=mock_get_obj_from_path,
    )
    def test_error_generate_exported_with_non_compiled_pdf_file_with_images(
        self, mock_get_obj_from_path, mock_response_get, mock_image, mock_temp_file
    ):
        """Test the generate_exported function of a DailyReportExport with complied equal False and format equal PDF."""

        multiple_daily_report = MultipleDailyReport.objects.first()

        # Create DailyReportExport with is_compiled equal False
        daily_report_export = DailyReportExport.objects.create(
            created_by=self.user,
            is_compiled=False,
            format="PDF",
            done=False,
            error=False,
            sort="date",
            order="asc",
        )

        # Add ManyToMany relationships
        daily_report_export.multiple_daily_reports.add(multiple_daily_report)

        # Create fake file
        test_file = SimpleUploadedFile(
            "test.pdf", b"arquivo de teste 2", content_type="application/pdf"
        )

        # Create MultipleDailyReportFile
        MultipleDailyReportFile.objects.create(
            multiple_daily_report=multiple_daily_report,
            description="Arquivo de teste 2",
            md5="abc123def456",
            upload=test_file,
            uploaded_at=timezone.now(),
            datetime=timezone.now(),
            created_by=self.user,
            kind="durante",
        )

        # Create binary image data and mock Image class
        binary_content = b"fake image data"

        # Create a mock for the Image class that won't try to open a real file
        mock_image_instance = MagicMock()
        mock_image.return_value = mock_image_instance

        # Create mock response with binary content
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = binary_content

        # Configure the mock_response_get to return our properly configured mock_response
        mock_response_get.return_value = mock_response

        generate_exported_file(str(daily_report_export.uuid))

        # Refresh DailyReportExport
        daily_report_export.refresh_from_db()

        assert daily_report_export.done is True
        assert daily_report_export.error is True

    @pytest.fixture
    def default_hours(self):
        return {
            "morning_start": "07:00",
            "morning_end": "11:00",
            "afternoon_start": "12:00",
            "afternoon_end": "16:00",
            "night_start": "19:00",
            "night_end": "23:00",
        }

    def test_parse_extra_hours_dict_with_extra_hours_key(self, default_hours):
        """Test parsing dict with 'extraHours' key."""
        extra_hours = {
            "extraHours": [
                {
                    "morningStart": time(8, 0),
                    "morningEnd": time(12, 0),
                    "afternoonStart": "13:00",
                    "afternoonEnd": "17:00",
                }
            ]
        }

        result = parse_extra_hours_to_list(extra_hours, default_hours)

        assert len(result) == 1
        assert result[0]["morning_start"] == time(8, 0)
        assert result[0]["morning_end"] == time(12, 0)
        assert result[0]["afternoon_start"] == time(13, 0)
        assert result[0]["afternoon_end"] == time(17, 0)
        # Should use defaults for unspecified times
        assert result[0]["night_start"] == time(19, 0)
        assert result[0]["night_end"] == time(23, 0)

    def test_parse_numeric_keys_dict(self, default_hours):
        """Test parsing dict with numeric string keys."""
        extra_hours = {
            "0": {"morningStart": "08:00", "morningEnd": "12:00"},
            "1": {"morningStart": "09:00", "morningEnd": "13:00"},
        }

        result = parse_extra_hours_to_list(extra_hours, default_hours)

        assert len(result) == 2
        assert result[0]["morning_start"] == time(8, 0)
        assert result[1]["morning_start"] == time(9, 0)

    def test_parse_list_format(self, default_hours):
        """Test parsing list format."""
        extra_hours = [
            {"morningStart": "08:00", "morningEnd": "12:00"},
            {"morningStart": "09:00", "morningEnd": "13:00"},
        ]

        result = parse_extra_hours_to_list(extra_hours, default_hours)

        assert len(result) == 2
        assert result[0]["morning_start"] == time(8, 0)
        assert result[1]["morning_start"] == time(9, 0)

    def test_empty_or_none_inputs(self, default_hours):
        """Test handling of empty or None inputs."""
        assert parse_extra_hours_to_list(None, default_hours) == []
        assert parse_extra_hours_to_list({}, default_hours) == []
        assert parse_extra_hours_to_list([], default_hours) == []

    def test_invalid_time_values(self, default_hours):
        """Test handling of invalid time values."""
        extra_hours = [
            {
                "morningStart": "invalid",
                "morningEnd": "10:30",
                "afternoonStart": None,
                "afternoonEnd": "",
            }
        ]

        result = parse_extra_hours_to_list(extra_hours, default_hours)

        # Should use default for invalid time
        assert result[0]["morning_start"] == time(7, 0)
        assert result[0]["morning_end"] == time(10, 30)
        assert result[0]["afternoon_start"] == time(12, 0)
        assert result[0]["afternoon_end"] == time(16, 0)
