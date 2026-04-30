import json
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status

from apps.reportings.models import Reporting, ReportingFile
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestReportingFile(TestBase):
    model = "ReportingFile"

    @pytest.fixture(autouse=True)
    def setup_reporting(self):

        reporting_base = Reporting.objects.filter(company=self.company)[0]

        self.reporting = Reporting.objects.create(
            company=self.company,
            occurrence_type=reporting_base.occurrence_type,
            km=reporting_base.km,
            status=reporting_base.status,
            number="test",
        )
        return self.reporting

    def test_list_reporting_file(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_filter_reporting_file(self, client):

        response = client.get(
            path="/{}/?company={}&file_type={}&page_size=1".format(
                self.model, str(self.company.pk), "image"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.get(
            path="/{}/?company={}&file_type={}&page_size=1".format(
                self.model, str(self.company.pk), "file"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_reporting_file_without_queryset(self, client):

        false_permission(self.user, self.company, self.model, allowed="none")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        false_permission(self.user, self.company, self.model, allowed="self")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_reporting_file_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_reporting_file(self, client):

        obj = ReportingFile.objects.filter(reporting__company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_reporting_file_without_company_uuid(self, client):

        obj = ReportingFile.objects.filter(reporting__company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, str(obj.pk), "test"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_reporting_file(self, client):

        reporting = Reporting.objects.filter(company=self.company).first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"upload": {"filename": "file_name.extension"}},
                    "relationships": {
                        "reporting": {
                            "data": {
                                "type": "Reporting",
                                "id": str(reporting.pk),
                            }
                        }
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # __str__ method
        content = json.loads(response.content)
        obj_created = ReportingFile.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

    def test_create_reporting_file_without_permission(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"upload": {"filename": "file_name.extension"}},
                    "relationships": {
                        "reporting": {"data": {"type": "Reporting", "id": "test"}}
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_reporting_file(self, client):

        obj = ReportingFile.objects.filter(reporting__company=self.company).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"include_rdo": True},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_bulk_reporting_file(self, client):

        obj = ReportingFile.objects.filter(reporting__company=self.company).first()

        response = client.post(
            path="/{}/{}/".format(self.model, "Bulk"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "includeDnit": False,
                        "includeRdo": True,
                        "isShared": True,
                    },
                    "relationships": {
                        "reporting_files": {
                            "data": [{"type": self.model, "id": str(obj.pk)}]
                        }
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

        response = client.post(
            path="/{}/{}/".format(self.model, "Bulk"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "includeDnit": False,
                        "includeRdo": True,
                        "isShared": True,
                    },
                    "relationships": {"reporting_files": {"data": [{}]}},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = client.post(
            path="/{}/{}/".format(self.model, "Bulk"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "includeDnit": False,
                        "includeRdo": True,
                        "includeTest": False,
                    },
                    "relationships": {
                        "reporting_files": {
                            "data": [{"type": self.model, "id": str(obj.pk)}]
                        }
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_shared_with_agency_is_handled_in_endpoint(self, client):
        """
        Ensure shared_with_agency is handled in the endpoint
        """

        reporting_file = ReportingFile.objects.filter(
            reporting__company=self.company, is_shared=True
        ).first()

        response = client.get(
            path="/ReportingFile/{}/?company={}".format(
                str(reporting_file.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["data"]["attributes"]["sharedWithAgency"]

        response = client.get(
            path="/ReportingFile/?company={}&shared_with_agency=true".format(
                str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_antt_supervisor_agency_qs_permissions(self, client):
        """
        Ensure antt_supervisor_agency queryset permission properly limits the results
        """

        false_permission(
            self.user, self.company, self.model, allowed="antt_supervisor_agency"
        )

        response = client.get(
            path="/ReportingFile/?company={}".format(str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_is_shared_with_agency_endpoint(self, client):
        """
        Ensure the IsSharedWithAgency endpoint is working correctly
        """

        reporting_file = ReportingFile.objects.filter(
            reporting__company=self.company, is_shared=True
        ).first()

        response = client.get(
            path="/ReportingFile/{}/IsSharedWithAgency/?company={}".format(
                str(reporting_file.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["data"]["isSharedWithAgency"]

    @patch("boto3.client")
    def test_redirect_to_s3(self, mock_boto3_client, client):

        # Create test file
        reporting_file = ReportingFile.objects.create(
            upload="test/path/file.jpg", reporting=self.reporting
        )

        # Mock S3 client and presigned URL
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://test-presigned-url.com"
        mock_boto3_client.return_value = mock_s3

        # Make request
        response = client.get(
            path="/ReportingFile/{}/RedirectToS3/?company={}".format(
                str(reporting_file.uuid), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        # Verify response
        assert response.status_code == status.HTTP_302_FOUND
        assert response["Location"] == "https://test-presigned-url.com"

    @patch("boto3.client")
    def test_redirect_to_s3_no_file(self, mock_boto3_client, client):

        # Create test file without upload
        reporting_file = ReportingFile.objects.create(reporting=self.reporting)

        # Make request
        response = client.get(
            path="/ReportingFile/{}/RedirectToS3/?company={}".format(
                str(reporting_file.uuid), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        # Verify error response
        content = json.loads(response.content)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            content["errors"][0]["detail"]
            == "kartado.error.reporting_file.no_file_upload_found"
        )

        # Verify S3 client was not called
        mock_boto3_client.assert_not_called()

    def test_get_company_id_property(self):
        """
        Test the get_company_id property of ReportingFile
        """
        # Create a reporting file
        reporting_file = ReportingFile.objects.filter(
            reporting__company=self.company
        ).first()

        # Test that get_company_id returns the correct company_id
        assert reporting_file.get_company_id == self.company.pk
        assert reporting_file.get_company_id == reporting_file.reporting.company_id

    @patch("boto3.client")
    def test_redirect_to_s3_s3_error(self, mock_boto3_client, client):

        # Create test file
        reporting_file = ReportingFile.objects.create(
            upload="test/path/file.jpg", reporting=self.reporting
        )

        # Mock S3 client to raise exception
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.side_effect = Exception("S3 Error")
        mock_boto3_client.return_value = mock_s3

        # Make request
        response = client.get(
            path="/ReportingFile/{}/RedirectToS3/?company={}".format(
                str(reporting_file.uuid), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        # Verify error response
        content = json.loads(response.content)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            content["errors"][0]["detail"]
            == "kartado.error.reporting_file.redirect_failed"
        )

    @patch("boto3.client")
    def test_redirect_to_s3_file_not_found(self, mock_boto3_client, client):

        # Create test file
        reporting_file = ReportingFile.objects.create(
            upload="test/path/file.jpg", reporting=self.reporting
        )

        # Mock S3 client to raise FileNotFoundError
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.side_effect = FileNotFoundError()
        mock_boto3_client.return_value = mock_s3

        # Make request
        response = client.get(
            path="/ReportingFile/{}/RedirectToS3/?company={}".format(
                str(reporting_file.uuid), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        # Verify error response
        content = json.loads(response.content)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            content["errors"][0]["detail"]
            == "kartado.error.reporting_file.s3_access_error"
        )
