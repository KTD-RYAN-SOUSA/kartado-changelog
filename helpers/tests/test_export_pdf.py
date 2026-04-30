from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

pytestmark = pytest.mark.django_db


class TestRenderTemplateAsPdf(TestCase):
    """Tests for render_template_as_pdf function"""

    @patch("helpers.export_pdf.tempfile.NamedTemporaryFile")
    def test_render_template_as_pdf_without_upload(self, mock_temp_file):
        """Test rendering PDF without uploading to S3"""
        from helpers.export_pdf import render_template_as_pdf

        mock_file = Mock()
        mock_file.name = "/tmp/test.pdf"
        mock_temp_file.return_value = mock_file

        mock_pdf = Mock()

        result = render_template_as_pdf(
            pdf=mock_pdf, upload_pdf_to_s3=False, bucket_name=None
        )

        mock_temp_file.assert_called_once_with(delete=False, suffix=".pdf")

        mock_pdf.build_pdf.assert_called_once_with("/tmp/test.pdf")

        assert result == "/tmp/test.pdf"

    @patch("helpers.export_pdf.upload_to_s3")
    @patch("helpers.export_pdf.tempfile.NamedTemporaryFile")
    def test_render_template_as_pdf_with_upload(
        self, mock_temp_file, mock_upload_to_s3
    ):
        """Test rendering PDF and uploading to S3"""
        from helpers.export_pdf import render_template_as_pdf

        mock_file = Mock()
        mock_file.name = "/tmp/test.pdf"
        mock_temp_file.return_value = mock_file

        mock_upload_to_s3.return_value = "https://s3.amazonaws.com/bucket/test.pdf"

        mock_pdf = Mock()

        result = render_template_as_pdf(
            pdf=mock_pdf, upload_pdf_to_s3=True, bucket_name="my-bucket"
        )

        mock_temp_file.assert_called_once_with(delete=False, suffix=".pdf")

        mock_pdf.build_pdf.assert_called_once_with("/tmp/test.pdf")

        mock_upload_to_s3.assert_called_once_with("/tmp/test.pdf", "my-bucket")

        assert result == "https://s3.amazonaws.com/bucket/test.pdf"

    @patch("helpers.export_pdf.tempfile.NamedTemporaryFile")
    def test_render_template_as_pdf_missing_bucket_name(self, mock_temp_file):
        """Test that ValueError is raised when upload=True but no bucket name"""
        from helpers.export_pdf import render_template_as_pdf

        mock_pdf = Mock()

        with self.assertRaises(ValueError) as context:
            render_template_as_pdf(
                pdf=mock_pdf, upload_pdf_to_s3=True, bucket_name=None
            )

        assert (
            "Please provide a bucket name if the PDF is going to be uploaded to S3"
            in str(context.exception)
        )

    @patch("helpers.export_pdf.tempfile.NamedTemporaryFile")
    def test_render_template_as_pdf_missing_bucket_with_empty_string(
        self, mock_temp_file
    ):
        """Test that ValueError is raised with empty bucket name"""
        from helpers.export_pdf import render_template_as_pdf

        mock_pdf = Mock()

        with self.assertRaises(ValueError) as context:
            render_template_as_pdf(pdf=mock_pdf, upload_pdf_to_s3=True, bucket_name="")

        assert "Please provide a bucket name" in str(context.exception)

    @patch("helpers.export_pdf.upload_to_s3")
    @patch("helpers.export_pdf.tempfile.NamedTemporaryFile")
    def test_render_template_as_pdf_calls_build_pdf(
        self, mock_temp_file, mock_upload_to_s3
    ):
        """Test that build_pdf is called with correct path"""
        from helpers.export_pdf import render_template_as_pdf

        mock_file = Mock()
        mock_file.name = "/custom/path/file.pdf"
        mock_temp_file.return_value = mock_file

        mock_pdf = Mock()

        render_template_as_pdf(pdf=mock_pdf, upload_pdf_to_s3=False, bucket_name=None)

        mock_pdf.build_pdf.assert_called_once_with("/custom/path/file.pdf")

    @patch("helpers.export_pdf.upload_to_s3")
    @patch("helpers.export_pdf.tempfile.NamedTemporaryFile")
    def test_render_template_as_pdf_default_upload_parameter(
        self, mock_temp_file, mock_upload_to_s3
    ):
        """Test default value of upload_pdf_to_s3 parameter"""
        from helpers.export_pdf import render_template_as_pdf

        mock_file = Mock()
        mock_file.name = "/tmp/test.pdf"
        mock_temp_file.return_value = mock_file

        mock_upload_to_s3.return_value = "https://s3.amazonaws.com/bucket/test.pdf"

        mock_pdf = Mock()

        result = render_template_as_pdf(pdf=mock_pdf, bucket_name="my-bucket")

        mock_upload_to_s3.assert_called_once_with("/tmp/test.pdf", "my-bucket")
        assert result == "https://s3.amazonaws.com/bucket/test.pdf"

    @patch("helpers.export_pdf.upload_to_s3")
    @patch("helpers.export_pdf.tempfile.NamedTemporaryFile")
    def test_render_template_as_pdf_with_different_bucket_names(
        self, mock_temp_file, mock_upload_to_s3
    ):
        """Test with different bucket names"""
        from helpers.export_pdf import render_template_as_pdf

        mock_file = Mock()
        mock_file.name = "/tmp/test.pdf"
        mock_temp_file.return_value = mock_file

        mock_pdf = Mock()

        buckets = ["bucket-1", "my-special-bucket", "prod-bucket"]

        for bucket in buckets:
            mock_upload_to_s3.reset_mock()
            mock_upload_to_s3.return_value = (
                f"https://s3.amazonaws.com/{bucket}/test.pdf"
            )

            result = render_template_as_pdf(
                pdf=mock_pdf, upload_pdf_to_s3=True, bucket_name=bucket
            )

            mock_upload_to_s3.assert_called_once_with("/tmp/test.pdf", bucket)
            assert bucket in result
