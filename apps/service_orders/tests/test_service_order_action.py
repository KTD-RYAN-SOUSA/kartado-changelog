import json
from datetime import datetime

import pytest
from rest_framework import status

from apps.companies.models import Firm
from apps.service_orders.helpers.email_judiciary.build_data import (
    build_data_check_email_judiciary,
)
from apps.service_orders.models import (
    ServiceOrder,
    ServiceOrderAction,
    ServiceOrderActionStatus,
)
from helpers.strings import keys_to_snake_case
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestServiceOrderAction(TestBase):
    model = "ServiceOrderAction"

    def test_list_service_order_action(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_filter_service_order_action(self, client):
        initial_date = "01/01/2019"
        final_date = "01/06/2019"

        response = client.get(
            path="/{}/?company={}&deadline_after={}&page_size=1".format(
                self.model, str(self.company.pk), initial_date
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.get(
            path="/{}/?company={}&deadline_before={}&page_size=1".format(
                self.model, str(self.company.pk), final_date
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.get(
            path="/{}/?company={}&deadline_after={}&deadline_before={}&page_size=1".format(
                self.model, str(self.company.pk), initial_date, final_date
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.get(
            path="/{}/?company={}&deadline_before={}&page_size=1".format(
                self.model, str(self.company.pk), ""
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_service_order_action_without_queryset(self, client):
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

    def test_list_service_order_action_without_company(self, client):
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_service_order_action(self, client):
        obj = ServiceOrderAction.objects.filter(
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

    def test_get_service_order_action_without_company(self, client):
        obj = ServiceOrderAction.objects.filter(
            service_order__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_service_order_action_without_company_uuid(self, client):
        obj = ServiceOrderAction.objects.filter(
            service_order__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, str(obj.pk), "not_uuid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_service_order_action(self, client):
        obj = ServiceOrderAction.objects.filter(
            service_order__company=self.company,
            service_order__is_closed=False,
            procedures__isnull=True,
        )[0]

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"name": "test", "allow_forwarding": False},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_service_order_action_without_permission(self, client):
        obj = ServiceOrderAction.objects.filter(
            service_order__company=self.company, service_order__is_closed=True
        )[0]

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"name": "test"},
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_service_order_action(self, client):
        obj = ServiceOrderAction.objects.filter(
            service_order__company=self.company, service_order__is_closed=False
        ).first()

        response = client.delete(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_create_service_order_action(self, client):
        firm = Firm.objects.filter(company=self.company).first()
        action_status = ServiceOrderActionStatus.objects.filter(
            companies=self.company
        ).first()
        service = ServiceOrder.objects.filter(
            company=self.company, is_closed=False
        ).first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "deadline": datetime.now(),
                        "allow_forwarding": False,
                    },
                    "relationships": {
                        "serviceOrder": {
                            "data": {
                                "type": "ServiceOrder",
                                "id": str(service.pk),
                            }
                        },
                        "serviceOrderActionStatus": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(action_status.pk),
                            }
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = ServiceOrderAction.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_service_order_action_without_permission(self, client):
        firm = Firm.objects.filter(company=self.company).first()
        action_status = ServiceOrderActionStatus.objects.filter(
            companies=self.company
        ).first()
        service = ServiceOrder.objects.filter(
            company=self.company, is_closed=True
        ).first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test", "deadline": datetime.now()},
                    "relationships": {
                        "serviceOrder": {
                            "data": {
                                "type": "ServiceOrder",
                                "id": str(service.pk),
                            }
                        },
                        "serviceOrderActionStatus": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(action_status.pk),
                            }
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_service_order_action_check_data_email_judiciary(self, client):
        obj = ServiceOrderAction.objects.filter(
            service_order__company=self.company,
            service_order__company__company_firms__is_judiciary=True,
        ).first()

        response = client.get(
            path="/{}/{}/CheckEmailJudiciary/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

        data = build_data_check_email_judiciary(obj, self)

        content = keys_to_snake_case((json.loads(response.content))["data"])

        valid_context = False
        for key, value in content.items():
            if value:
                if data[key] != value:
                    valid_context = False
                    break
                valid_context = True

        assert valid_context is True
