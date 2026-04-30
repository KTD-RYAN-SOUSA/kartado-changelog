import json

import pytest
from rest_framework import status

from apps.resources.models import Contract, ContractAdditive
from helpers.apps.contract_utils import get_total_price
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestContractAdditive(TestBase):
    model = "ContractAdditive"

    def test_list_contract_additive(self, client):
        """Test listing ContractAdditives with company filter"""

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)

        assert content["meta"]["pagination"]["count"] == 2

    def test_list_contract_additive_without_company_filter(self, client):
        """Test listing ContractAdditives without company filter should return 403"""

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_contract_additive(self, client):
        """Test retrieving a specific ContractAdditive"""

        obj = ContractAdditive.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_contract_additive(self, client):
        """Test creating a ContractAdditive"""

        contract = Contract.objects.get(uuid="339fc8c2-3351-4509-af8a-aa7c519d89ee")
        old_total_price = get_total_price(contract)

        percentage = 10.0

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "description": "Test additive description",
                        "notes": "Test notes",
                        "additional_percentage": percentage,
                        "old_price": 1000.0,
                        "new_price": 1100.0,
                    },
                    "relationships": {
                        "contract": {
                            "data": {"type": "Contract", "id": str(contract.pk)}
                        },
                        "company": {
                            "data": {"type": "Company", "id": str(self.company.pk)}
                        },
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        # Verify object was created with correct data
        content = json.loads(response.content)
        obj_created = ContractAdditive.objects.get(pk=content["data"]["id"])
        assert obj_created.number != ""
        assert obj_created.description == "Test additive description"
        assert obj_created.additional_percentage == 10.0
        assert obj_created.created_by == self.user
        assert obj_created.company == self.company
        assert obj_created.error is False
        assert obj_created.done is True

        contract.refresh_from_db()
        assert contract.total_price == round(
            old_total_price * (1 + percentage / 100), 4
        )

    def test_update_contract_additive_not_allowed(self, client):
        """Test that UPDATE method is not allowed on ContractAdditive"""

        obj = ContractAdditive.objects.filter(company=self.company).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"number": "UPDATED"},
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_contract_additive_not_allowed(self, client):
        """Test that DELETE method is not allowed on ContractAdditive"""

        obj = ContractAdditive.objects.filter(company=self.company).first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_contract_additive_with_filters(self, client):
        """Test listing ContractAdditives with various filters"""

        # Filter by contract
        response = client.get(
            path="/{}/?company={}&number={}".format(
                self.model, str(self.company.pk), "1"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)

        assert content["meta"]["pagination"]["count"] == 1
