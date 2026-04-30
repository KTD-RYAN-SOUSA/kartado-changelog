import json

import pytest
from rest_framework import status

from apps.services.models import ServiceSpecs
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestServiceSpecs(TestBase):
    model = "ServiceSpecs"

    def test_list_service_specs(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_service_specs_without_queryset(self, client):

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

    def test_list_service_specs_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_service_specs(self, client):

        specs = ServiceSpecs.objects.filter(service__company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(specs.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_service_specs_without_company(self, client):

        specs = ServiceSpecs.objects.filter(service__company=self.company).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(specs.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_service_specs_without_company_uuid(self, client):

        specs = ServiceSpecs.objects.filter(service__company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, str(specs.pk), "not_uuid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_service_specs(self, client):

        specs = ServiceSpecs.objects.filter(service__company=self.company).first()
        occtype = specs.occurrence_type
        service = specs.service
        specs.delete()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"formula": {"backend": "test"}},
                    "relationships": {
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occtype.pk),
                            }
                        },
                        "service": {"data": {"type": "Service", "id": str(service.pk)}},
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = ServiceSpecs.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_service_specs_without_service_id(self, client):

        specs = ServiceSpecs.objects.filter(service__company=self.company).first()
        occtype = specs.occurrence_type
        specs.delete()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"formula": {"backend": "test"}},
                    "relationships": {
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occtype.pk),
                            }
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_service_specs(self, client):

        specs = ServiceSpecs.objects.filter(service__company=self.company).first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(specs.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(specs.pk),
                    "attributes": {"formula": {"backend": "test"}},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_service_specs_with_wrong_formula(self, client):

        specs = ServiceSpecs.objects.filter(service__company=self.company).first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(specs.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(specs.pk),
                    "attributes": {"formula": {"test": "test"}},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_service_specs(self, client):

        specs = ServiceSpecs.objects.filter(service__company=self.company).first()

        response = client.delete(
            path="/{}/{}/".format(self.model, str(specs.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT
