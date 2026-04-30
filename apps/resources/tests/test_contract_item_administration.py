# TODO: change to the new item
import json

import pytest
from django.contrib.contenttypes.models import ContentType
from rest_framework import status

from apps.companies.models import Entity
from apps.daily_reports.models import DailyReportVehicle
from apps.service_orders.models import AdditionalControl, ServiceOrderResource
from helpers.dates import convent_creation_date_to_datetime
from helpers.signals import DisableSignals
from helpers.testing.fixtures import TestBase, false_permission

from ..models import ContractItemAdministration

pytestmark = pytest.mark.django_db


class TestContractItemAdministration(TestBase):
    model = "ContractItemAdministration"

    ATTRIBUTES = {"sortString": "1.1"}

    def test_contract_item_administration_list(self, client):
        """
        Ensures we can list using the ContractItemAdministration endpoint
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
        assert content["meta"]["pagination"]["count"] > 0

    def test_contract_item_administration_without_company(self, client):
        """
        Ensures calling the ContractItemAdministration endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_contract_item_administration(self, client):
        """
        Ensures a specific ContractItemAdministration can be fetched using the uuid
        """

        instance = ContractItemAdministration.objects.first()

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

    def test_create_contract_item_administration(self, client):
        """
        Ensures a new ContractItemAdministration can be created using the endpoint
        """

        resource_id = ServiceOrderResource.objects.first().pk
        entity_id = Entity.objects.first().pk
        content_type_id = (
            ContentType.objects.filter(model="dailyreportworker").first().pk
        )

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
                        "contentType": {
                            "data": {
                                "type": "ContentType",
                                "id": str(content_type_id),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_contract_item_administration_without_company_id(self, client):
        """
        Ensures a new ContractItemAdministration cannot be created
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

    def test_create_contract_item_administration_without_permission(self, client):
        """
        Ensures a new ContractItemAdministration cannot be created without
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

    def test_update_contract_item_administration(self, client):
        """
        Ensure a ContractItemAdministration can be updated using the endpoint
        """

        instance = ContractItemAdministration.objects.first()

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

    def test_delete_contract_item_administration(self, client):
        """
        Ensure a ContractItemAdministration can be deleted using the endpoint
        """

        instance = ContractItemAdministration.objects.first()

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

    def test_should_sort_by_resource_name(self, client):
        """
        Ensures we can sort by resource name
        """

        response = client.get(
            path="/{}/?company={}&page_size=1&sort=resource_name".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        id = content["data"][0]["id"]
        first_adm_contract = ContractItemAdministration.objects.get(pk=id)
        assert first_adm_contract.resource.resource.name == "ART"

    def test_should_sort_by_description(self, client):
        """
        Ensures we can sort by description
        """

        response = client.get(
            path="/{}/?company={}&page_size=1&sort=descriptions".format(
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
        id = content["data"][0]["id"]
        first_adm_contract = ContractItemAdministration.objects.get(pk=id)
        assert first_adm_contract.resource.resource.name == "ART"
        assert content["meta"]["pagination"]["count"] > 0

    def test_field_values_item_administration(self, client):
        """
        Ensures expected_amount field is correct
        """
        item_administration_uuid = "fdbc54e8-ab5a-4520-97ce-d299fd00ec0f"
        response = client.get(
            path="/{}/?company={}&uuid={}".format(
                self.model, str(self.company.pk), item_administration_uuid
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        expected_amount = 4.08

        assert response.data["results"][0]["expected_amount"] == expected_amount

    def test_filter_additional_control_contract_item_administration(self, client):
        """
        Ensures we can list using the ContractItemAdministration for filter entity endpoint
        and the fixture is properly listed
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

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_filter_sort_string_contract_item_administration(self, client):
        """
        Ensures we can list using the ContractItemAdministration for filter entity endpoint
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

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_filter_creation_date_range_contract_item_administration(self, client):
        """
        Ensures we can list using the ContractItemAdministration for filter entity endpoint
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

    def test_filter_creation_date_before_contract_item_administration(self, client):
        """
        Ensures we can list using the ContractItemAdministration for filter entity endpoint
        and the fixture is properly listed
        """
        obj = ContractItemAdministration.objects.order_by("-created_at").first()

        dt_obj = obj.resource.creation_date.date()

        response = client.get(
            path="/{}/?company={}&creation_date_before={}".format(
                self.model,
                str(self.company.pk),
                str(dt_obj),
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

    def test_filter_creation_date_after_contract_item_administration(self, client):
        """
        Ensures we can list using the ContractItemAdministration for filter entity endpoint
        and the fixture is properly listed
        """

        obj = ContractItemAdministration.objects.order_by("created_at").first()

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

    def test_contract_item_administration_calc_balance_total_items(self, client):
        """
        Ensures we can list using the ContractItemAdministration for filter balance endpoint
        and the fixture is properly listed
        """
        instance = ContractItemAdministration.objects.filter(
            resource__unit_price=3.0,
            resource__remaining_amount=49.0,
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        extractive_balance = instance.balance

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        assert response.data["balance"] == extractive_balance

    def test_contract_item_administration_balance_from(self, client):
        """
        Ensures we can list using the ContractItemAdministration for filter balance endpoint
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

    def test_contract_item_administration_balance_to(self, client):
        """
        Ensures we can list using the ContractItemAdministration for filter balance endpoint
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

    def test_contract_item_administration_balance_range(self, client):
        """
        Ensures we can list using the ContractItemAdministration for filter balance endpoint
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

    def test_contract_service_filter_content_type_get_dailyreportworker(self, client):
        """
        Ensures we can list using the ContractItemAdministration for filter content_type endpoint
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

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_filter_unit_contract_item_administration(self, client):
        """
        Ensures we can list using the ContractItemAdministration for filter entity endpoint
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

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] > 0

    def test_deletion_error(self, client):
        instance = ContractItemAdministration.objects.first()

        vehicle = DailyReportVehicle.objects.first()

        vehicle.contract_item_administration = instance

        with DisableSignals():
            vehicle.save()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # Object was not deleted
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            content["errors"][0]["detail"]
            == "kartado.error.contract_item_in_use_cannot_be_deleted"
        )
