import json

import pytest
from rest_framework import status

from apps.services.models import Service
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestService(TestBase):
    model = "Service"

    def test_list_service(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_service_without_queryset(self, client):

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

    def test_list_service_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_service(self, client):

        service = Service.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(service.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_service_without_initial_price(self, client):

        service = Service.objects.filter(company=self.company).first()
        service.initial_price = None
        service.save()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(service.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_service_without_company(self, client):

        service = Service.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(service.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_service(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "unit_price": 1.0,
                        "total_amount": 1.0,
                        "current_balance": 1.0,
                        "adjustment_coefficient": 1.0,
                        "unit": "m",
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = Service.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_update_service(self, client):

        service = Service.objects.filter(company=self.company).first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(service.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(service.pk),
                    "attributes": {"unit_price": 5.0},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_service_total_amount(self, client):

        service = Service.objects.filter(company=self.company).first()
        value = -(service.current_balance + service.total_amount + 1)

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(service.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(service.pk),
                    "attributes": {"total_amount": value},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_service_usage(self, client):

        service = Service.objects.filter(company=self.company).first()

        response = client.delete(
            path="/{}/{}/".format(self.model, str(service.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT
