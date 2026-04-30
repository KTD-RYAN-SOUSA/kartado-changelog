import json

import pytest
from rest_framework import status

from apps.locations.models import City
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestCity(TestBase):
    model = "City"

    def test_list_city(self, client):

        response = client.get(
            path="/Location/{}/?page_size=1".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_city(self, client):

        city = City.objects.first()

        response = client.get(
            path="/Location/{}/{}/".format(self.model, str(city.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_city(self, client):

        response = client.post(
            path="/Location/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"ufCode": 1, "name": "Test"},
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = City.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_update_city(self, client):

        city = City.objects.first()

        response = client.patch(
            path="/Location/{}/{}/".format(self.model, str(city.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(city.pk),
                    "attributes": {"name": "test_update"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_city(self, client):

        city = City.objects.first()

        response = client.delete(
            path="/Location/{}/{}/".format(self.model, str(city.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT
