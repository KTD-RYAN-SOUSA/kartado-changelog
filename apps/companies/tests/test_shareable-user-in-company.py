import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestShareableUserInCompany(TestBase):
    model = "ShareableUserInCompany"

    def test_list_shareable_userincompany(self, client):
        response = client.get(
            path=f"/{self.model}/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert "data" in response.json()

    def test_filter_shareable_userincompany_by_company(self, client):
        response = client.get(
            path=f"/{self.model}/?company={self.company.pk}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        for item in response.json().get("data", []):
            company_id = item["relationships"]["company"]["data"]["id"]
            assert company_id == str(self.company.pk)

    def test_shareable_userincompany_ordering_by_uuid(self, client):
        response = client.get(
            path=f"/{self.model}/?company={self.company.pk}&ordering=uuid",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.json().get("data", [])

        uuids = [item["attributes"]["uuid"] for item in results]
        assert uuids == sorted(uuids)

    def test_shareable_userincompany_unauthenticated(self, client):
        response = client.get(
            path=f"/{self.model}/",
            content_type="application/vnd.api+json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_shareable_userincompany_fields(self, client):
        response = client.get(
            path=f"/{self.model}/?company={self.company.pk}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        data = response.json().get("data", [])
        if data:
            attributes = data[0].get("attributes", {})
            for field in ["uuid", "expirationDate", "isActive"]:
                assert field in attributes
