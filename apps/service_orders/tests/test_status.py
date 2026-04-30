import json
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework_json_api import serializers

from apps.service_orders.filters import ServiceOrderActionStatusFilter
from apps.service_orders.models import (
    ServiceOrder,
    ServiceOrderAction,
    ServiceOrderActionStatus,
    ServiceOrderActionStatusSpecs,
)
from apps.service_orders.serializers import ServiceOrderActionStatusSerializer
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestServiceOrderActionStatus(TestBase):
    model = "ServiceOrderActionStatus"

    def test_list_status(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_status_without_queryset(self, client):

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

    def test_list_status_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_status(self, client):

        obj = ServiceOrderActionStatus.objects.filter(companies=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_status_without_company(self, client):

        obj = ServiceOrderActionStatus.objects.filter(companies=self.company).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_status_without_company_uuid(self, client):

        obj = ServiceOrderActionStatus.objects.filter(companies=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, str(obj.pk), "not_uuid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_status(self, client):

        obj = ServiceOrderActionStatus.objects.filter(companies=self.company).first()

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

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_status(self, client):
        # Create status that is not being used
        obj = ServiceOrderActionStatus.objects.create(
            name="Status not used",
        )
        # Add to company
        ServiceOrderActionStatusSpecs.objects.create(
            status=obj,
            company=self.company,
            order=0,
        )

        response = client.delete(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_status_fail(self, client):
        # Get a status
        action_status = ServiceOrderActionStatus.objects.filter(
            companies=self.company
        ).first()
        # Creact ServiceOrderAction with status
        ServiceOrderAction.objects.create(
            service_order=ServiceOrder.objects.filter(company=self.company).first(),
            name="Test",
            service_order_action_status=action_status,
        )

        response = client.delete(
            path="/{}/{}/".format(self.model, str(action_status.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object is not deleted
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert ServiceOrderActionStatus.objects.filter(pk=action_status.pk).exists()

    def test_create_status_companies_list(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "color": "#FF0000",
                        "order": 0,
                    },
                    "relationships": {
                        "companies": {
                            "data": [{"type": "Company", "id": str(self.company.pk)}]
                        }
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = ServiceOrderActionStatus.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_status_companies_single(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "color": "#FF0000",
                        "order": 0,
                    },
                    "relationships": {
                        "companies": {
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
        obj_created = ServiceOrderActionStatus.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_status_without_permission(self, client):

        false_permission(self.user, self.company, self.model)

        # Not permission and list
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "order": 1000,
                        "color": "#FF0000",
                    },
                    "relationships": {
                        "companies": {
                            "data": [{"type": "Company", "id": str(self.company.pk)}]
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Not permission and not list
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "order": 1000,
                        "color": "#FF0000",
                    },
                    "relationships": {
                        "companies": {
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

        # Not companies
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "order": 1000,
                        "color": "#FF0000",
                    },
                    "relationships": {},
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Not id and list
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "order": 1000,
                        "color": "#FF0000",
                    },
                    "relationships": {
                        "companies": {
                            "data": [
                                {
                                    "type": "Company",
                                    "not_id": str(self.company.pk),
                                }
                            ]
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Not id and not list
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "order": 1000,
                        "color": "#FF0000",
                    },
                    "relationships": {
                        "companies": {
                            "data": {
                                "type": "Company",
                                "not_id": str(self.company.pk),
                            }
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_with_is_final_true_land(self):
        # Create your test data with kind equal to "LAND_SERVICE_CONCLUSION"
        test_data = {
            "name": "Test Status",
            "kind": "LAND_SERVICE_CONCLUSION",
            "companies": [{"type": "Company", "id": str(self.company.pk)}],
            "order": 0,
        }

        # Create an instance in the serializer
        serializer = ServiceOrderActionStatusSerializer(data=test_data)

        # Check if the serializer is valid
        assert serializer.is_valid()

        # Create the status by calling the serializer's create method
        status = serializer.save()

        # Check if the is_final field is True
        assert status.is_final

    def test_create_with_is_final_true_environmental(self):
        # Create your test data with kind equal to "ENVIRONMENTAL_SERVICE_CONCLUSION"
        test_data = {
            "name": "Test Status",
            "kind": "ENVIRONMENTAL_SERVICE_CONCLUSION",
            "companies": [{"type": "Company", "id": str(self.company.pk)}],
            "order": 0,
        }

        # Create an instance in the serializer
        serializer = ServiceOrderActionStatusSerializer(data=test_data)

        # Check if the serializer is valid
        assert serializer.is_valid()

        # Create the status by calling the serializer's create method
        status = serializer.save()

        # Check if the is_final field is True
        assert status.is_final


class TestServiceOrderActionStatusFilter:
    """Testes específicos para o filtro ServiceOrderActionStatusFilter"""

    def setup_method(self):
        self.filter_class = ServiceOrderActionStatusFilter

    def test_get_only_executed_reporting_status_without_company(self):
        """Testa que retorna queryset inalterado quando não há company nos dados"""
        # Mock do queryset
        mock_queryset = MagicMock()

        # Mock do filtro sem company nos dados
        filter_instance = self.filter_class()
        filter_instance.data = {}  # Sem company

        # Chama o método
        result = filter_instance.get_only_executed_reporting_status(
            mock_queryset, "test", True
        )

        # Verifica que retorna o queryset original
        assert result == mock_queryset

    def test_get_only_executed_reporting_status_with_invalid_metadata(self):
        """Testa que lança ValidationError quando executed_status_order não é um inteiro"""
        # Mock do queryset
        mock_queryset = MagicMock()

        # Mock da company com metadata inválido
        mock_company = MagicMock()
        mock_company.metadata = {"executed_status_order": "not_an_int"}

        # Mock do filtro com company nos dados
        filter_instance = self.filter_class()
        filter_instance.data = {"company": "test-uuid"}

        with patch(
            "apps.service_orders.filters.Company.objects.get", return_value=mock_company
        ):
            with patch(
                "apps.service_orders.filters.get_obj_from_path",
                return_value="not_an_int",
            ):
                with pytest.raises(serializers.ValidationError) as exc_info:
                    filter_instance.get_only_executed_reporting_status(
                        mock_queryset, "test", True
                    )

                # Verifica a mensagem de erro
                assert "Unidade não possui status de execução configurado" in str(
                    exc_info.value
                )

    def test_get_only_executed_reporting_status_with_missing_metadata(self):
        """Testa que lança ValidationError quando executed_status_order não existe"""
        # Mock do queryset
        mock_queryset = MagicMock()

        # Mock da company com metadata sem executed_status_order
        mock_company = MagicMock()
        mock_company.metadata = {}

        # Mock do filtro com company nos dados
        filter_instance = self.filter_class()
        filter_instance.data = {"company": "test-uuid"}

        with patch(
            "apps.service_orders.filters.Company.objects.get", return_value=mock_company
        ):
            with patch(
                "apps.service_orders.filters.get_obj_from_path", return_value=None
            ):
                with pytest.raises(serializers.ValidationError) as exc_info:
                    filter_instance.get_only_executed_reporting_status(
                        mock_queryset, "test", True
                    )

                # Verifica a mensagem de erro
                assert "Unidade não possui status de execução configurado" in str(
                    exc_info.value
                )

    def test_get_only_executed_reporting_status_true_value(self):
        """Testa filtro com value=True (status executados)"""
        # Mock do queryset
        mock_queryset = MagicMock()
        mock_filtered_queryset = MagicMock()
        mock_queryset.filter.return_value.distinct.return_value = mock_filtered_queryset

        # Mock da company com metadata válido
        mock_company = MagicMock()
        executed_status_order = 5

        # Mock do filtro com company nos dados
        filter_instance = self.filter_class()
        filter_instance.data = {"company": "test-uuid"}

        with patch(
            "apps.service_orders.filters.Company.objects.get", return_value=mock_company
        ):
            with patch(
                "apps.service_orders.filters.get_obj_from_path",
                return_value=executed_status_order,
            ):
                result = filter_instance.get_only_executed_reporting_status(
                    mock_queryset, "test", True
                )

                # Verifica que o filtro foi aplicado corretamente
                expected_filter = {
                    "companies": mock_company,
                    "kind": "REPORTING_STATUS",
                    "status_specs__order__gte": executed_status_order,
                }
                mock_queryset.filter.assert_called_once_with(**expected_filter)
                assert result == mock_filtered_queryset

    def test_get_only_executed_reporting_status_false_value(self):
        """Testa filtro com value=False (status não executados)"""
        # Mock do queryset
        mock_queryset = MagicMock()
        mock_filtered_queryset = MagicMock()
        mock_queryset.filter.return_value.distinct.return_value = mock_filtered_queryset

        # Mock da company com metadata válido
        mock_company = MagicMock()
        executed_status_order = 3

        # Mock do filtro com company nos dados
        filter_instance = self.filter_class()
        filter_instance.data = {"company": "test-uuid"}

        with patch(
            "apps.service_orders.filters.Company.objects.get", return_value=mock_company
        ):
            with patch(
                "apps.service_orders.filters.get_obj_from_path",
                return_value=executed_status_order,
            ):
                result = filter_instance.get_only_executed_reporting_status(
                    mock_queryset, "test", False
                )

                # Verifica que o filtro foi aplicado corretamente
                expected_filter = {
                    "companies": mock_company,
                    "kind": "REPORTING_STATUS",
                    "status_specs__order__lt": executed_status_order,
                }
                mock_queryset.filter.assert_called_once_with(**expected_filter)
                assert result == mock_filtered_queryset

    def test_get_only_executed_reporting_status_with_zero_order(self):
        """Testa filtro quando executed_status_order é zero"""
        # Mock do queryset
        mock_queryset = MagicMock()
        mock_filtered_queryset = MagicMock()
        mock_queryset.filter.return_value.distinct.return_value = mock_filtered_queryset

        # Mock da company com metadata válido (ordem zero)
        mock_company = MagicMock()
        executed_status_order = 0

        # Mock do filtro com company nos dados
        filter_instance = self.filter_class()
        filter_instance.data = {"company": "test-uuid"}

        with patch(
            "apps.service_orders.filters.Company.objects.get", return_value=mock_company
        ):
            with patch(
                "apps.service_orders.filters.get_obj_from_path",
                return_value=executed_status_order,
            ):
                result = filter_instance.get_only_executed_reporting_status(
                    mock_queryset, "test", True
                )

                # Verifica que o filtro foi aplicado corretamente mesmo com ordem zero
                expected_filter = {
                    "companies": mock_company,
                    "kind": "REPORTING_STATUS",
                    "status_specs__order__gte": executed_status_order,
                }
                mock_queryset.filter.assert_called_once_with(**expected_filter)
                assert result == mock_filtered_queryset
