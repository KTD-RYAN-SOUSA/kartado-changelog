from datetime import datetime
from unittest.mock import Mock, PropertyMock, patch

import pytest
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.approval_flows.models import ApprovalFlow
from apps.companies.models import Company
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import Reporting, ReportingFile
from apps.reportings.views import ReportingFileView, ReportingView
from apps.users.models import User

pytestmark = pytest.mark.django_db


class ReportingViewTestCase(TestCase):
    @patch("apps.reportings.signals.auto_add_reporting_number")
    def setUp(self, mock_auto_add):
        mock_auto_add.return_value = None

        self.factory = APIRequestFactory()
        self.user = User.objects.create(username="testuser")

        self.company = Company.objects.create(
            name="Test Company",
            metadata={"RP_name_format": {"default": "RP-{sequential}"}},
        )

        self.occurrence_type = OccurrenceType.objects.create(
            name="Test Occurrence", form_fields={"fields": []}
        )

        self.reporting = Reporting.objects.create(
            company=self.company,
            km=10.0,
            direction="North",
            lane="Left",
            created_by=self.user,
            occurrence_type=self.occurrence_type,
            number="RP-001",
        )

        self.approval_flow = ApprovalFlow.objects.create(
            name="Test Flow", target_model="Reporting", company=self.company
        )

        # Create a ReportingFile for testing the check method
        self.reporting_file = ReportingFile.objects.create(
            reporting=self.reporting, kind="test_kind", description="Test file"
        )

        self.view = ReportingView.as_view(
            {"get": "get_hidden", "delete": "bulk", "post": "bulk"}
        )
        self.approval_view = ReportingView.as_view({"post": "approval"})
        self.bulk_approval_view = ReportingView.as_view({"post": "bulk_approval"})
        self.zip_pictures_view = ReportingView.as_view({"get": "zip_pictures"})
        self.check_view = ReportingFileView.as_view({"get": "check"})

        self.permission_patcher = patch("apps.reportings.views.ReportingPermissions")
        self.mock_permission = self.permission_patcher.start()
        self.mock_permission.return_value.has_permission.return_value = True
        self.mock_permission.return_value.has_object_permission.return_value = True

        self.file_permission_patcher = patch(
            "apps.reportings.views.ReportingFilePermissions"
        )
        self.mock_file_permission = self.file_permission_patcher.start()
        self.mock_file_permission.return_value.has_permission.return_value = True
        self.mock_file_permission.return_value.has_object_permission.return_value = True

    def tearDown(self):
        self.permission_patcher.stop()
        self.file_permission_patcher.stop()

    def test_get_hidden(self):
        """Test the get_hidden method with valid and invalid parameters"""
        request = self.factory.get("/api/reportings/Hidden/")
        force_authenticate(request, user=self.user)

        with patch.object(ReportingView, "get_queryset") as mock_get_queryset, patch(
            "apps.reportings.views.ReportingFilter"
        ) as mock_filter:

            mock_queryset = Mock()
            mock_get_queryset.return_value = mock_queryset
            mock_filter_instance = Mock()
            mock_filter.return_value = mock_filter_instance
            mock_filter_instance.is_valid.return_value = True
            mock_filter_instance.filter_queryset.return_value = mock_queryset
            mock_queryset.count.return_value = 5

            response = self.view(request)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("attributes", response.data)
            self.assertIn("count", response.data["attributes"])

    def test_check_endpoint_method_configuration(self):

        self.assertTrue(hasattr(ReportingFileView, "check"))

        check_method = getattr(ReportingFileView, "check")
        self.assertTrue(hasattr(check_method, "url_path"))
        self.assertEqual(check_method.url_path, "Check")

        self.assertIn("get", check_method.mapping)

        self.assertTrue(check_method.detail)

    def test_check_endpoint_file_exists_with_size(self):

        from helpers.files import check_endpoint

        mock_file_obj = Mock()
        mock_file_obj.uuid = "test-uuid-123"

        mock_upload = Mock()
        mock_upload.storage.exists.return_value = True
        mock_upload.size = 1024
        mock_upload.name = "test_file.jpg"
        mock_upload.storage.e_tag.return_value = '"abc123def456"'

        mock_file_obj.upload = mock_upload

        response = check_endpoint(mock_file_obj)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["type"], "FileCheck")
        self.assertEqual(response.data["attributes"]["exists"], True)
        self.assertEqual(response.data["attributes"]["size"], 1024)
        self.assertEqual(response.data["attributes"]["md5"], "abc123def456")
        self.assertEqual(response.data["attributes"]["uuid"], "test-uuid-123")
        self.assertEqual(response.data["attributes"]["deleted"], False)

    def test_check_endpoint_file_not_exists_gets_deleted(self):

        from helpers.files import check_endpoint

        mock_file_obj = Mock()
        mock_file_obj.uuid = "test-uuid-456"
        mock_file_obj.delete.return_value = (
            1,
            {"ReportingFile": 1},
        )

        mock_upload = Mock()
        mock_upload.storage.exists.return_value = False
        mock_upload.name = "missing_file.jpg"

        mock_file_obj.upload = mock_upload

        response = check_endpoint(mock_file_obj)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["type"], "FileCheck")
        self.assertEqual(response.data["attributes"]["exists"], False)
        self.assertEqual(response.data["attributes"]["size"], None)
        self.assertEqual(response.data["attributes"]["md5"], None)
        self.assertEqual(response.data["attributes"]["uuid"], "test-uuid-456")
        self.assertEqual(response.data["attributes"]["deleted"], True)

        mock_file_obj.delete.assert_called_once()

        expected_reason = "Auto-deleting file on /Check. Exists was False and size was None. E-Tag was None"
        self.assertEqual(mock_file_obj._change_reason, expected_reason)

    def test_check_endpoint_file_exists_but_no_size_gets_deleted(self):

        from helpers.files import check_endpoint

        mock_file_obj = Mock()
        mock_file_obj.uuid = "test-uuid-789"
        mock_file_obj.delete.return_value = (
            1,
            {"ReportingFile": 1},
        )

        mock_upload = Mock()
        mock_upload.storage.exists.return_value = True
        mock_upload.size = None
        mock_upload.name = "empty_file.jpg"
        mock_upload.storage.e_tag.return_value = '"def456ghi789"'

        mock_file_obj.upload = mock_upload

        response = check_endpoint(mock_file_obj)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["type"], "FileCheck")
        self.assertEqual(response.data["attributes"]["exists"], True)
        self.assertEqual(response.data["attributes"]["size"], None)
        self.assertEqual(response.data["attributes"]["md5"], "def456ghi789")
        self.assertEqual(response.data["attributes"]["uuid"], "test-uuid-789")
        self.assertEqual(response.data["attributes"]["deleted"], True)

        mock_file_obj.delete.assert_called_once()

        expected_reason = "Auto-deleting file on /Check. Exists was True and size was None. E-Tag was def456ghi789"
        self.assertEqual(mock_file_obj._change_reason, expected_reason)

    def test_check_endpoint_no_upload_field(self):
        from helpers.files import check_endpoint

        mock_file_obj = Mock()
        mock_file_obj.uuid = "test-uuid-000"
        del mock_file_obj.upload

        response = check_endpoint(mock_file_obj)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["type"], "FileCheck")
        self.assertEqual(response.data["attributes"]["exists"], False)
        self.assertEqual(response.data["attributes"]["size"], None)
        self.assertEqual(response.data["attributes"]["md5"], None)
        self.assertEqual(response.data["attributes"]["uuid"], "test-uuid-000")
        self.assertEqual(response.data["attributes"]["deleted"], False)

    def test_check_endpoint_exception_accessing_field(self):
        from helpers.files import check_endpoint

        mock_file_obj = Mock()
        mock_file_obj.uuid = "test-uuid-error"

        type(mock_file_obj).upload = PropertyMock(
            side_effect=Exception("Field access error")
        )

        response = check_endpoint(mock_file_obj)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["type"], "FileCheck")
        self.assertEqual(response.data["attributes"]["exists"], False)
        self.assertEqual(response.data["attributes"]["size"], None)
        self.assertEqual(response.data["attributes"]["md5"], None)
        self.assertEqual(response.data["attributes"]["uuid"], "test-uuid-error")
        self.assertEqual(response.data["attributes"]["deleted"], False)

    def test_check_endpoint_custom_field_name(self):
        from helpers.files import check_endpoint

        mock_file_obj = Mock()
        mock_file_obj.uuid = "test-uuid-custom"

        mock_custom_field = Mock()
        mock_custom_field.storage.exists.return_value = True
        mock_custom_field.size = 2048
        mock_custom_field.name = "custom_file.pdf"
        mock_custom_field.storage.e_tag.return_value = '"custom123hash456"'

        mock_file_obj.custom_upload = mock_custom_field

        response = check_endpoint(mock_file_obj, field_name="custom_upload")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["type"], "FileCheck")
        self.assertEqual(response.data["attributes"]["exists"], True)
        self.assertEqual(response.data["attributes"]["size"], 2048)
        self.assertEqual(response.data["attributes"]["md5"], "custom123hash456")
        self.assertEqual(response.data["attributes"]["uuid"], "test-uuid-custom")
        self.assertEqual(response.data["attributes"]["deleted"], False)

    def test_check_view_integration_file_exists(self):
        """Test the actual check view method integration - file exists"""
        request = self.factory.get(
            f"/api/reporting-files/{self.reporting_file.pk}/Check/"
        )
        force_authenticate(request, user=self.user)

        # Mock the upload field to simulate a file that exists
        mock_upload = Mock()
        mock_upload.storage.exists.return_value = True
        mock_upload.size = 2048
        mock_upload.name = "test_integration.jpg"
        mock_upload.storage.e_tag.return_value = '"integration123hash"'

        with patch.object(self.reporting_file, "upload", mock_upload), patch.object(
            ReportingFileView, "get_object", return_value=self.reporting_file
        ):

            response = self.check_view(request, pk=self.reporting_file.pk)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["type"], "FileCheck")
            self.assertEqual(response.data["attributes"]["exists"], True)
            self.assertEqual(response.data["attributes"]["size"], 2048)
            self.assertEqual(response.data["attributes"]["md5"], "integration123hash")
            self.assertEqual(
                response.data["attributes"]["uuid"], self.reporting_file.uuid
            )
            self.assertEqual(response.data["attributes"]["deleted"], False)

    def test_check_view_integration_file_not_exists_deletes(self):
        """Test the actual check view method integration - file doesn't exist, gets deleted (RED LINE)"""
        request = self.factory.get(
            f"/api/reporting-files/{self.reporting_file.pk}/Check/"
        )
        force_authenticate(request, user=self.user)

        # Mock the upload field to simulate a file that doesn't exist
        mock_upload = Mock()
        mock_upload.storage.exists.return_value = False
        mock_upload.name = "missing_integration.jpg"

        # Mock the reporting file's delete method
        original_delete = self.reporting_file.delete
        self.reporting_file.delete = Mock(return_value=(1, {"ReportingFile": 1}))

        with patch.object(self.reporting_file, "upload", mock_upload), patch.object(
            ReportingFileView, "get_object", return_value=self.reporting_file
        ):

            response = self.check_view(request, pk=self.reporting_file.pk)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["type"], "FileCheck")
            self.assertEqual(response.data["attributes"]["exists"], False)
            self.assertEqual(response.data["attributes"]["size"], None)
            self.assertEqual(response.data["attributes"]["md5"], None)
            self.assertEqual(
                response.data["attributes"]["uuid"], self.reporting_file.uuid
            )
            self.assertEqual(response.data["attributes"]["deleted"], True)

            # Verify the object was actually "deleted"
            self.reporting_file.delete.assert_called_once()

            # Verify the change reason was set
            expected_reason = "Auto-deleting file on /Check. Exists was False and size was None. E-Tag was None"
            self.assertEqual(self.reporting_file._change_reason, expected_reason)

        # Restore original delete method
        self.reporting_file.delete = original_delete

    def test_check_view_integration_file_exists_no_size_deletes(self):
        """Test the actual check view method integration - file exists but no size, gets deleted (RED LINE)"""
        request = self.factory.get(
            f"/api/reporting-files/{self.reporting_file.pk}/Check/"
        )
        force_authenticate(request, user=self.user)

        # Mock the upload field to simulate a file that exists but has no size
        mock_upload = Mock()
        mock_upload.storage.exists.return_value = True
        mock_upload.size = None  # No size!
        mock_upload.name = "no_size_integration.jpg"
        mock_upload.storage.e_tag.return_value = '"nosize123hash"'

        # Mock the reporting file's delete method
        original_delete = self.reporting_file.delete
        self.reporting_file.delete = Mock(return_value=(1, {"ReportingFile": 1}))

        with patch.object(self.reporting_file, "upload", mock_upload), patch.object(
            ReportingFileView, "get_object", return_value=self.reporting_file
        ):

            response = self.check_view(request, pk=self.reporting_file.pk)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["type"], "FileCheck")
            self.assertEqual(response.data["attributes"]["exists"], True)
            self.assertEqual(response.data["attributes"]["size"], None)
            self.assertEqual(response.data["attributes"]["md5"], "nosize123hash")
            self.assertEqual(
                response.data["attributes"]["uuid"], self.reporting_file.uuid
            )
            self.assertEqual(response.data["attributes"]["deleted"], True)

            # Verify the object was actually "deleted"
            self.reporting_file.delete.assert_called_once()

            # Verify the change reason was set
            expected_reason = "Auto-deleting file on /Check. Exists was True and size was None. E-Tag was nosize123hash"
            self.assertEqual(self.reporting_file._change_reason, expected_reason)

        # Restore original delete method
        self.reporting_file.delete = original_delete


class TestZipPicturesView(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create(username="zipuser")
        self.company = Company.objects.create(name="Comp/Name", metadata={})
        self.occurrence_type = OccurrenceType.objects.create(
            name="Occ", form_fields={"fields": []}
        )
        self.reporting = Reporting.objects.create(
            company=self.company,
            km=10.0,
            created_by=self.user,
            occurrence_type=self.occurrence_type,
            number="RP-XYZ",
        )
        ReportingView.permission_classes = []
        self.view = ReportingView.as_view({"get": "zip_pictures"})

    def make_request(self, url: str):
        req = self.factory.get(url)
        force_authenticate(req, user=self.user)
        return req

    def test_invalid_strtobool_sets_false(self):
        request = self.make_request(
            "/api/reportings/ZipPicture/?use_file_location=notabool"
        )
        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings:

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_file_obj = Mock()
            mock_file_obj.upload = None
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                mock_file_obj
            ]
            mock_export.return_value.pk = "uuid123"
            mock_post.return_value.status_code = 200
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 200

    def test_no_reporting_files_raises_validation_error(self):
        request = self.make_request("/api/reportings/ZipPicture/")
        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files:
            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = (
                []
            )

            response = self.view(request)

            assert response.status_code == 400
            assert "kartado.error.reporting.no_files_in_zip_picture_export" in str(
                response.data
            )

    def test_invalid_watermark_field_raises_validation_error(self):
        request = self.make_request("/api/reportings/ZipPicture/?fields=invalidfield")
        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs:
            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting

            response = self.view(request)

            assert response.status_code == 400
            assert "Filtro não disponível" in str(response.data)

    def test_nomenclature_with_roads(self):
        company_with_roads = Company.objects.create(name="RoadCo", metadata={})
        self.reporting.company = company_with_roads
        self.reporting.save()

        request = self.make_request("/api/reportings/ZipPicture/")
        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings, patch.object(
            company_with_roads.company_roads, "exists", return_value=True
        ):

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_file_obj = Mock()
            mock_file_obj.upload = None
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                mock_file_obj
            ]
            mock_export.return_value.pk = "uuid123"
            mock_post.return_value.status_code = 200
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 200

    def test_reportingfile_processed_builds_json_and_truncate(self):
        request = self.make_request("/api/reportings/ZipPicture/?fields=notes")

        fake_upload = Mock()
        fake_upload.url = "https://bucket.s3.amazonaws.com/path/file.jpg?x=1"
        fake_upload.name = "file.jpg"

        long_name = "X" * 130
        fake_reporting = self.reporting
        fake_reporting.number = long_name

        file_obj = Mock()
        file_obj.upload = fake_upload
        file_obj.reporting = fake_reporting
        file_obj.kind = "kind"
        file_obj.km = 12.345
        file_obj.reporting.road_name = "MainRoad"
        file_obj.reporting.occurrence_type.name = "OT"
        file_obj.reporting.found_at = None
        file_obj.reporting.road = None
        file_obj.reporting.uuid = "test-uuid"

        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.check_image_file", return_value=True
        ), patch(
            "apps.reportings.views.build_text_dict", return_value={"note": "val"}
        ), patch(
            "apps.reportings.views.clean_latin_string", return_value="clean_value"
        ), patch(
            "apps.reportings.views.resolve_duplicate_name", return_value="final_name"
        ), patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings:

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                file_obj
            ]
            mock_export.return_value.pk = "uuid123"
            mock_post.return_value.status_code = 200
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 200

    def test_post_status_not_200_triggers_error_and_email(self):
        request = self.make_request("/api/reportings/ZipPicture/")
        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.send_email_export_request"
        ) as mock_email, patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings:

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_file_obj = Mock()
            mock_file_obj.upload = None
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                mock_file_obj
            ]
            fake_export = Mock()
            fake_export.error = False
            fake_export.save = Mock()
            mock_export.return_value = fake_export
            mock_post.return_value.status_code = 500
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 400
            assert fake_export.error is True
            fake_export.save.assert_called_once()
            mock_email.assert_called_once_with(fake_export)

    def test_valid_watermark_fields(self):
        request = self.make_request(
            "/api/reportings/ZipPicture/?fields=notes,date,number"
        )
        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings:

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_file_obj = Mock()
            mock_file_obj.upload = None
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                mock_file_obj
            ]
            mock_export.return_value.pk = "uuid123"
            mock_post.return_value.status_code = 200
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 200

    def test_custom_nomenclature(self):
        request = self.make_request(
            "/api/reportings/ZipPicture/?nomenclature=number,date,km"
        )
        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings:

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_file_obj = Mock()
            mock_file_obj.upload = None
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                mock_file_obj
            ]
            mock_export.return_value.pk = "uuid123"
            mock_post.return_value.status_code = 200
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 200

    def test_use_file_location_true(self):
        request = self.make_request(
            "/api/reportings/ZipPicture/?use_file_location=true"
        )

        fake_upload = Mock()
        fake_upload.url = "https://bucket.s3.amazonaws.com/path/file.jpg?x=1"
        fake_upload.name = "file.jpg"

        file_obj = Mock()
        file_obj.upload = fake_upload
        file_obj.reporting = self.reporting
        file_obj.kind = "kind"
        file_obj.km = 15.5
        file_obj.reporting.road_name = "MainRoad"
        file_obj.reporting.occurrence_type.name = "OT"
        file_obj.reporting.found_at = None
        file_obj.reporting.road = None
        file_obj.reporting.uuid = "test-uuid"

        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.check_image_file", return_value=True
        ), patch(
            "apps.reportings.views.clean_latin_string", return_value="clean_value"
        ), patch(
            "apps.reportings.views.resolve_duplicate_name", return_value="final_name"
        ), patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings:

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                file_obj
            ]
            mock_export.return_value.pk = "uuid123"
            mock_post.return_value.status_code = 200
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 200

    def test_no_image_files_filtered_out(self):
        request = self.make_request("/api/reportings/ZipPicture/")

        fake_upload = Mock()
        fake_upload.url = "https://bucket.s3.amazonaws.com/path/document.pdf?x=1"
        fake_upload.name = "document.pdf"

        file_obj = Mock()
        file_obj.upload = fake_upload
        file_obj.reporting = self.reporting

        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.check_image_file", return_value=False
        ), patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings:

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                file_obj
            ]
            mock_export.return_value.pk = "uuid123"
            mock_post.return_value.status_code = 200
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 200

    def test_font_size_parameter(self):
        request = self.make_request("/api/reportings/ZipPicture/?font_size=large")
        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings:

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_file_obj = Mock()
            mock_file_obj.upload = None
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                mock_file_obj
            ]
            mock_export.return_value.pk = "uuid123"
            mock_post.return_value.status_code = 200
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 200

    def test_nomenclature_with_road_auto_adds_km(self):
        company_with_roads = Company.objects.create(name="RoadCo", metadata={})
        self.reporting.company = company_with_roads
        self.reporting.save()

        request = self.make_request(
            "/api/reportings/ZipPicture/?nomenclature=road,number"
        )
        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings, patch.object(
            company_with_roads.company_roads, "exists", return_value=True
        ):

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_file_obj = Mock()
            mock_file_obj.upload = None
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                mock_file_obj
            ]
            mock_export.return_value.pk = "uuid123"
            mock_post.return_value.status_code = 200
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 200

    def test_nomenclature_removes_road_when_no_roads(self):
        request = self.make_request(
            "/api/reportings/ZipPicture/?nomenclature=road,number,km"
        )
        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings:

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_file_obj = Mock()
            mock_file_obj.upload = None
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                mock_file_obj
            ]
            mock_export.return_value.pk = "uuid123"
            mock_post.return_value.status_code = 200
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 200

    def test_file_with_road_object(self):

        request = self.make_request("/api/reportings/ZipPicture/")

        fake_upload = Mock()
        fake_upload.url = "https://bucket.s3.amazonaws.com/path/file.jpg?x=1"
        fake_upload.name = "file.jpg"

        mock_reporting = Mock()
        mock_reporting.road_name = "MainRoad"
        mock_reporting.occurrence_type.name = "OT"
        mock_reporting.found_at = None
        mock_reporting.uuid = "test-uuid"
        mock_reporting.number = "RP-XYZ"
        mock_reporting.km = 10.0
        mock_reporting.road = Mock()
        mock_reporting.road.name = "Highway 1"

        file_obj = Mock()
        file_obj.upload = fake_upload
        file_obj.reporting = mock_reporting
        file_obj.kind = "kind"
        file_obj.km = 12.345

        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.check_image_file", return_value=True
        ), patch(
            "apps.reportings.views.clean_latin_string", return_value="clean_value"
        ), patch(
            "apps.reportings.views.resolve_duplicate_name", return_value="final_name"
        ), patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings:

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                file_obj
            ]
            mock_export.return_value.pk = "uuid123"
            mock_post.return_value.status_code = 200
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 200

    def test_file_with_found_at_date(self):
        self.reporting.found_at = timezone.make_aware(datetime(2023, 5, 15, 14, 30))
        self.reporting.save()

        request = self.make_request(
            "/api/reportings/ZipPicture/?nomenclature=date,number"
        )

        fake_upload = Mock()
        fake_upload.url = "https://bucket.s3.amazonaws.com/path/file.jpg?x=1"
        fake_upload.name = "file.jpg"

        file_obj = Mock()
        file_obj.upload = fake_upload
        file_obj.reporting = self.reporting
        file_obj.kind = "kind"
        file_obj.km = 12.345
        file_obj.reporting.road_name = "MainRoad"
        file_obj.reporting.occurrence_type.name = "OT"
        file_obj.reporting.found_at = timezone.make_aware(datetime(2023, 5, 15, 14, 30))
        file_obj.reporting.road = None
        file_obj.reporting.uuid = "test-uuid"

        with patch.object(ReportingView, "get_queryset") as mock_qs, patch.object(
            ReportingView, "filter_queryset"
        ) as mock_filter_qs, patch(
            "apps.reportings.views.ReportingFile.objects.filter"
        ) as mock_files, patch(
            "apps.reportings.views.ExportRequest.objects.create"
        ) as mock_export, patch(
            "apps.reportings.views.requests.post"
        ) as mock_post, patch(
            "apps.reportings.views.check_image_file", return_value=True
        ), patch(
            "apps.reportings.views.clean_latin_string", return_value="clean_value"
        ), patch(
            "apps.reportings.views.resolve_duplicate_name", return_value="final_name"
        ), patch(
            "apps.reportings.views.get_user_token"
        ) as mock_token, patch(
            "apps.reportings.views.settings"
        ) as mock_settings:

            mock_qs.return_value.first.return_value = self.reporting
            mock_filter_qs.return_value.first.return_value = self.reporting
            mock_files.return_value.prefetch_related.return_value.distinct.return_value = [
                file_obj
            ]
            mock_export.return_value.pk = "uuid123"
            mock_post.return_value.status_code = 200
            mock_token.return_value = "fake_token"
            mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
            mock_settings.BACKEND_URL = "http://backend.com"

            response = self.view(request)
            assert response.status_code == 200
