import json

import pytest
from rest_framework import status

from apps.locations.models import City, Location
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestLocation(TestBase):
    model = "Location"

    def test_list_location(self, client):

        response = client.get(
            path="/Location/{}/?company={}&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_location_without_company(self, client):

        response = client.get(
            path="/Location/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_location(self, client):

        location = Location.objects.filter(company=self.company).first()

        response = client.get(
            path="/Location/{}/{}/?company={}".format(
                self.model, str(location.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_location(self, client):

        city = City.objects.first()

        response = client.post(
            path="/Location/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test"},
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "city": {"data": {"type": "City", "id": str(city.pk)}},
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = Location.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_location_without_company_id(self, client):

        city = City.objects.first()

        response = client.post(
            path="/Location/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test"},
                    "relationships": {
                        "company": {"data": {"type": "Company"}},
                        "city": {"data": {"type": "City", "id": str(city.pk)}},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_location_without_permission(self, client):

        false_permission(self.user, self.company, self.model)

        city = City.objects.first()

        response = client.post(
            path="/Location/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test"},
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "city": {"data": {"type": "City", "id": str(city.pk)}},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_location(self, client):

        location = Location.objects.filter(company=self.company).first()

        response = client.patch(
            path="/Location/{}/{}/?company={}".format(
                self.model, str(location.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(location.pk),
                    "attributes": {"name": "test_update"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_location(self, client):

        location = Location.objects.filter(company=self.company).first()

        response = client.delete(
            path="/Location/{}/{}/?company={}".format(
                self.model, str(location.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT
