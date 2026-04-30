import json

import pytest
from rest_framework import status

from apps.locations.models import Location, River
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestRiver(TestBase):
    model = "River"

    def test_list_river(self, client):

        response = client.get(
            path="/Location/{}/?company={}&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_river_without_company(self, client):

        response = client.get(
            path="/Location/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_river(self, client):

        river = River.objects.filter(company=self.company).first()

        response = client.get(
            path="/Location/{}/{}/?company={}".format(
                self.model, str(river.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_river(self, client):

        location = Location.objects.filter(company=self.company).first()

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
                        "locations": {
                            "data": [{"type": "Location", "id": str(location.pk)}]
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = River.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_river_without_company_id(self, client):

        location = Location.objects.filter(company=self.company).first()

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
                        "locations": {
                            "data": [{"type": "Location", "id": str(location.pk)}]
                        },
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_river_without_permission(self, client):

        false_permission(self.user, self.company, self.model)

        location = Location.objects.filter(company=self.company).first()

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
                        "locations": {
                            "data": [{"type": "Location", "id": str(location.pk)}]
                        },
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_river(self, client):

        river = River.objects.filter(company=self.company).first()

        response = client.patch(
            path="/Location/{}/{}/?company={}".format(
                self.model, str(river.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(river.pk),
                    "attributes": {"name": "test_update"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_river(self, client):

        river = River.objects.filter(company=self.company).first()

        response = client.delete(
            path="/Location/{}/{}/?company={}".format(
                self.model, str(river.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT
