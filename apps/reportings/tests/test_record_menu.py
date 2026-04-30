import json

import pytest
from django.db.models import Max
from rest_framework import status

from apps.companies.models import UserInCompany
from apps.occurrence_records.models import RecordPanel
from apps.reportings.models import RecordMenu, RecordMenuRelation
from apps.users.models import User
from helpers.testing.fixtures import TestBase, add_false_permission

pytestmark = pytest.mark.django_db


class TestRecordMenu(TestBase):
    model = "RecordMenu"

    def test_list_recordmenu(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 6
        assert content["data"][0]["relationships"].get("menuRecordPanels") is not None

    def test_list_recordmenu_without_permission(self, client):
        add_false_permission(self.user, self.company, self.model, {"can_view": False})

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_check_hide_menu_and_content_type_name_values(self, client):
        add_false_permission(self.user, self.company, self.model, {"can_view": True})

        obj_id = "e1b79573-473e-4f47-9d35-606f8a54b816"
        obj = RecordMenu.objects.get(pk=obj_id)

        expected_hide_menu = (
            obj.recordmenurelation_set.filter(user=self.user).first().hide_menu
        )

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, obj_id, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert content["data"]["attributes"]["hideMenu"] == expected_hide_menu
        assert response.status_code == status.HTTP_200_OK

    def test_create_recordmenu(self, client):
        hide_menu = True
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "teste criacao",
                        "created_at": "2020-09-03",
                        "contentTypeName": "reporting",
                        "hideMenu": hide_menu,
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                },
            },
        )
        content = json.loads(response.content)
        obj_id = content["data"]["id"]
        created_obj = RecordMenu.objects.get(pk=obj_id)
        panel = RecordPanel.objects.filter(menu_id=obj_id).exists()
        user_menu = created_obj.recordmenurelation_set.filter(user=self.user).first()
        all_users_have_menus = not (
            created_obj.recordmenurelation_set.all()
            .exclude(user_id__in=self.company.get_active_users_id())
            .exists()
        )
        users_max_order = created_obj.recordmenurelation_set.all().aggregate(
            Max("order")
        )
        assert created_obj.order > users_max_order["order__max"]
        assert user_menu.hide_menu == hide_menu
        assert response.status_code == status.HTTP_201_CREATED
        assert all_users_have_menus
        assert panel

    def test_create_recordmenu_without_content_type_name(self, client):
        hide_menu = True
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "teste criacao",
                        "created_at": "2020-09-03",
                        "hideMenu": hide_menu,
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                },
            },
        )
        error_message = "kartado.error.record_menu.need_to_specify_menu_type"
        content = json.loads(response.content)
        assert content["errors"][0]["detail"] == error_message
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_recordmenu_without_permission(self, client):
        add_false_permission(self.user, self.company, self.model, {"can_create": False})
        hide_menu = True
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "teste criacao",
                        "created_at": "2020-09-03",
                        "contentTypeName": "reporting",
                        "hideMenu": hide_menu,
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                },
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_edit_recordmenu(self, client):
        obj_id = "e1b79573-473e-4f47-9d35-606f8a54b816"
        obj = RecordMenu.objects.get(pk=obj_id)
        old_hide_menu = (
            obj.recordmenurelation_set.filter(user=self.user).first().hide_menu
        )
        hide_menu = not (old_hide_menu)
        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {
                        "name": "teste criacao",
                        "created_at": "2020-09-03",
                        "contentTypeName": "reporting",
                        "hideMenu": hide_menu,
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                },
            },
        )
        obj.refresh_from_db()
        new_hide_menu = (
            obj.recordmenurelation_set.filter(user=self.user).first().hide_menu
        )
        assert new_hide_menu != old_hide_menu
        assert response.status_code == status.HTTP_200_OK

    def test_try_to_edit_created_by_field(self, client):
        another_user = User.objects.get(pk="eca34fc1-6e07-44db-bfc0-d1a30bfcb24d")
        obj_id = "e1b79573-473e-4f47-9d35-606f8a54b816"
        obj = RecordMenu.objects.get(pk=obj_id)
        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {
                        "name": "teste criacao",
                        "created_at": "2020-09-03",
                        "contentTypeName": "reporting",
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "createdBy": {
                            "data": {
                                "type": "User",
                                "id": str(another_user.pk),
                            }
                        },
                    },
                },
            },
        )
        obj.refresh_from_db()
        assert obj.created_by == self.user
        assert response.status_code == status.HTTP_200_OK

    def test_try_to_edit_recordmenu_without_any_permissions(self, client):
        """
        Try to edit a recordmenu created by another user and without can_edit permission
        """
        add_false_permission(self.user, self.company, self.model, {"can_edit": False})
        obj_id = "31e9a760-57d6-4f1d-aa5e-55319abaa491"
        obj = RecordMenu.objects.get(pk=obj_id)
        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {
                        "name": "teste criacao",
                        "created_at": "2020-09-03",
                        "contentTypeName": "reporting",
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                },
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_try_to_edit_system_dafault_record_menu(self, client):
        add_false_permission(self.user, self.company, self.model, {"can_edit": True})

        obj = RecordMenu.objects.filter(system_default=True).first()
        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {
                        "name": "teste criacao",
                        "created_at": "2020-09-03",
                        "contentTypeName": "reporting",
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                },
            },
        )
        content = json.loads(response.content)
        error_message = (
            "kartado.error.record_menu.system_default_menu_records_cannot_be_edited"
        )
        assert content["errors"][0]["detail"] == error_message
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_record_menu(self, client):
        obj_id = "e1b79573-473e-4f47-9d35-606f8a54b816"
        obj = RecordMenu.objects.get(pk=obj_id)
        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        all_user_menus_deleted = not (
            RecordMenuRelation.objects.filter(record_menu_id=obj.uuid).exists()
        )
        assert all_user_menus_deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_try_to_delete_record_menu_without_permissions(self, client):
        add_false_permission(self.user, self.company, self.model, {"can_delete": False})
        obj_id = "e1b79573-473e-4f47-9d35-606f8a54b816"
        obj = RecordMenu.objects.get(pk=obj_id)

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_recordmenu_name_filter(self, client):
        obj = RecordMenu.objects.filter(name="a").first()

        response = client.get(
            path="/{}/?company={}&name=a".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert content["data"][0]["attributes"]["name"] == obj.name
        assert response.status_code == status.HTTP_200_OK

    def test_recordmenu_uuid_filter(self, client):
        obj_id = "3fbc8d53-3eb6-4cbe-b44e-41db30df7ac3"

        response = client.get(
            path="/{}/?company={}&page_size=1&uuid={}".format(
                self.model, str(self.company.pk), obj_id
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert content["data"][0]["attributes"]["uuid"] == str(obj_id)
        assert response.status_code == status.HTTP_200_OK

    def test_recordmenu_created_by_filter(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1&created_by={}".format(
                self.model, str(self.company.pk), str(self.user.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)
        assert content["data"][0]["relationships"]["createdBy"]["data"]["id"] == str(
            self.user.pk
        )
        assert response.status_code == status.HTTP_200_OK

    def test_should_create_user_menus(self, client):
        permission = self.company.permission_companies.first()

        user = User.objects.create(username="recordmenu")

        client.post(
            path="/UserInCompany/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "UserInCompany",
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

        all_user_menus_created = all(
            rm.recordmenurelation_set.filter(user=user).exists()
            for rm in RecordMenu.objects.filter(
                company=self.company, system_default=False
            )
        )
        assert all_user_menus_created

    def test_should_create_user_menus_when_user_is_activated(self, client):
        user = UserInCompany.objects.filter(is_active=False).first().user

        response = client.patch(
            path="/User/{}/?company={}".format(str(user.pk), str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "User",
                    "id": str(user.pk),
                    "attributes": {
                        "active": True,
                        "active_company": str(self.company.pk),
                    },
                }
            },
        )
        all_user_menus_created = all(
            rm.recordmenurelation_set.filter(user=user).exists()
            for rm in RecordMenu.objects.filter(
                company=self.company, system_default=False
            )
        )
        assert all_user_menus_created
        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_recordmenu_cannot_be_used_filter(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1&can_be_used=false".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert content["data"][0]["attributes"]["systemDefault"] is True

    def test_recordmenu_can_be_used_filter(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1&can_be_used=true".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert not (content["data"][0]["attributes"]["systemDefault"])

    def test_can_be_deleted_endpoint(self, client):
        instance = RecordMenu.objects.filter(
            record_menu_reportings__isnull=False
        ).first()

        response = client.get(
            path="/{}/{}/CanBeDeleted/?company={}&page_size=1".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert not (content["data"][0]["can_be_deleted"])

    def test_delete_record_menu_with_reporting(self, client):
        instance = RecordMenu.objects.filter(
            record_menu_reportings__isnull=False
        ).first()
        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        error_message = (
            "kartado.error.record_menu.menu_with_reportings_cannot_be_deleted"
        )
        assert content["errors"][0]["detail"] == error_message
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_record_menu_without_being_the_creator(self, client):
        add_false_permission(
            self.user, self.company, self.model, {"can_delete_all": True}
        )
        obj_id = "b0b0806b-328d-44c6-a52c-409903b6cb81"
        obj = RecordMenu.objects.get(pk=obj_id)
        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        all_user_menus_deleted = not (
            RecordMenuRelation.objects.filter(record_menu_id=obj.uuid).exists()
        )
        assert all_user_menus_deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT
