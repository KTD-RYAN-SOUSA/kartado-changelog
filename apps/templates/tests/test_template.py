import json

import pytest
from rest_framework import status

from apps.templates.models import Template
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestTemplate(TestBase):
    model = "Template"

    def test_list_template(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_template_without_queryset(self, client):

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

    def test_list_template_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_template(self, client):

        template = Template.objects.filter(companies=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(template.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_template(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "model_name": "test_template",
                        "item_name": "test_template",
                        "options": {},
                        "validation": {},
                    },
                    "relationships": {
                        "companies": {
                            "data": [{"type": "Company", "id": str(self.company.pk)}]
                        }
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = Template.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_template_without_company_id(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "model_name": "test_template",
                        "item_name": "test_template",
                        "options": {},
                        "validation": {},
                    },
                    "relationships": {"companies": {"data": [{"type": "Company"}]}},
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_template_without_permission(self, client):

        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "model_name": "test_template",
                        "item_name": "test_template",
                        "options": {},
                        "validation": {},
                    },
                    "relationships": {
                        "companies": {
                            "data": [{"type": "Company", "id": str(self.company.pk)}]
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_uniqueness_template(self, client):

        template = Template.objects.filter(companies=self.company).first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "model_name": template.model_name,
                        "item_name": template.item_name,
                        "options": {},
                        "validation": {},
                    },
                    "relationships": {
                        "companies": {
                            "data": [
                                {
                                    "type": "Company",
                                    "id": str(template.companies.first().pk),
                                }
                            ]
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_template(self, client):

        template = Template.objects.filter(companies=self.company).first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(template.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(template.pk),
                    "attributes": {"model_name": "test_update"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_template(self, client):

        template = Template.objects.filter(companies=self.company).first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(template.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT
