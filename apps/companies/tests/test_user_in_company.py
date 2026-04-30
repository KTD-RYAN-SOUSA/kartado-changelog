import json

import pytest
from rest_framework import status

from apps.companies.models import UserInCompany
from apps.users.models import User
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestUserInCompany(TestBase):
    model = "UserInCompany"

    def test_list_userincompany(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_userincompany_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_userincompany_without_uuid(self, client):

        response = client.get(
            path="/{}/?company={}".format(self.model, "test"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_userincompany(self, client):

        permission = self.company.permission_companies.first()

        user = User.objects.create(username="teste")

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "user": {"data": {"type": "User", "id": str(user.pk)}},
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "permissions": {
                            "data": {
                                "type": "UserPermission",
                                "id": str(permission.pk),
                            }
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = UserInCompany.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED
