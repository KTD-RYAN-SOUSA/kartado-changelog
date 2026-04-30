import json

import pytest
from rest_framework import status

from apps.reportings.models import Reporting
from apps.services.models import Service, ServiceUsage
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestServiceUsage(TestBase):
    model = "ServiceUsage"

    def test_list_service_usage(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_filter_service_usage(self, client):

        reporting = Reporting.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/?company={}&reporting_resource={}&page_size=1".format(
                self.model, str(self.company.pk), str(reporting.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.get(
            path="/{}/?company={}&reporting_resource={}&page_size=1".format(
                self.model, str(self.company.pk), "not_uuid"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_service_usage_without_queryset(self, client):

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

    def test_list_service_usage_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_service_usage(self, client):

        usage = ServiceUsage.objects.filter(service__company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(usage.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_service_usage_without_company(self, client):

        usage = ServiceUsage.objects.filter(service__company=self.company).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(usage.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_service_usage(self, client):

        reporting = Reporting.objects.filter(company=self.company).first()
        service = Service.objects.filter(company=self.company).first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "reporting": {
                            "data": {
                                "type": "Reporting",
                                "id": str(reporting.pk),
                            }
                        },
                        "service": {"data": {"type": "Service", "id": str(service.pk)}},
                    },
                }
            },
        )

        content = json.loads(response.content)
        obj_created = ServiceUsage.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        assert response.status_code == status.HTTP_201_CREATED

    def test_update_service_usage(self, client):

        usage = ServiceUsage.objects.filter(service__company=self.company).first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(usage.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(usage.pk),
                    "attributes": {"amount": 5.0},
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

    def test_delete_service_usage(self, client):

        usage = ServiceUsage.objects.filter(service__company=self.company).first()

        response = client.delete(
            path="/{}/{}/".format(self.model, str(usage.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
