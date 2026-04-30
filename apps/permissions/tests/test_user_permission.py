import json

import pytest
from rest_framework import status

from apps.permissions.models import UserPermission
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestUserPermission(TestBase):
    model = "UserPermission"

    def test_list_permission(self, client):

        response = client.get(
            path="/Permission/?page_size=1",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_permission_without_queryset(self, client):

        false_permission(self.user, self.company, self.model, allowed="none")

        response = client.get(
            path="/Permission/?page_size=1",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_permission(self, client):

        permission = UserPermission.objects.filter(companies=self.company).first()

        response = client.get(
            path="/Permission/{}/".format(str(permission.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_permission(self, client):

        response = client.post(
            path="/Permission/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "HOMOLOGATOR"},
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
        obj_created = UserPermission.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_permission_with_permissions(self, client):

        response = client.post(
            path="/Permission/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "HOMOLOGATOR",
                        "permissions": {
                            "procedure": {
                                "can_edit": True,
                                "can_view": True,
                                "queryset": "all",
                                "can_create": True,
                                "can_delete": True,
                                "allowed_status_transitions": {
                                    "0ae1850d-ade6-45b2-87d4-59c44add0e0f": [
                                        "0ae1850d-ade6-45b2-87d4-59c44add0e0f",
                                        "8460c2e0-d5cd-4e34-b5be-0f86a86935dc",
                                        "e4f6f5f2-9958-4239-a6e1-431b4aa9b2be",
                                    ]
                                },
                            }
                        },
                    },
                    "relationships": {
                        "companies": {
                            "data": [{"type": "Company", "id": str(self.company.pk)}]
                        }
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_update_permission(self, client):

        permission = UserPermission.objects.filter(companies=self.company).first()

        response = client.patch(
            path="/Permission/{}/".format(str(permission.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(permission.pk),
                    "attributes": {"permissions": {"test": "test_update"}},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_permission_with_permissions(self, client):

        permission = UserPermission.objects.filter(companies=self.company).first()

        response = client.patch(
            path="/Permission/{}/".format(str(permission.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(permission.pk),
                    "attributes": {
                        "permissions": {
                            "procedure": {
                                "can_edit": True,
                                "can_view": True,
                                "queryset": "all",
                                "can_create": True,
                                "can_delete": True,
                                "allowed_status_transitions": {
                                    "0ae1850d-ade6-45b2-87d4-59c44add0e0f": [
                                        "0ae1850d-ade6-45b2-87d4-59c44add0e0f",
                                        "8460c2e0-d5cd-4e34-b5be-0f86a86935dc",
                                        "e4f6f5f2-9958-4239-a6e1-431b4aa9b2be",
                                    ]
                                },
                            }
                        }
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_permission(self, client):

        permission = UserPermission.objects.filter(companies=self.company).first()

        response = client.delete(
            path="/Permission/{}/".format(str(permission.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_is_admin_filter(self, client):

        response = client.get(
            path="/Permission/?page_size=1&is_admin=false",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 1
