import pytest
from rest_framework import status

from apps.templates.models import ExportRequest
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestExportRequest(TestBase):
    model = "ExportRequest"

    def test_list_export_request(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_export_request_without_queryset(self, client):

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

    def test_list_export_request_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_export_request(self, client):

        export_request = ExportRequest.objects.create(
            company=self.company, created_by=self.user
        )

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(export_request.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_update_export_request(self, client):

        export_request = ExportRequest.objects.create(
            company=self.company, created_by=self.user
        )

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(export_request.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(export_request.pk),
                    "attributes": {"done": True},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_str_method_with_created_by(self, client):
        export_request = ExportRequest.objects.create(
            company=self.company, created_by=self.user
        )

        # __str__ method returns expected format with created_by
        expected_str = "{}: {} - {}".format(
            export_request.company.name,
            export_request.created_by.username,
            export_request.created_at.strftime("%d/%m/%Y, %H:%M:%S"),
        )
        assert str(export_request) == expected_str

    def test_str_method_without_created_by(self, client):
        export_request = ExportRequest.objects.create(
            company=self.company, created_by=None
        )

        # __str__ method returns expected format without created_by
        expected_str = "{}: {}".format(
            export_request.company.name,
            export_request.created_at.strftime("%d/%m/%Y, %H:%M:%S"),
        )
        assert str(export_request) == expected_str

    def test_get_company_id(self, client):
        export_request = ExportRequest.objects.create(
            company=self.company, created_by=self.user
        )

        # get_company_id property returns company_id
        assert export_request.get_company_id == export_request.company_id
        assert export_request.get_company_id == self.company.pk
