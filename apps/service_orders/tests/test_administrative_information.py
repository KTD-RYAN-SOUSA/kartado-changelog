import json

import pytest
from django.db.models import Q
from rest_framework import status

from apps.resources.models import Contract
from apps.service_orders.models import AdministrativeInformation, ServiceOrder
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestAdministrativeInformation(TestBase):
    model = "AdministrativeInformation"

    def test_list_administrative_information(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_administrative_information_without_queryset(self, client):

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

    def test_list_administrative_information_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_administrative_information(self, client):

        obj = AdministrativeInformation.objects.filter(
            service_order__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_administrative_information_without_company(self, client):

        obj = AdministrativeInformation.objects.filter(
            service_order__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_administrative_information_without_company_uuid(self, client):

        obj = AdministrativeInformation.objects.filter(
            service_order__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, str(obj.pk), "not_uuid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_administrative_information(self, client):

        obj = AdministrativeInformation.objects.filter(
            Q(service_order__company=self.company)
            & Q(service_order__is_closed=False)
            & Q(
                Q(contract__firm__is_company_team=True)
                | Q(contract__subcompany__subcompany_type="HIRING")
            )
        ).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"spendLimit": obj.spend_limit + 1},
                    "relationships": {
                        "serviceOrder": {
                            "data": {
                                "type": "ServiceOrder",
                                "id": str(obj.service_order.pk),
                            }
                        },
                        "humanResource": {
                            "data": {
                                "type": "Contract",
                                "id": str(obj.contract.pk),
                            }
                        },
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_administrative_information(self, client):

        obj = AdministrativeInformation.objects.filter(
            service_order__company=self.company, service_order__is_closed=False
        ).first()

        response = client.delete(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_administrative_information(self, client):

        service_ids = AdministrativeInformation.objects.all().values_list(
            "service_order_id", flat=True
        )
        contract_ids = AdministrativeInformation.objects.all().values_list(
            "contract_id", flat=True
        )
        service = ServiceOrder.objects.filter(
            company=self.company, is_closed=False
        ).exclude(pk__in=service_ids)[0]
        contract = Contract.objects.filter(firm__company=self.company).exclude(
            pk__in=contract_ids
        )[0]

        if contract.firm.is_company_team:
            data_json = {
                "human_resource": {
                    "data": {"type": "HumanResource", "id": str(contract.pk)}
                }
            }
        else:
            data_json = {
                "contract": {"data": {"type": "Contract", "id": str(contract.pk)}}
            }

        data_json["serviceOrder"] = {
            "data": {"type": "ServiceOrder", "id": str(service.pk)}
        }

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"spendLimit": 5},
                    "relationships": data_json,
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # __str__ method
        content = json.loads(response.content)
        obj_created = AdministrativeInformation.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()
