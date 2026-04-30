import json

import pytest
from django.contrib.admin.sites import AdminSite
from rest_framework import status

from apps.roads.admin import RoadAdmin
from apps.roads.models import Road
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestRoad(TestBase):
    model = "Road"

    def test_list_road(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_road_without_queryset(self, client):

        false_permission(self.user, self.company, self.model, allowed="none")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_road_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_road(self, client):

        road = Road.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(road.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_road(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test_road",
                        "direction": 1,
                        "marks": {},
                    },
                    "relationships": {
                        "company": {
                            "data": [{"type": "Company", "id": str(self.company.pk)}]
                        }
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = Road.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_road_without_company_id(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test_road",
                        "direction": 1,
                        "marks": {},
                    },
                    "relationships": {"company": {"data": [{"type": "Company"}]}},
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_road_without_permission(self, client):

        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test_road",
                        "direction": 1,
                        "marks": {},
                    },
                    "relationships": {
                        "company": {
                            "data": [{"type": "Company", "id": str(self.company.pk)}]
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_road(self, client):

        road = Road.objects.filter(company=self.company).first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(road.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(road.pk),
                    "attributes": {"name": "test_update"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_road(self, client):

        road = Road.objects.filter(company=self.company).first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(road.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_admin_road(self, client):

        road = Road.objects.filter(company=self.company).first()
        site = AdminSite()
        road_admin = RoadAdmin(model=Road, admin_site=site)
        road_admin_str = [road_admin.companies_names(road)]
        str_admin = [comp.name for comp in road.company.all()]

        assert road_admin_str == str_admin

    def test_road_id_filter(self, client):

        response = client.get(
            path="/{}/?company={}&id=1,3&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 2
