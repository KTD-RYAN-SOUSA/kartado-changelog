import json

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase

from ..models import ReportingRelation

pytestmark = pytest.mark.django_db


class TestReportingRelation(TestBase):
    model = "ReportingRelation"

    def test_list_reporting_relation(self, client):
        objects_count = ReportingRelation.objects.count()
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        # The call was successful and the object count in the request is equal to
        # the object count in the database

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == objects_count

    def test_retrieve_reporting_relation(self, client):
        instance = ReportingRelation.objects.first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

    def test_create_reporting_relation(self, client):
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "Criado no teste",
                        "outward": "123",
                        "inward": "321",
                    },
                    "relationships": {
                        "company": {
                            "data": {"type": "Company", "id": str(self.company.pk)}
                        }
                    },
                },
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_filter_name_reporting_relation(self, client):
        response = client.get(
            path="/{}/?company={}&name={}&page_size=1".format(
                self.model, str(self.company.pk), "Teste 1"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_filter_outward_reporting_relation(self, client):
        response = client.get(
            path="/{}/?company={}&outward={}&page_size=1".format(
                self.model, str(self.company.pk), "montante"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 2

    def test_filter_inward_reporting_relation(self, client):
        response = client.get(
            path="/{}/?company={}&inward={}&page_size=1".format(
                self.model, str(self.company.pk), "relação in"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 3

    def test_create_reporting_relation_without_company(self, client):
        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "Criado no teste",
                        "outward": "123",
                        "inward": "321",
                    },
                },
            },
        )

        # Object was not created successfully
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_reporting_relation(self, client):
        instance = ReportingRelation.objects.first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(instance.pk),
                    "attributes": {
                        "name": "Modificado no teste",
                        "outward": "321",
                        "inward": "123",
                    },
                },
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_reporting_relation(self, client):
        instance = ReportingRelation.objects.first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT
