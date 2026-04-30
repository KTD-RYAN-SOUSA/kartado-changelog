import json

import pytest
from rest_framework import status

from apps.companies.models import Firm
from apps.resources.models import ContractItemUnitPrice, ContractService
from apps.service_orders.models import AdditionalControl
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestContractService(TestBase):
    model = "ContractService"

    ATTRIBUTES = {"description": "Test description", "weight": 0.5}

    def test_contract_service_list(self, client):
        """
        Ensures we can list using the ContractService endpoint
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
        assert content["meta"]["pagination"]["count"] == 6

    def test_contract_service_without_company(self, client):
        """
        Ensures calling the ContractService endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_contract_service(self, client):
        """
        Ensures a specific ContractService can be fetched using the uuid
        """

        instance = ContractService.objects.first()

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

    def test_create_contract_service(self, client):
        """
        Ensures a new ContractService can be created using the endpoint
        """

        firm_id = Firm.objects.filter(company=self.company).first().pk
        contract_item_unit_price_id = ContractItemUnitPrice.objects.first().pk

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "firms": {"data": [{"type": "Firm", "id": str(firm_id)}]},
                        "contract_item_unit_prices": {
                            "data": [
                                {
                                    "type": "ContractItemUnitPrice",
                                    "id": str(contract_item_unit_price_id),
                                }
                            ]
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_contract_service_without_company_id(self, client):
        """
        Ensures a new ContractService cannot be created
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

    def test_create_contract_service_without_permission(self, client):
        """
        Ensures a new ContractService cannot be created without
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

    def test_update_contract_service(self, client):
        """
        Ensure a ContractService can be updated using the endpoint
        """

        instance = ContractService.objects.first()

        # Change weight from 20 to 30 for the update
        self.ATTRIBUTES["weight"] = 30

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

    def test_delete_contract_service_null(self, client):
        """
        Ensure a ContractService can be deleted using the endpoint
        """

        instance = ContractService.objects.get(
            pk="c80407ae-b267-4c3f-972e-7c56d8018f26"
        )

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

    @pytest.mark.parametrize(
        "param",
        [
            "b0db7a37-50af-4010-a893-20fb9a85ff72",
            "0e2f3da9-a75f-4d89-b14d-88b314d89b26",
            "de3950a1-cdb0-4167-a850-d78ea58bbec2",
        ],
    )
    def test_delete_contract_service_not_null(self, client, param):
        """
        Ensure that a ContractService cannot be deleted using the endpoint (because it has related contract items)
        """

        instance = ContractService.objects.get(pk=param)

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        error_message = response.data[0]["detail"].lower()

        assert (
            error_message
            == "kartado.error.contract_service.cannot_be_deleted_because_it_has_items"
        )

    def test_contract_service_filter_entity(self, client):
        """
        Ensures we can list using the ContractService for filter entity endpoint
        and the fixture is properly listed
        """
        response = client.get(
            path="/{}/?company={}&entity={}".format(
                self.model,
                str(self.company.pk),
                "052196eb-008f-4b2f-880b-7943670baa4e",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_contract_service_filter_content_type(self, client):
        """
        Ensures we can list using the ContractService for filter content_type endpoint
        and the fixture is properly listed
        """
        response = client.get(
            path="/{}/?company={}&content_type={}".format(
                self.model, str(self.company.pk), "dailyreportworker"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_contract_service_filter_additional_control(self, client):
        """
        Ensures we can list using the ContractService for filter additional_control
        endpoint and the fixture is properly listed
        """

        target_pk = str(
            AdditionalControl.objects.filter(
                service_order_resources__resource__company__pk=self.company.pk
            )
            .first()
            .pk
        )

        response = client.get(
            path="/{}/?company={}&additional_control={}".format(
                self.model,
                str(self.company.pk),
                target_pk,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_contract_service_filter_sort_string(self, client):
        """
        Ensures we can list using the ContractService for filter sort_string endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&sort_string={}".format(
                self.model,
                str(self.company.pk),
                "1.1",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_contract_service_filter_creation_date_after(self, client):
        """
        Ensures we can list using the ContractService for filter creation_date_after
        endpoint and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&creation_date_after={}".format(
                self.model,
                str(self.company.pk),
                "2000-01-01",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_contract_service_filter_creation_date_before(self, client):
        """
        Ensures we can list using the ContractService for filter creation_date_before
        endpoint and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&creation_date_before={}".format(
                self.model,
                str(self.company.pk),
                "2030-12-30",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_contract_service_filter_creation_date_range(self, client):
        """
        Ensures we can list using the ContractService for filter creation_date_range
        endpoint and the fixture is properly listed
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

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_contract_service_filter_balance_from(self, client):
        """
        Ensures we can list using the ContractService for filter balance endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&balance_from={}".format(
                self.model,
                str(self.company.pk),
                0,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_contract_service_filter_balance_to(self, client):
        """
        Ensures we can list using the ContractService for filter balance endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&balance_to={}".format(
                self.model,
                str(self.company.pk),
                6000,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_contract_service_filter_balance_range(self, client):
        """
        Ensures we can list using the ContractService for filter balance endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&balance_from={}&balance_to={}".format(
                self.model,
                str(self.company.pk),
                1,
                6000,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_contract_service_filter_unit(self, client):
        """
        Ensures we can list using the ContractItemAdministration for filter entity
        endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&unit={}".format(
                self.model,
                str(self.company.pk),
                "km",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_contract_service_items_ordering(self, client):

        response = client.post(
            path="/{}/ContractItemsOrdering/?company={}".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "item_type": "ContractItemUnitPrice",
                    "0e2f3da9-a75f-4d89-b14d-88b314d89b26": {
                        "aabda400-2527-44a0-b56f-c881ba7f4d10": 2,
                        "7e067c5e-729a-4f0e-91f5-97db2117a068": 1,
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

        contract_item_order_1 = ContractItemUnitPrice.objects.get(
            uuid="7e067c5e-729a-4f0e-91f5-97db2117a068"
        )
        contract_item_order_2 = ContractItemUnitPrice.objects.get(
            uuid="aabda400-2527-44a0-b56f-c881ba7f4d10"
        )

        assert contract_item_order_1.order == 1
        assert contract_item_order_2.order == 2

    def test_contract_service_unit_price_service_filter(self, client):
        """
        Ensures we can list using the ContractService for filter unit_price_service
        endpoint and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&unit_price_service_contracts={}".format(
                self.model,
                str(self.company.pk),
                "339fc8c2-3351-4509-af8a-aa7c519d89ee",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture items are listed
        assert content["meta"]["pagination"]["count"] == 4

        def test_contract_service_administration_service_filter(self, client):
            """
            Ensures we can list using the ContractService for filter administration
            endpoint and the fixture is properly listed
            """

            response = client.get(
                path="/{}/?company={}&administration_service_contracts={}".format(
                    self.model,
                    str(self.company.pk),
                    "339fc8c2-3351-4509-af8a-aa7c519d89ee",
                ),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
            )

            content = json.loads(response.content)

            # The call was successful
            assert response.status_code == status.HTTP_200_OK

            # The fixture items are listed
            assert content["meta"]["pagination"]["count"] == 4

        def test_contract_service_performance_service_filter(self, client):
            """
            Ensures we can list using the ContractService for filter administration
            endpoint and the fixture is properly listed
            """

            response = client.get(
                path="/{}/?company={}&aperformance_service_contracts={}".format(
                    self.model,
                    str(self.company.pk),
                    "339fc8c2-3351-4509-af8a-aa7c519d89ee",
                ),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
            )

            content = json.loads(response.content)

            # The call was successful
            assert response.status_code == status.HTTP_200_OK

            # The fixture items are listed
            assert content["meta"]["pagination"]["count"] == 4
