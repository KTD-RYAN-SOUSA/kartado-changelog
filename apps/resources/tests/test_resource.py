import json

import pytest
from rest_framework import status

from apps.resources.models import Resource
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestResource(TestBase):
    model = "Resource"

    def test_list_resource(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_resource_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_resource(self, client):

        resource = Resource.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(resource.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_resource(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test", "total_amount": 1},
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = Resource.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_resource_without_company_id(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test", "total_amount": 1},
                    "relationships": {"company": {"data": {"type": "Company"}}},
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_resource_without_permission(self, client):

        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test", "total_amount": 1},
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_resource(self, client):

        resource = Resource.objects.filter(company=self.company).first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(resource.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(resource.pk),
                    "attributes": {"name": "test_update"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_resource(self, client):

        resource = Resource.objects.filter(company=self.company).first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(resource.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_should_return_resource_extra_fields(self, client):

        """
        This endpoint should return "contractServiceDescription" and "remainingAmount" atributes
        """

        resource = Resource.objects.filter(
            resource_service_orders__resource_contract_unit_price_items__isnull=False,
            resource_service_orders__resource_contract_administration_items__isnull=True,
            resource_service_orders__resource_contract_performance_items__isnull=True,
        ).first()
        response = client.get(
            path="/{}/?company={}&page_size=1&uuid={}&only_unit_price_contracts=true&show_unit_price_contracts=true".format(
                self.model, str(self.company.pk), str(resource.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)
        attributes = content["data"][0]["attributes"]
        assert "contractServiceDescription" in attributes
        assert "remainingAmount" in attributes
        assert "order" in attributes
        assert "sortString" in attributes
        assert response.status_code == status.HTTP_200_OK

    def test_contract_serializer_with_money_permission(self, client):
        from unittest.mock import Mock

        from apps.resources.serializers import ContractSerializer
        from apps.resources.views import ContractView

        view = ContractView()

        mock_permissions = Mock()
        mock_permissions.has_permission.return_value = True
        view.permissions = mock_permissions

        serializer_class = view.get_serializer_class()

        assert serializer_class == ContractSerializer
        mock_permissions.has_permission.assert_called_once_with("can_view_money")

    def test_contract_serializer_without_money_permission(self, client):

        from unittest.mock import Mock

        from apps.resources.serializers import ContractWithoutMoneySerializer
        from apps.resources.views import ContractView

        # Create a mock view instance
        view = ContractView()

        # Mock permissions with can_view_money = False
        mock_permissions = Mock()
        mock_permissions.has_permission.return_value = False
        view.permissions = mock_permissions

        # Call get_serializer_class
        serializer_class = view.get_serializer_class()

        # Assert that ContractWithoutMoneySerializer is returned
        assert serializer_class == ContractWithoutMoneySerializer
        mock_permissions.has_permission.assert_called_once_with("can_view_money")

    def test_contract_serializer_without_permissions_object(self, client):

        from apps.resources.serializers import ContractWithoutMoneySerializer
        from apps.resources.views import ContractView

        view = ContractView()
        view.permissions = None

        serializer_class = view.get_serializer_class()

        assert serializer_class == ContractWithoutMoneySerializer
