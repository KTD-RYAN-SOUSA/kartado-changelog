import json

import pytest
from django_rest_passwordreset.models import ResetPasswordToken
from rest_framework import status

from apps.permissions.models import UserPermission
from apps.users.models import User
from helpers.testing.fixtures import TestBase, add_false_permission, false_permission

pytestmark = pytest.mark.django_db


class TestUser(TestBase):
    model = "User"

    @pytest.fixture
    def user_token(self):
        self.headers = {"HTTP_USER_AGENT": "Mozilla/5.0", "REMOTE_ADDR": "127.0.0.1"}
        self.user = User.objects.first()
        self.token = ResetPasswordToken.objects.create(
            user=self.user,
            user_agent=self.headers["HTTP_USER_AGENT"],
            ip_address=self.headers["REMOTE_ADDR"],
        )

    def test_list_user(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_user_without_queryset(self, client):
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

    def test_list_user_without_company(self, client):
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_user(self, client):
        user = self.company.users.all().exclude(pk=self.user.pk)[0]

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(user.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_user_request(self, client):
        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(self.user.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_user(self, client):
        permission = UserPermission.objects.filter(
            companies=self.company, name="HOMOLOGATOR"
        )[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "username": "test.test",
                        "password": "piloto2018@",
                        "confirm_password": "piloto2018@",
                        "memberships": [
                            {
                                "permission": str(permission.pk),
                                "company": str(self.company.pk),
                            }
                        ],
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

        # object created
        assert response.status_code == status.HTTP_201_CREATED
        # __str__ method
        content = json.loads(response.content)
        obj_created = User.objects.get(pk=content["data"]["id"])
        assert obj_created.legacy_uuid is None
        assert obj_created.__str__()

    def test_create_user_with_blank_legacy_uuid(self, client):
        permission = UserPermission.objects.filter(
            companies=self.company, name="HOMOLOGATOR"
        )[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "username": "test.test",
                        "password": "piloto2018@",
                        "confirm_password": "piloto2018@",
                        "legacy_uuid": "",
                        "memberships": [
                            {
                                "permission": str(permission.pk),
                                "company": str(self.company.pk),
                            }
                        ],
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

        # object created
        content = json.loads(response.content)
        assert content["data"]["attributes"]["legacyUuid"] == ""
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_user_without_memberships(self, client):
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "username": "test.test",
                        "password": "piloto2018@",
                        "confirm_password": "piloto2018@",
                        "memberships": [],
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

        assert response.status_code == status.HTTP_201_CREATED

    def test_create_user_with_wrong_confirm_password(self, client):
        permission = UserPermission.objects.filter(
            companies=self.company, name="HOMOLOGATOR"
        )[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "username": "test.test",
                        "password": "piloto2018@",
                        "confirm_password": "piloto2000@",
                        "memberships": [
                            {
                                "permission": str(permission.pk),
                                "company": str(self.company.pk),
                            }
                        ],
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

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_user_with_wrong_permission(self, client):
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "username": "test.test",
                        "password": "piloto2018@",
                        "confirm_password": "piloto2018@",
                        "memberships": [
                            {
                                "permission": "86bf3df8-c675-4da2-aca9-0a6d667edded",
                                "company": str(self.company.pk),
                            }
                        ],
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

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_user_with_wrong_company(self, client):
        permission = UserPermission.objects.filter(
            companies=self.company, name="HOMOLOGATOR"
        )[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "username": "test.test",
                        "password": "piloto2018@",
                        "confirm_password": "piloto2018@",
                        "memberships": [
                            {
                                "permission": str(permission.pk),
                                "company": "86bf3df8-c675-4da2-aca9-0a6d667edded",
                            }
                        ],
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

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_user_with_no_company(self, client):
        permission = UserPermission.objects.filter(
            companies=self.company, name="HOMOLOGATOR"
        )[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "username": "test.test",
                        "password": "piloto2018@",
                        "confirm_password": "piloto2018@",
                        "memberships": [{"permission": str(permission.pk)}],
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_user(self, client):
        user = self.company.users.all().exclude(pk=self.user.pk)[0]

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(user.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(user.pk),
                    "attributes": {"username": "test_update"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_self_user(self, client):
        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(self.user.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(self.user.pk),
                    "attributes": {"username": "test_update"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_user(self, client):
        user = self.company.users.all().exclude(pk=self.user.pk)[0]

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(user.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_reset_password_success(self, client):

        user = User.objects.first()

        headers = {"HTTP_USER_AGENT": "Mozilla/5.0", "REMOTE_ADDR": "127.0.0.1"}

        data = {
            "data": {
                "type": "ResetPasswordRequestTokenCustom",
                "attributes": {
                    "email": user.email,
                    "username": user.username,
                },
            }
        }

        response = client.post(
            path="/{}/".format("ResetPassword"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=data,
            **headers
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)

        assert (
            content["data"][0]["detail"]
            == "kartado.success.password.new_password_link_sent"
        )

    def test_reset_password_invalid_email(self, client):

        user = User.objects.first()

        data = {
            "data": {
                "type": "ResetPasswordRequestTokenCustom",
                "attributes": {
                    "email": user.email,
                    "username": "test@example.com",
                },
            }
        }

        response = client.post(
            path="/{}/".format("ResetPassword"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=data,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        content = json.loads(response.content)

        assert (
            content["errors"][0]["detail"]
            == "kartado.error.email_not_associated_with_system"
        )

    def test_update_restricted_fields_without_permission(self, client):
        """Testa se usuário sem can_Edit_All_Fields não pode editar campos restritos"""
        user = self.company.users.all().exclude(pk=self.user.pk)[0]

        new_first_name = "Novo Nome"

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(user.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(user.pk),
                    "attributes": {
                        "first_name": new_first_name,
                        "active_company": str(self.company.pk),
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            "permissão para alterar estes campos restritos" in response.content.decode()
        )

    def test_update_restricted_fields_with_permission(self, client):
        """Testa se usuário com can_Edit_All_Fields pode editar campos restritos"""
        user = self.company.users.all().exclude(pk=self.user.pk)[0]

        add_false_permission(
            self.user, self.company, self.model, {"can_edit_all_fields": True}
        )

        new_first_name = "Novo Nome"

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(user.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(user.pk),
                    "attributes": {
                        "first_name": new_first_name,
                        "active_company": str(self.company.pk),
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

        user.refresh_from_db()
        assert user.first_name == new_first_name

    def test_update_metadata_restricted_fields_without_permission(self, client):
        """Testa validação de campos restritos do metadata sem permissão"""
        user = self.company.users.all().exclude(pk=self.user.pk)[0]

        new_metadata = {"role": "admin"}

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(user.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(user.pk),
                    "attributes": {
                        "metadata": new_metadata,
                        "active_company": str(self.company.pk),
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            "permissão para alterar estes campos restritos" in response.content.decode()
        )

    def test_update_metadata_restricted_fields_with_permission(self, client):
        """Testa se usuário com can_Edit_All_Fields pode editar campos restritos do metadata"""
        user = self.company.users.all().exclude(pk=self.user.pk)[0]

        add_false_permission(
            self.user, self.company, self.model, {"can_edit_all_fields": True}
        )

        new_metadata = {
            "role": "admin",
            "organizationalUnit": "TI",
            "rhStatus": "active",
        }

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(user.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(user.pk),
                    "attributes": {
                        "metadata": new_metadata,
                        "active_company": str(self.company.pk),
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

        user.refresh_from_db()

        assert user.metadata.get("role") == "admin"
        assert user.metadata.get("organizational_unit") == "TI"
        assert user.metadata.get("rh_status") == "active"

    def test_update_non_restricted_fields_without_permission(self, client):
        """Testa se usuário sem can_Edit_All_Fields pode editar campos não restritos"""
        user = self.company.users.all().exclude(pk=self.user.pk)[0]

        new_username = "novo_username"

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(user.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(user.pk),
                    "attributes": {
                        "username": new_username,
                        "active_company": str(self.company.pk),
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

        user.refresh_from_db()
        assert user.username == new_username

    def test_user_search(self, client, enable_unaccent):
        response = client.get(
            path="/{}/?company={}&page_size=1&search=engiehehe".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)

        assert content["meta"]["pagination"]["count"] == 1

    def test_user_active(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1&active=False".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)

        assert content["meta"]["pagination"]["count"] == 1

    def test_user_confirm_password(self, client, user_token):

        data = {
            "data": {
                "type": "ResetPasswordConfirmCustom",
                "attributes": {
                    "token": self.token.key,
                    "password": "ladjlksjdklasdjlashdjl",
                },
            }
        }

        response = client.post(
            path="/{}/".format("ConfirmPassword"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=data,
            **self.headers
        )

        assert response.status_code == status.HTTP_200_OK

    def test_user_is_new_password_valid(self, client, user_token):

        data = {
            "data": {
                "type": "IsNewPasswordValid",
                "attributes": {
                    "token": self.token.key,
                    "password": "fqopimf2o3ime129iomoiedm",
                },
            }
        }

        response = client.post(
            path="/{}/".format("IsNewPasswordValid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=data,
            **self.headers
        )

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.parametrize(
        "password,error_message",
        [
            ("a", "kartado.error.password.need_at_least_eight_chars"),
            ("engie", "kartado.error.password.contains_user_personal_info"),
            ("qwertyuiop", "kartado.error.password.too_common"),
            ("83030983820329823", "kartado.error.password.only_numbers"),
        ],
    )
    def test_user_is_new_password_valid_errors(
        self, client, user_token, password, error_message
    ):

        data = {
            "data": {
                "type": "IsNewPasswordValid",
                "attributes": {
                    "token": self.token.key,
                    "password": password,
                },
            }
        }

        response = client.post(
            path="/{}/".format("IsNewPasswordValid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=data,
            **self.headers
        )

        content = json.loads(response.content)

        # Error creating object
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        assert content["errors"][0]["detail"] == error_message
