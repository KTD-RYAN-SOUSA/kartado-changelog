import json
from unittest.mock import Mock, patch

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase

from ..models import MultipleDailyReport, MultipleDailyReportFile
from ..permissions import MultipleDailyReportFilePermissions

pytestmark = pytest.mark.django_db


class TestDailyReport(TestBase):
    model = "MultipleDailyReportFile"

    def test_multiple_daily_report_file_list(self, client):
        """
        Ensures we can list using the MultipleDailyReport endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 2

    def test_multiple_daily_report_file_without_company(self, client):
        """
        Ensures calling the MultipleDailyReportFile endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_multiple_daily_report_file(self, client):
        """
        Ensures a specific multiple daily report can be fetched using the uuid
        """

        report = MultipleDailyReportFile.objects.filter(
            multiple_daily_report__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(report.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK

    def test_create_multiple_daily_report_file(self, client):
        """
        Ensures a new multiple daily report can be created using the endpoint
        """

        rdo = MultipleDailyReport.objects.filter(
            company=self.company, editable=True
        ).first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "description": "teste",
                        "md5": "",
                        "upload": {
                            "filename": "e8c01a27-ef71-4260-9fed-3356d9ff0f96.jpg"
                        },
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "multipleDailyReport": {
                            "data": {
                                "type": "MultipleDailyReport",
                                "id": str(rdo.pk),
                            }
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = MultipleDailyReportFile.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()
        assert obj_created.legacy_uuid is None
        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_multiple_daily_report_file_with_blank_legacy_uuid(self, client):
        """
        Ensures a new multiple daily report can be created using the endpoint
        """

        rdo = MultipleDailyReport.objects.filter(
            company=self.company, editable=True
        ).first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "description": "teste",
                        "md5": "",
                        "upload": {
                            "filename": "e8c01a27-ef71-4260-9fed-3356d9ff0f96.jpg"
                        },
                        "legacy_uuid": "",
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "multipleDailyReport": {
                            "data": {
                                "type": "MultipleDailyReport",
                                "id": str(rdo.pk),
                            }
                        },
                    },
                }
            },
        )

        content = json.loads(response.content)
        assert content["data"]["attributes"]["legacyUuid"] == ""
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_multiple_daily_report_file_without_rdo(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "description": "teste",
                        "md5": "",
                        "upload": {
                            "filename": "f327e8a7-6e04-4909-be66-6866ed20abc0.jpg"
                        },
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_multiple_daily_report_file_rdo_filter(self, client):

        rdo = MultipleDailyReport.objects.filter(
            company=self.company, editable=True
        ).first()

        response = client.get(
            path="/{}/?company={}&multiple_daily_report={}".format(
                self.model, str(self.company.pk), str(rdo.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 2

    def test_multiple_daily_report_file_file_type_filter(self, client):

        response = client.get(
            path="/{}/?company={}&file_type=image".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 2

    def test_multiple_daily_report_file_jobs_rdos_user_firms_filter(self, client):

        response = client.get(
            path="/{}/?company={}&jobs_rdos_user_firms=7".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 2

    def test_check_method(self, client):
        """
        Ensures the check method can be accessed and returns file validation data
        """

        report_file = MultipleDailyReportFile.objects.filter(
            multiple_daily_report__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/Check/?company={}".format(
                self.model, str(report_file.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

    def test_multiple_daily_report_file_legacy_uuid_filter(self, client):
        report_file = MultipleDailyReportFile.objects.filter(
            multiple_daily_report__company=self.company
        ).first()
        report_file.legacy_uuid = "a-legacy-uuid"
        report_file.save()

        response = client.get(
            path="/{}/?company={}&legacy_uuid={}".format(
                self.model, str(self.company.pk), report_file.legacy_uuid
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 1
        assert content["data"][0]["id"] == str(report_file.pk)

    @patch("apps.daily_reports.permissions.PermissionManager")
    def test_has_object_permission_when_action_is_check(self, mock_permission_manager):
        permissions = MultipleDailyReportFilePermissions()

        mock_request = Mock()
        mock_request.user = self.user
        mock_request.query_params = {"company": str(self.company.pk)}

        mock_view = Mock()
        mock_view.action = "check"
        mock_view.permissions = None

        mock_obj = Mock()
        mock_obj.multiple_daily_report.company_id = self.company.pk

        mock_manager = Mock()
        mock_permission_manager.return_value = mock_manager
        mock_manager.has_permission.return_value = True

        result = permissions.has_object_permission(mock_request, mock_view, mock_obj)

        assert mock_view.action == "retrieve"
        assert result is True
