import json

import pytest
from rest_framework import status

from apps.companies.models import Entity
from apps.service_orders.models import ServiceOrderResource
from helpers.dates import convent_creation_date_to_datetime
from helpers.testing.fixtures import TestBase, false_permission

from ..models import ContractItemPerformance

pytestmark = pytest.mark.django_db


class TestContractItemPerformance(TestBase):
    model = "ContractItemPerformance"

    ATTRIBUTES = {"sortString": "1.1"}

    def test_contract_item_performance_list(self, client):
        """
        Ensures we can list using the ContractItemPerformance endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 11

    def test_contract_item_performance_without_company(self, client):
        """
        Ensures calling the ContractItemPerformance endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_contract_item_performance(self, client):
        """
        Ensures a specific ContractItemPerformance can be fetched using the uuid
        """

        instance = ContractItemPerformance.objects.first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK

    def test_create_contract_item_performance(self, client):
        """
        Ensures a new ContractItemPerformance can be created using the endpoint
        """

        resource_id = ServiceOrderResource.objects.first().pk
        entity_id = Entity.objects.first().pk

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "resource": {
                            "data": {
                                "type": "ServiceOrderResource",
                                "id": str(resource_id),
                            }
                        },
                        "entity": {"data": {"type": "Entity", "id": str(entity_id)}},
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_contract_item_performance_without_company_id(self, client):
        """
        Ensures a new ContractItemPerformance cannot be created
        without a company id
        """

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_contract_item_performance_without_permission(self, client):
        """
        Ensures a new ContractItemPerformance cannot be created without
        the proper permissions
        """

        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_contract_item_performance(self, client):
        """
        Ensure a ContractItemPerformance can be updated using the endpoint
        """

        instance = ContractItemPerformance.objects.first()

        # Change amount from 2 to 3 for the update
        self.ATTRIBUTES["sortString"] = "1.2"

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(instance.pk),
                    "attributes": self.ATTRIBUTES,
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_contract_item_performance(self, client):
        """
        Ensure a ContractItemPerformance can be deleted using the endpoint
        """

        instance = ContractItemPerformance.objects.first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_filter_creation_date_range_contract_item_performance(self, client):
        """
        Ensures we can list using the ContractItemPerformance for filter entity endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&creation_date_after={}&creation_date_before={}".format(
                self.model,
                str(self.company.pk),
                "2000-01-01",
                "2030-12-30",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_filter_creation_date_before_contract_item_performance(self, client):
        """
        Ensures we can list using the ContractItemPerformance for filter entity endpoint
        and the fixture is properly listed
        """
        obj = ContractItemPerformance.objects.order_by("-created_at").first()

        dt_service_order_resource = obj.resource.creation_date.date()

        response = client.get(
            path="/{}/?company={}&creation_date_before={}".format(
                self.model,
                str(self.company.pk),
                str(dt_service_order_resource),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] > 0

        dates_is_valid = True
        for context in content["data"]:
            creation_date = context["attributes"].get("creationDate")
            date_format = convent_creation_date_to_datetime(creation_date)
            if obj.resource.creation_date < date_format:
                dates_is_valid = False
                break

        assert dates_is_valid is True

    def test_filter_creation_date_after_contract_item_performance(self, client):
        """
        Ensures we can list using the ContractItemPerformance for filter entity endpoint
        and the fixture is properly listed
        """

        obj = ContractItemPerformance.objects.order_by("created_at").first()

        dt_service_order_resource = obj.resource.creation_date.date()

        response = client.get(
            path="/{}/?company={}&creation_date_after={}".format(
                self.model,
                str(self.company.pk),
                str(dt_service_order_resource),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] > 0

        dates_is_valid = True
        for context in content["data"]:
            creation_date = context["attributes"].get("creationDate")
            date_format = convent_creation_date_to_datetime(creation_date)
            if obj.resource.creation_date > date_format:
                dates_is_valid = False
                break

        assert dates_is_valid is True
