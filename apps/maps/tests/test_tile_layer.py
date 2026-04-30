import json

import pytest
from rest_framework import status

from apps.maps.models import TileLayer
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestTileLayer(TestBase):
    model = "TileLayer"

    # Make sure we can't create a TileLayer if we don't specify a company
    def test_create_tile_layer_without_company(self, client):

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "type": "mapbox",
                        "name": "Mapa Claro",
                        "description": "Mapa Claro",
                        "providerInfo": {
                            "url": "https://api.mapbox.com/styles/v1/natank/cjmmhqxpt0jsn2smsihy5nx5w/tiles/{z}/{x}/{y}.mapbox",
                            "type": "mapbox",
                            "order": 4,
                            "accessToken": "MAPBOX_TEST_TOKEN",
                            "attribution": 'Licensed by &copy; <a href="https://www.mapbox.com/">Mapbox</a>',
                            "styleString": "mapbox://styles/natank/ck0z9bp0r0z4l1cqhp4wt15ew",
                        },
                    },
                }
            },
        )

        content = json.loads(response.content)
        assert "errors" in content
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # Make sure we can create a TileLayer if we specify all the required fields
    def test_create_tile_layer_with_company(self, client):

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "type": "mapbox",
                        "name": "Mapa Claro",
                        "description": "Mapa Claro",
                        "providerInfo": {
                            "url": "https://api.mapbox.com/styles/v1/natank/cjmmhqxpt0jsn2smsihy5nx5w/tiles/{z}/{x}/{y}.mapbox",
                            "type": "mapbox",
                            "order": 4,
                            "accessToken": "MAPBOX_TEST_TOKEN",
                            "attribution": 'Licensed by &copy; <a href="https://www.mapbox.com/">Mapbox</a>',
                            "styleString": "mapbox://styles/natank/ck0z9bp0r0z4l1cqhp4wt15ew",
                        },
                    },
                    "relationships": {
                        "companies": {
                            "data": [{"id": self.company.pk, "type": "Company"}]
                        }
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = TileLayer.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    # Make sure we can list TileLayer objects
    def test_list_tile_layer(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    # Make sure we can get a single TileLayer objects
    def test_get_tile_layer(self, client):

        obj = TileLayer.objects.filter(companies=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    # Make sure we can update attributes of a TileLayer object
    def test_update_tile_layer(self, client):

        tile_layer = TileLayer.objects.filter(companies=self.company).first()
        new_name = "Mapa Escuro"

        response = client.patch(
            path="/{}/{}/".format(self.model, str(tile_layer.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(tile_layer.pk),
                    "attributes": {"description": new_name, "name": new_name},
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)
        updated_attributes = content["data"]["attributes"]
        assert updated_attributes["name"] == new_name
        assert updated_attributes["description"] == new_name
