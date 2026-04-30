import json
from datetime import datetime

import pytest
from rest_framework import status

from apps.companies.models import Firm
from apps.service_orders.models import Procedure, ServiceOrderAction
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestProcedure(TestBase):
    model = "Procedure"

    def test_list_procedure(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_procedure_without_queryset(self, client):

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

    def test_list_procedure_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_procedure(self, client):

        obj = Procedure.objects.filter(
            action__service_order__company=self.company,
            firm__company=self.company,
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

        # __str__ method
        obj.refresh_from_db()
        obj.firm.company.metadata["extra_actions"]["sendToApproval"][
            "sent_to_all_in_firm"
        ] = True
        obj.firm.company.save()
        obj.save()
        assert obj.__str__()

    def test_get_procedure_without_company(self, client):

        obj = Procedure.objects.filter(
            action__service_order__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_procedure_without_company_uuid(self, client):

        obj = Procedure.objects.filter(
            action__service_order__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, str(obj.pk), "not_uuid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_procedure(self, client):

        obj = Procedure.objects.filter(
            action__service_order__company=self.company,
            action__service_order__is_closed=False,
        ).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"toDo": "test"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_procedure(self, client):

        obj = Procedure.objects.filter(
            action__service_order__company=self.company,
            action__service_order__is_closed=False,
        ).first()

        response = client.delete(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_create_procedure_without_new_service_order_status(self, client):

        action = ServiceOrderAction.objects.filter(
            service_order__company=self.company, service_order__is_closed=False
        )[0]
        firm = Firm.objects.filter(company=self.company)[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "Procedure",
                    "attributes": {
                        "formData": {},
                        "occurrenceKind": "",
                        "deadline": datetime.now(),
                        "toDo": "",
                    },
                    "relationships": {
                        "action": {
                            "data": {
                                "type": "ServiceOrderAction",
                                "id": str(action.pk),
                            },
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # __str__ method
        content = json.loads(response.content)
        obj_created = Procedure.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

    def test_create_procedure_with_new_service_order_status(self, client):

        action = ServiceOrderAction.objects.filter(
            service_order__company=self.company, service_order__is_closed=False
        )[0]
        firm = Firm.objects.filter(company=self.company)[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "Procedure",
                    "attributes": {
                        "formData": {},
                        "occurrenceKind": "",
                        "deadline": datetime.now(),
                        "toDo": "",
                    },
                    "relationships": {
                        "action": {
                            "data": {
                                "type": "ServiceOrderAction",
                                "id": str(action.pk),
                            },
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                        "new_service_order_status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": "a32e8241-4fbc-4734-89b9-c5be6416a4a3",
                            },
                        },
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # __str__ method
        content = json.loads(response.content)
        obj_created = Procedure.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()
