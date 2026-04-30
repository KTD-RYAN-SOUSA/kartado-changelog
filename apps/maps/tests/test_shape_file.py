import json

import pytest
from rest_framework import status

from apps.maps.models import ShapeFile
from apps.maps.tests.acate_feature_collection import acate_feature_collection
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestShapeFile(TestBase):
    model = "ShapeFile"

    # Make sure we can't create a ShapeFile if we don't specify a company
    def test_create_shape_file_without_company(self, client):
        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "ACATE",
                        "description": "ACATE",
                        "featureCollection": acate_feature_collection,
                    },
                }
            },
        )

        content = json.loads(response.content)
        assert "errors" in content
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # Make sure we can create a ShapeFile if we specify all the required fields
    def test_create_shape_file_with_company(self, client):
        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "ACATE",
                        "description": "ACATE",
                        "featureCollection": acate_feature_collection,
                    },
                    "relationships": {
                        "companies": {
                            "data": [
                                {
                                    "id": "daac1370-ee61-45ce-ad13-63aa131bf4e6",
                                    "type": "Company",
                                }
                            ]
                        }
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = ShapeFile.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    # Make sure we can list ShapeFile objects
    def test_list_shape_file(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    # Make sure we can get a single ShapeFile objects
    def test_get_shape_file(self, client):
        obj = ShapeFile.objects.filter(companies=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    # Make sure we can get a single ShapeFile objects using the GZIP endpoint
    def test_get_shape_file_gzip(self, client):
        obj = ShapeFile.objects.filter(companies=self.company).first()

        response = client.get(
            path="/{}/{}/GZIP/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/octet-stream",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["Content-Type"] == "application/gzip"

    # Make sure we can update attributes of a ShapeFile object
    def test_update_shape_file(self, client):
        shape_file = ShapeFile.objects.filter(companies=self.company).first()
        new_name = "Florianópolis"

        response = client.patch(
            path="/{}/{}/".format(self.model, str(shape_file.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(shape_file.pk),
                    "attributes": {"description": new_name, "name": new_name},
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)
        updated_attributes = content["data"]["attributes"]
        assert updated_attributes["name"] == new_name
        assert updated_attributes["description"] == new_name

    # Make sure we can list ShapeFileProperty objects
    def test_list_shape_file_property(self, client):
        response = client.get(
            path="/{}Property/?company={}&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_filter_object_id_shape_file_property(self, client):
        shape_file = ShapeFile.objects.filter(companies=self.company).first()

        find_id = f"{shape_file.pk}-{shape_file.properties[0]['OBJECTID']}"

        response = client.get(
            path="/{}Property/?company={}&id={}&page_size=1".format(
                self.model, str(self.company.pk), find_id
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data[0]["id"] == find_id

    def test_filter_shape_file_name(self, client):

        response = client.get(
            path="/{}/?company={}&name__icontains=teste".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)

        # name filter works, object doesn't exist
        assert content["meta"]["pagination"]["count"] == 0
