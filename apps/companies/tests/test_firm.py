import json
from datetime import date

import pytest
from django.db.models import Q
from rest_framework import status

from apps.companies.models import Firm, InspectorInFirm, UserInFirm
from apps.daily_reports.models import MultipleDailyReport
from apps.service_orders.models import ServiceOrder
from apps.users.models import User
from helpers.testing.fixtures import TestBase, add_false_permission, false_permission

pytestmark = pytest.mark.django_db


class TestFirm(TestBase):
    model = "Firm"

    cnpj_valid = "29.128.809/0001-85"

    def test_list_firms(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] > 0

    def test_list_firms_without_queryset(self, client):
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

    def test_list_firm_without_company(self, client):
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_firm_without_uuid(self, client):
        response = client.get(
            path="/{}/?company={}".format(self.model, "test"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_filter_firm(self, client):
        service_order = ServiceOrder.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/?company={}&service_order={}".format(
                self.model, str(self.company.pk), str(service_order.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_firm(self, client):
        users_in_firm = (
            UserInFirm.objects.all().values_list("user", flat=True).distinct()
        )
        user = User.objects.all().exclude(pk__in=users_in_firm)[0]

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "cnpj": self.cnpj_valid,
                        "active": True,
                        "isCompanyTeam": True,
                        "customOptions": {},
                        "metadata": {},
                    },
                    "relationships": {
                        "manager": {"data": {"type": "User", "id": str(self.user.pk)}},
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "add_users": {"data": [{"type": "User", "id": str(user.pk)}]},
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = Firm.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()
        assert obj_created.legacy_uuid is None
        # UserInFirm created
        assert UserInFirm.objects.filter(firm=obj_created)

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_firm_with_alphanumeric_cnpj(self, client):
        """KAP-46: Firm aceita CNPJ alfanumérico (IN RFB 2.229/2024)."""
        users_in_firm = (
            UserInFirm.objects.all().values_list("user", flat=True).distinct()
        )
        user = User.objects.all().exclude(pk__in=users_in_firm)[0]
        cnpj_alphanumeric = "12.ABC.345/01DE-35"  # exemplo oficial Serpro

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test alphanumeric",
                        "cnpj": cnpj_alphanumeric,
                        "active": True,
                        "isCompanyTeam": True,
                        "customOptions": {},
                        "metadata": {},
                    },
                    "relationships": {
                        "manager": {"data": {"type": "User", "id": str(self.user.pk)}},
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "add_users": {"data": [{"type": "User", "id": str(user.pk)}]},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        content = json.loads(response.content)
        assert content["data"]["attributes"]["cnpj"] == cnpj_alphanumeric
        obj_created = Firm.objects.get(pk=content["data"]["id"])
        assert obj_created.cnpj == cnpj_alphanumeric

    def test_create_firm_with_blank_legacy_uuid(self, client):
        users_in_firm = (
            UserInFirm.objects.all().values_list("user", flat=True).distinct()
        )
        user = User.objects.all().exclude(pk__in=users_in_firm)[0]

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test blank legacy_uuid",
                        "cnpj": self.cnpj_valid,
                        "active": True,
                        "isCompanyTeam": True,
                        "customOptions": {},
                        "metadata": {},
                        "legacy_uuid": "",
                    },
                    "relationships": {
                        "manager": {"data": {"type": "User", "id": str(self.user.pk)}},
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "add_users": {"data": [{"type": "User", "id": str(user.pk)}]},
                    },
                }
            },
        )

        content = json.loads(response.content)
        assert content["data"]["attributes"]["legacyUuid"] == ""
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_firm_without_valid_users(self, client):
        cnpj_valid = "29.128.809/0001-85"

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "cnpj": cnpj_valid,
                        "active": True,
                        "isCompanyTeam": True,
                        "customOptions": {},
                        "metadata": {},
                    },
                    "relationships": {
                        "manager": {"data": {"type": "User", "id": str(self.user.pk)}},
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "add_users": {
                            "data": [
                                {
                                    "type": "User",
                                    "id": "17ad37b0-895e-4954-9fc2-3c320957d75c",
                                }
                            ]
                        },
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_firm(self, client):
        firm = Firm.objects.filter(company=self.company).first()
        users_in_firm = (
            UserInFirm.objects.all().values_list("user", flat=True).distinct()
        )
        user = User.objects.all().exclude(pk__in=users_in_firm)[0]
        len_before = len(UserInFirm.objects.filter(firm=firm))

        response = client.patch(
            path="/{}/{}/".format(self.model, str(firm.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(firm.pk),
                    "attributes": {"logo": ""},
                    "relationships": {
                        "add_users": {"data": [{"type": "User", "id": str(user.pk)}]}
                    },
                }
            },
        )

        # UserInFirm created
        len_after = len(UserInFirm.objects.filter(firm=firm))
        assert len_after > len_before

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_firm_without_valid_users(self, client):
        firm = Firm.objects.filter(company=self.company).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(firm.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(firm.pk),
                    "attributes": {},
                    "relationships": {
                        "add_users": {
                            "data": [
                                {
                                    "type": "User",
                                    "id": "17ad37b0-895e-4954-9fc2-3c320957d75c",
                                }
                            ]
                        }
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_firm_with_inspectors(self, client):
        inspector = User.objects.first()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "cnpj": self.cnpj_valid,
                        "active": True,
                        "isCompanyTeam": True,
                        "customOptions": {},
                        "metadata": {},
                    },
                    "relationships": {
                        "manager": {"data": {"type": "User", "id": str(self.user.pk)}},
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "add_inspectors": {
                            "data": [{"type": "User", "id": str(inspector.pk)}]
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = Firm.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # InspectorInForm created
        assert InspectorInFirm.objects.filter(firm=obj_created)

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_update_firm_add_valid_inspectors(self, client):
        firm = Firm.objects.filter(company=self.company).first()
        inspectors_in_firm = (
            InspectorInFirm.objects.filter(firm=firm)
            .values_list("user", flat=True)
            .distinct()
        )
        inspector = User.objects.all().exclude(pk__in=inspectors_in_firm)[0]
        len_before_update = InspectorInFirm.objects.all().count()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(firm.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(firm.pk),
                    "relationships": {
                        "add_inspectors": {
                            "data": [{"type": "User", "id": str(inspector.pk)}]
                        }
                    },
                }
            },
        )

        len_after_update = InspectorInFirm.objects.all().count()
        assert len_after_update > len_before_update

        assert response.status_code == status.HTTP_200_OK

    def test_update_firm_add_already_added_inspector(self, client):
        inspector = User.objects.first()

        post_response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "cnpj": self.cnpj_valid,
                        "active": True,
                        "isCompanyTeam": True,
                        "customOptions": {},
                        "metadata": {},
                    },
                    "relationships": {
                        "manager": {"data": {"type": "User", "id": str(self.user.pk)}},
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "add_inspectors": {
                            "data": [{"type": "User", "id": str(inspector.pk)}]
                        },
                    },
                }
            },
        )

        content = json.loads(post_response.content)
        firm_created = Firm.objects.get(pk=content["data"]["id"])

        patch_response = client.patch(
            path="/{}/{}/".format(self.model, str(firm_created.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(firm_created.pk),
                    "attributes": {"logo": ""},
                    "relationships": {
                        "add_inspectors": {
                            "data": [{"type": "User", "id": str(inspector.pk)}]
                        }
                    },
                }
            },
        )

        assert patch_response.status_code == status.HTTP_400_BAD_REQUEST

        error_message = patch_response.data[0]["detail"].title()
        assert (
            error_message.lower()
            == "kartado.error.firm.user_does_not_exist_or_is_already_an_inspector"
        )

    def test_filter_firm_manager(self, client):
        qs_firm = Firm.objects.filter(manager__isnull=False, company=self.company.pk)
        firm = qs_firm.first()

        manager = firm.manager
        search_pk = str(manager.pk)

        response = client.get(
            path="/{}/?company={}&manager={}&page_size=1".format(
                self.model, str(self.company.pk), search_pk
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expectative_manager = False
        for _data in content["data"]:
            if _data["relationships"]["manager"]["data"]["id"] in search_pk.split(","):
                expectative_manager = True
                break

        assert expectative_manager is True

        expectative_count = qs_firm.filter(manager__pk=search_pk).count()

        assert expectative_count == len(content["data"])

    def test_filter_firm_list_manager(self, client):
        qs_firm = Firm.objects.filter(manager__isnull=False, company=self.company.pk)

        search_pk = (",").join(
            [str(pk) for pk in qs_firm.values_list("manager__pk", flat=True)]
        )

        response = client.get(
            path="/{}/?company={}&manager={}".format(
                self.model, str(self.company.pk), search_pk
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expectative_count = qs_firm.filter(manager__pk__in=search_pk.split(",")).count()

        assert content["meta"]["pagination"]["count"] == expectative_count

    def test_filter_firm_inspectors(self, client):
        qs_firm = Firm.objects.filter(inspectors__isnull=False, company=self.company.pk)
        firm = qs_firm.first()

        inspector = firm.inspectors.all().first()
        search_pk = str(inspector.pk)

        response = client.get(
            path="/{}/?company={}&inspectors={}&page_size=1".format(
                self.model, str(self.company.pk), search_pk
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expectative_inspector = False
        for _data in content["data"]:
            for _obj in _data["relationships"]["inspectors"]["data"]:
                if _obj["id"] in search_pk.split(","):
                    expectative_inspector = True
                    break
            else:
                continue
            break

        assert expectative_inspector is True

        expectative_count = qs_firm.filter(inspectors__pk=search_pk).count()

        assert expectative_count == len(content["data"])

    def test_filter_firm_list_inspectors(self, client):
        qs_firm = Firm.objects.filter(inspectors__isnull=False, company=self.company.pk)

        search_pk = (",").join(
            [str(pk) for pk in qs_firm.values_list("inspectors__pk", flat=True)]
        )

        response = client.get(
            path="/{}/?company={}&inspectors={}".format(
                self.model, str(self.company.pk), search_pk
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expectative_count = qs_firm.filter(
            inspectors__pk__in=search_pk.split(",")
        ).count()

        assert content["meta"]["pagination"]["count"] == expectative_count

    def test_filter_firm_users(self, client):
        qs_firm = Firm.objects.filter(users__isnull=False, company=self.company.pk)
        firm = qs_firm.first()

        inspector = firm.users.all().first()
        search_pk = str(inspector.pk)

        response = client.get(
            path="/{}/?company={}&users={}&page_size=25".format(
                self.model, str(self.company.pk), search_pk
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expectative_user = False
        for _data in content["data"]:
            for _obj in _data["relationships"]["users"]["data"]:
                if _obj["id"] in search_pk.split(","):
                    expectative_user = True
                    break
            else:
                continue
            break

        assert expectative_user is True

        expectative_users = []
        for firm in qs_firm.filter(users__pk=search_pk):
            expectative_users += list(firm.users.all())

        expectative_count = len(set(expectative_users))

        assert expectative_count == len(content["data"])

    def test_filter_firm_list_users(self, client):
        qs_firm = Firm.objects.filter(users__isnull=False, company=self.company.pk)

        search_pk = (",").join(
            [str(pk) for pk in qs_firm.values_list("users__pk", flat=True)]
        )

        response = client.get(
            path="/{}/?company={}&users={}".format(
                self.model, str(self.company.pk), search_pk
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expectative_users = []
        for firm in qs_firm.filter(users__pk__in=search_pk.split(",")):
            expectative_users += list(firm.users.all())

        expectative_count = len(set(expectative_users))

        assert content["meta"]["pagination"]["count"] == expectative_count

    def test_filter_firm_active(self, client):
        qs_firm = Firm.objects.filter(active=True, company=self.company.pk)

        response = client.get(
            path="/{}/?company={}&active={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expectative_count = qs_firm.count()

        assert content["meta"]["pagination"]["count"] == expectative_count

    def test_filter_firm_not_active(self, client):
        qs_firm = Firm.objects.filter(active=False, company=self.company.pk)

        response = client.get(
            path="/{}/?company={}&active={}".format(
                self.model, str(self.company.pk), False
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expectative_count = qs_firm.count()

        assert content["meta"]["pagination"]["count"] == expectative_count

    def test_filter_firm_ordering_subcompany_name(self, client):
        order_by_orm = "subcompany__name"

        qs_firm = Firm.objects.filter(company=self.company.pk).order_by(order_by_orm)

        response = client.get(
            path="/{}/?company={}&ordering={}".format(
                self.model, str(self.company.pk), order_by_orm
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)

        top_filter = str(qs_firm.first().pk)
        assert top_filter == content["data"][0]["id"]

        assert content["meta"]["pagination"]["count"] > 1

    def test_filter_firm_ordering_desc_subcompany_name(self, client):
        order_by_orm = "-subcompany__name"

        qs_firm = Firm.objects.filter(company=self.company.pk).order_by(order_by_orm)

        response = client.get(
            path="/{}/?company={}&ordering={}".format(
                self.model, str(self.company.pk), order_by_orm
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)

        top_filter = str(qs_firm.first().pk)
        assert top_filter == content["data"][0]["id"]

        qs_firm.count()

        assert content["meta"]["pagination"]["count"] > 1

    def test_filter_firm_ordering_members_amount(self, client):
        order_by_orm = "members_amount"

        qs_firm = Firm.objects.filter(company=self.company.pk).order_by(order_by_orm)

        response = client.get(
            path="/{}/?company={}&ordering={}".format(
                self.model, str(self.company.pk), order_by_orm
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)

        top_filter = str(qs_firm.first().pk)
        assert top_filter == content["data"][0]["id"]

        assert content["meta"]["pagination"]["count"] > 1

    def test_filter_firm_ordering_desc_members_amount(self, client):
        order_by_orm = "-members_amount"

        qs_firm = Firm.objects.filter(company=self.company.pk).order_by(order_by_orm)

        response = client.get(
            path="/{}/?company={}&ordering={}".format(
                self.model, str(self.company.pk), order_by_orm
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)

        top_filter = str(qs_firm.first().pk)
        assert top_filter == content["data"][0]["id"]

        qs_firm.count()

        assert content["meta"]["pagination"]["count"] > 1

    def test_filter_can_rdo_create_with_can_create_and_edit_all_firms_permission(
        self, client
    ):
        add_false_permission(
            self.user,
            self.company,
            "MultipleDailyReport",
            {"can_create_and_edit_all_firms": True},
        )

        response = client.get(
            path="/{}/?company={}&can_rdo_create={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expected_count = Firm.objects.filter(company_id=self.company.pk).count()

        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_view_with_can_view_all_firms_permission(self, client):
        add_false_permission(
            self.user, self.company, "MultipleDailyReport", {"can_view_all_firms": True}
        )

        response = client.get(
            path="/{}/?company={}&can_rdo_view={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expected_count = Firm.objects.filter(company_id=self.company.pk).count()

        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_create_without_can_create_and_edit_all_firms_permission(
        self, client
    ):
        add_false_permission(
            self.user,
            self.company,
            "MultipleDailyReport",
            {"can_create_and_edit_all_firms": False, "can_view_all_firms": False},
        )

        response = client.get(
            path="/{}/?company={}&can_rdo_create={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expected_count = (
            Firm.objects.filter(
                Q(users__uuid=self.user.uuid)
                | Q(inspectors__uuid=self.user.uuid)
                | Q(manager_id=self.user.uuid)
            )
            .distinct()
            .count()
        )

        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_view_without_can_view_all_firms_permission(self, client):
        add_false_permission(
            self.user,
            self.company,
            "MultipleDailyReport",
            {"can_create_and_edit_all_firms": False, "can_view_all_firms": False},
        )

        response = client.get(
            path="/{}/?company={}&can_rdo_view={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expected_count = (
            Firm.objects.filter(
                Q(users__uuid=self.user.uuid)
                | Q(inspectors__uuid=self.user.uuid)
                | Q(manager_id=self.user.uuid)
            )
            .distinct()
            .count()
        )

        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_view_without_can_view_all_firms_permission_set(
        self, client
    ):
        response = client.get(
            path="/{}/?company={}&can_rdo_view={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expected_count = Firm.objects.filter(company_id=self.company.pk).count()

        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_view_when_value_is_false(self, client):

        add_false_permission(
            self.user,
            self.company,
            "MultipleDailyReport",
            {"can_view_all_firms": False},
        )

        response = client.get(
            path="/{}/?company={}&can_rdo_view={}".format(
                self.model, str(self.company.pk), "false"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK

        # Quando value is not True, deve retornar TODOS os registros sem filtros
        expected_count = Firm.objects.filter(company_id=self.company.pk).count()
        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_create_without_can_view_all_firms_permission_set(
        self, client
    ):
        response = client.get(
            path="/{}/?company={}&can_rdo_create={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expected_count = Firm.objects.filter(company_id=self.company.pk).count()

        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_create_when_value_is_false(self, client):

        add_false_permission(
            self.user,
            self.company,
            "MultipleDailyReport",
            {"can_create_and_edit_all_firms": False},
        )

        response = client.get(
            path="/{}/?company={}&can_rdo_create={}".format(
                self.model, str(self.company.pk), "false"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK

        expected_count = Firm.objects.filter(company_id=self.company.pk).count()
        assert content["meta"]["pagination"]["count"] == expected_count

    def test_update_with_deletion(self, client):

        firm_uuid = "4ee50e2c-be0b-4d32-9341-efb4c0d89818"
        firm = Firm.objects.filter(uuid=firm_uuid).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(firm.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(firm.pk),
                    "attributes": {"active": False, "delete": True},
                    "relationships": {},
                }
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_without_deletion(self, client):

        firm_uuid = "eb093034-7f05-4d93-8a7d-cdf8ee04923d"
        firm = Firm.objects.filter(uuid=firm_uuid).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(firm.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(firm.pk),
                    "attributes": {"active": False, "delete": True},
                    "relationships": {},
                }
            },
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["data"]["attributes"]["deleteInProgress"]

        firm = Firm.objects.filter(uuid=firm_uuid)

        assert firm.exists()
        firm_object = firm.first()
        assert not firm_object.active
        assert not firm_object.delete_in_progress

    def test_get_rdo_found_on_date_with_valid_date(self, client):
        """Test get_rdo_found_on_date method with valid date and existing MDR"""

        firm = Firm.objects.create(
            name="Test Firm for RDO",
            cnpj=self.cnpj_valid,
            company=self.company,
            manager=self.user,
            active=True,
        )

        # Create a MultipleDailyReport for the test
        test_date = date(2024, 1, 15)
        mdr = MultipleDailyReport.objects.create(
            date=test_date, created_by=self.user, firm=firm, company=self.company
        )

        # Make request with has_rdo_on_date parameter
        response = client.get(
            path="/{}/?company={}&has_rdo_on_date={}".format(
                self.model, str(self.company.pk), test_date.strftime("%Y-%m-%d")
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        # Find the firm in the response and check if rdo_found_on_date is set
        firm_data = None
        for item in content["data"]:
            if item["id"] == str(firm.pk):
                firm_data = item
                break

        assert firm_data is not None
        assert firm_data["attributes"]["rdoFoundOnDate"] == str(mdr.uuid)
