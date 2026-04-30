import json
from datetime import datetime

import pytest
from django.db.models import F
from rest_framework import status

from apps.resources.models import Contract, Resource
from apps.service_orders.models import ProcedureResource, ServiceOrderResource
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestServiceOrderResource(TestBase):
    model = "ServiceOrderResource"

    def test_list_service_order_resource(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_service_order_resource_without_queryset(self, client):
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

    def test_list_service_order_resource_without_company(self, client):
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_service_order_resource(self, client):
        obj = ServiceOrderResource.objects.filter(
            contract__firm__company=self.company,
            contract__firm__is_company_team=False,
        )[0]

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_service_order_resource_without_company(self, client):
        obj = ServiceOrderResource.objects.filter(
            contract__firm__company=self.company,
            contract__firm__is_company_team=False,
        )[0]

        response = client.get(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_service_order_resource_without_company_uuid(self, client):
        obj = ServiceOrderResource.objects.filter(
            contract__firm__company=self.company,
            contract__firm__is_company_team=False,
        )[0]

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, str(obj.pk), "not_uuid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_service_order_resource(self, client):
        obj = ServiceOrderResource.objects.filter(
            contract__firm__company=self.company,
            contract__firm__is_company_team=False,
        )[0]

        # Make sure the contract is current, otherwise the test will fail
        assert (
            obj.contract.contract_end
            > datetime.strptime("2023-12-30", "%Y-%m-%d").date()
        )

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"provider": "test"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_service_order_resource_with_amount(self, client):
        obj = ServiceOrderResource.objects.filter(
            contract__firm__company=self.company,
            contract__firm__is_company_team=False,
            remaining_amount__gte=F("amount"),
        )[0]

        # Make sure the contract is current, otherwise the test will fail
        assert (
            obj.contract.contract_end
            > datetime.strptime("2023-12-30", "%Y-%m-%d").date()
        )

        amount = obj.remaining_amount - obj.amount

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"amount": amount},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

        obj.refresh_from_db()
        amount = obj.amount - obj.remaining_amount - 1

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"amount": amount},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # Make sure the remaining_amount will also change when we change the amount
    def test_update_service_order_resource_and_change_amount(self, client):
        obj = ServiceOrderResource.objects.filter(
            contract__firm__company=self.company,
            contract__firm__is_company_team=False,
            remaining_amount__gte=F("amount"),
        )[0]

        # Make sure the contract is current, otherwise the test will fail
        assert (
            obj.contract.contract_end
            > datetime.strptime("2023-12-30", "%Y-%m-%d").date()
        )

        amount_increase = 50
        amount = obj.amount + amount_increase
        initial_remaining_amount = obj.remaining_amount

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"amount": amount},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

        obj.refresh_from_db()
        assert obj.remaining_amount == initial_remaining_amount + amount_increase

    def test_delete_service_order_resource(self, client):
        usages = ProcedureResource.objects.filter(
            procedure__action__service_order__company=self.company
        ).values_list("service_order_resource_id", flat=True)

        obj = ServiceOrderResource.objects.filter(
            contract__firm__company=self.company,
            contract__firm__is_company_team=False,
        ).exclude(pk__in=usages)[0]

        # Make sure the contract is current, otherwise the test will fail
        assert (
            obj.contract.contract_end
            > datetime.strptime("2023-12-30", "%Y-%m-%d").date()
        )

        response = client.delete(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_service_order_resource_without_permission(self, client):
        usages = ProcedureResource.objects.filter(
            procedure__action__service_order__company=self.company
        ).values_list("service_order_resource_id", flat=True)

        obj = ServiceOrderResource.objects.filter(
            pk__in=usages,
            contract__firm__company=self.company,
            contract__firm__is_company_team=False,
        )[0]

        response = client.delete(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_service_order_resource(self, client):
        resource = Resource.objects.filter(company=self.company)[0]
        contract = Contract.objects.filter(firm__company=self.company)[0]

        # Make sure the contract is current, otherwise the test will fail
        assert (
            contract.contract_end > datetime.strptime("2023-12-30", "%Y-%m-%d").date()
        )

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "resource": {
                            "data": {"type": "Resource", "id": str(resource.pk)}
                        },
                        "contract": {
                            "data": {"type": "Contract", "id": str(contract.pk)}
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = ServiceOrderResource.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_contract_in_force_filter(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1&contract_in_force=true".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 2
