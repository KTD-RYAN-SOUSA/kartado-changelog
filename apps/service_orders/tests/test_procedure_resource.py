import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status

from apps.service_orders.models import (
    MeasurementBulletin,
    Procedure,
    ProcedureResource,
    ServiceOrderResource,
)
from apps.service_orders.permissions import ProcedureResourcePermissions
from apps.service_orders.serializers import (
    ProcedureResourceSerializer,
    ProcedureResourceWithoutMoneySerializer,
)
from apps.service_orders.views import ProcedureResourceView
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestProcedureResource(TestBase):
    model = "ProcedureResource"

    def test_list_procedure_resource(self, client):

        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_procedure_resource_without_queryset(self, client):

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

    def test_list_procedure_resource_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_procedure_resource(self, client):

        obj = ProcedureResource.objects.filter(
            service_order__company=self.company,
            service_order__is_closed=False,
            service_order_resource__contract__firm__is_company_team=False,
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

    def test_get_procedure_resource_without_company(self, client):

        obj = ProcedureResource.objects.filter(
            procedure__action__service_order__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_procedure_resource_without_company_uuid(self, client):

        obj = ProcedureResource.objects.filter(
            procedure__action__service_order__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, str(obj.pk), "not_uuid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_should_update_field_when_measurement_bulletin_is_removed(self, client):
        obj_id = "e80354da-e523-4f49-83db-62c53adee444"
        obj = ProcedureResource.objects.get(pk=obj_id)
        service_order_resource = obj.service_order_resource
        expected_remaining_amount = service_order_resource.remaining_amount + obj.amount
        expected_used_price = service_order_resource.used_price - obj.total_price

        obj.measurement_bulletin = None
        obj.save()
        service_order_resource.refresh_from_db()

        assert service_order_resource.remaining_amount == expected_remaining_amount
        assert service_order_resource.used_price == expected_used_price

    def test_should_update_field_when_measurement_bulletin_is_added(self, client):
        obj_id = "be7b6919-1766-46f6-8aa9-711f2c786d9a"
        mb_id = "0b02c96e-2632-42c4-afaa-0461b47c875b"
        obj = ProcedureResource.objects.get(pk=obj_id)
        mb = MeasurementBulletin.objects.get(pk=mb_id)
        service_order_resource = obj.service_order_resource
        expected_remaining_amount = service_order_resource.remaining_amount - obj.amount
        expected_used_price = service_order_resource.used_price + obj.total_price

        obj.measurement_bulletin = mb
        obj.save()
        service_order_resource.refresh_from_db()

        assert service_order_resource.remaining_amount == expected_remaining_amount
        assert service_order_resource.used_price == expected_used_price

    def test_delete_procedure_resource(self, client):

        obj = ProcedureResource.objects.filter(
            procedure__action__service_order__company=self.company,
            procedure__action__service_order__is_closed=False,
            service_order_resource__contract__firm__is_company_team=False,
        ).exclude(approval_status="APPROVED_APPROVAL")[0]

        response = client.delete(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_procedure_resource_without_permission(self, client):

        obj = ProcedureResource.objects.filter(
            approval_status="APPROVED_APPROVAL",
            procedure__action__service_order__company=self.company,
            procedure__action__service_order__is_closed=False,
            service_order_resource__contract__firm__is_company_team=False,
        )[0]

        response = client.delete(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_procedure_resource(self, client):

        procedure = Procedure.objects.filter(
            action__service_order__company=self.company,
            action__service_order__is_closed=False,
        )[0]
        resource = ServiceOrderResource.objects.filter(
            contract__firm__company=self.company
        )[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"amount": 1},
                    "relationships": {
                        "procedure": {
                            "data": {
                                "type": "Procedure",
                                "id": str(procedure.pk),
                            }
                        },
                        "serviceOrderResource": {
                            "data": {
                                "type": "ServiceOrderResource",
                                "id": str(resource.pk),
                            }
                        },
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # __str__ method
        content = json.loads(response.content)
        obj_created = ProcedureResource.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

    def test_approve_procedure_resource(self, client):
        approval_status = ["DENIED_APPROVAL", "APPROVED_APPROVAL"]

        resource = ProcedureResource.objects.filter(
            procedure__action__service_order__company=self.company,
            procedure__action__service_order__is_closed=False,
            service_order_resource__contract__firm__is_company_team=False,
        ).exclude(approval_status__in=approval_status)[0]

        response = client.post(
            path="/{}/{}/{}/?company={}".format(
                self.model, str(resource.pk), "Approval", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": {"approve": True}}},
        )

        assert response.status_code == status.HTTP_200_OK

        resource.refresh_from_db()
        assert resource.approval_status == "APPROVED_APPROVAL"
        assert str(resource.approved_by.uuid) == str(self.user.pk)

    def test_approve_errors_procedure_resource(self, client):

        resource = ProcedureResource.objects.filter(
            procedure__action__service_order__company=self.company,
            procedure__action__service_order__is_closed=False,
            measurement_bulletin__isnull=False,
            service_order_resource__contract__firm__is_company_team=False,
        )[0]

        response = client.post(
            path="/{}/{}/{}/?company={}".format(
                self.model, str(resource.pk), "Approval", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": {"approve": True}}},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = client.post(
            path="/{}/{}/{}/?company={}".format(
                self.model, str(resource.pk), "Approval", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": {}}},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_deny_procedure_resource(self, client):
        approval_status = ["DENIED_APPROVAL", "APPROVED_APPROVAL"]

        resource = ProcedureResource.objects.filter(
            procedure__action__service_order__company=self.company,
            procedure__action__service_order__is_closed=False,
            service_order_resource__contract__firm__is_company_team=False,
        ).exclude(approval_status__in=approval_status)[0]

        response = client.post(
            path="/{}/{}/{}/?company={}".format(
                self.model, str(resource.pk), "Approval", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": {"approve": False}}},
        )

        assert response.status_code == status.HTTP_200_OK

        resource.refresh_from_db()
        assert resource.approval_status == "DENIED_APPROVAL"
        assert str(resource.approved_by.uuid) == str(self.user.pk)

    def test_firm_filter(self, client):
        firm_uuid = "eb093034-7f05-4d93-8a7d-cdf8ee04923d"

        response = client.get(
            path="/{}/?company={}&firm={}&page_size=1".format(
                self.model, str(self.company.pk), firm_uuid
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 3

    def test_lot_filter(self, client):

        response = client.get(
            path="/{}/?company={}&lot={}&page_size=1".format(
                self.model, str(self.company.pk), "1"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_active_filter(self, client):
        response = client.get(
            path="/{}/?company={}&active={}&page_size=1".format(
                self.model, str(self.company.pk), "1,2"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 2


class TestProcedureResourcePermissions:
    """Testes específicos para o método get_company_id da classe ProcedureResourcePermissions"""

    def setup_method(self):
        self.permissions = ProcedureResourcePermissions()

    def test_get_company_id_create_with_editable_reporting(self):
        """Testa a criação de ProcedureResource quando um reporting editável é fornecido na requisição"""
        # Mock do request com reporting
        mock_request = MagicMock()
        mock_request.data = {
            "reporting": {"id": str(uuid.uuid4())},
            "procedure": {"id": str(uuid.uuid4())},
        }

        # Mock do Reporting que existe e é editável
        mock_reporting = MagicMock()
        mock_reporting.editable = True

        with patch(
            "apps.service_orders.permissions.Reporting.objects.get",
            return_value=mock_reporting,
        ):
            with patch(
                "apps.service_orders.permissions.Procedure.objects.get"
            ) as mock_procedure_get:
                mock_procedure = MagicMock()
                mock_procedure.action.service_order.uuid = uuid.uuid4()
                mock_procedure_get.return_value = mock_procedure

                self.permissions.get_company_id("create", mock_request)

                # Verifica que o service_order foi preenchido automaticamente
                assert mock_request.data["service_order"]["id"] == str(
                    mock_procedure.action.service_order.uuid
                )

    def test_get_company_id_create_with_non_editable_reporting(self):
        """Testa que uma exceção é lançada quando o reporting não é editável"""
        from rest_framework_json_api import serializers

        # Mock do request com reporting
        mock_request = MagicMock()
        mock_request.data = {
            "reporting": {"id": str(uuid.uuid4())},
        }

        # Mock do Reporting que existe mas não é editável
        mock_reporting = MagicMock()
        mock_reporting.editable = False

        with patch(
            "apps.service_orders.permissions.Reporting.objects.get",
            return_value=mock_reporting,
        ):
            with pytest.raises(serializers.ValidationError) as exc_info:
                self.permissions.get_company_id("create", mock_request)

            # Verifica que a exceção correta foi lançada
            assert "kartado.error.reporting.not_editable" in str(exc_info.value)

    def test_get_company_id_create_using_service_order_resource(self):
        """Testa a obtenção do company_id através do service_order_resource quando não há service_order nem procedure"""
        # Mock do request sem service_order nem procedure, mas com service_order_resource
        mock_request = MagicMock()
        mock_service_order_resource_id = str(uuid.uuid4())
        mock_request.data = {
            "service_order_resource": {"id": mock_service_order_resource_id}
        }

        # Mock do ServiceOrderResource
        mock_service_order_resource = MagicMock()
        mock_company_id = uuid.uuid4()
        mock_service_order_resource.resource.company_id = mock_company_id

        with patch(
            "apps.service_orders.permissions.ServiceOrderResource.objects.get",
            return_value=mock_service_order_resource,
        ) as mock_get:
            result = self.permissions.get_company_id("create", mock_request)

            # Verifica que o método foi chamado com o ID correto e retornou o company_id esperado
            mock_get.assert_called_once_with(
                pk=uuid.UUID(mock_service_order_resource_id)
            )
            assert result == mock_company_id

    def test_get_company_id_create_handles_service_order_resource_not_found(self):
        """Testa o tratamento de erro quando o ServiceOrderResource não é encontrado"""
        # Mock do request com service_order_resource
        mock_request = MagicMock()
        mock_request.data = {"service_order_resource": {"id": str(uuid.uuid4())}}

        # Mock que lança exceção
        with patch(
            "apps.service_orders.permissions.ServiceOrderResource.objects.get",
            side_effect=Exception("Test exception"),
        ):
            result = self.permissions.get_company_id("create", mock_request)

            # Verifica que retorna False quando há exceção
            assert result is False

    def test_get_company_id_create_returns_company_from_service_order_resource(self):
        """Testa que o company_id é corretamente extraído do resource associado ao service_order_resource"""
        # Mock do request com service_order_resource
        mock_request = MagicMock()
        mock_service_order_resource_id = str(uuid.uuid4())
        mock_request.data = {
            "service_order_resource": {"id": mock_service_order_resource_id}
        }

        # Mock do ServiceOrderResource com company_id específico
        mock_service_order_resource = MagicMock()
        expected_company_id = uuid.uuid4()
        mock_service_order_resource.resource.company_id = expected_company_id

        with patch(
            "apps.service_orders.permissions.ServiceOrderResource.objects.get",
            return_value=mock_service_order_resource,
        ):
            result = self.permissions.get_company_id("create", mock_request)

            # Verifica que retorna o company_id correto
            assert result == expected_company_id

    def test_get_company_id_create_handles_reporting_not_found(self):
        """Testa o tratamento de erro quando o Reporting especificado não existe"""
        from rest_framework_json_api import serializers

        from apps.reportings.models import Reporting

        # Mock do request com reporting
        mock_request = MagicMock()
        mock_request.data = {
            "reporting": {"id": str(uuid.uuid4())},
        }

        # Mock que lança Reporting.DoesNotExist
        with patch(
            "apps.service_orders.permissions.Reporting.objects.get",
            side_effect=Reporting.DoesNotExist("Not found"),
        ):
            with pytest.raises(serializers.ValidationError) as exc_info:
                self.permissions.get_company_id("create", mock_request)

            # Verifica que a exceção correta foi lançada
            assert "kartado.error.reporting.not_found" in str(exc_info.value)

    def test_get_company_id_create_handles_reporting_database_error(self):
        """Testa o tratamento de erros gerais de banco de dados ao buscar o Reporting"""
        # Mock do request com reporting
        mock_request = MagicMock()
        mock_request.data = {
            "reporting": {"id": str(uuid.uuid4())},
        }

        # Mock que lança exceção geral
        with patch(
            "apps.service_orders.permissions.Reporting.objects.get",
            side_effect=Exception("General error"),
        ):
            result = self.permissions.get_company_id("create", mock_request)

            # Verifica que retorna False quando há erro de banco de dados
            assert result is False


class TestProcedureResourceView:
    """Testes específicos para a view ProcedureResourceView"""

    def setup_method(self):
        self.view = ProcedureResourceView()

    def test_get_serializer_class_with_money_permission(self):
        """Testa que retorna ProcedureResourceSerializer quando usuário tem permissão para ver valores monetários"""
        # Mock das permissions com permissão para ver dinheiro
        mock_permissions = MagicMock()
        mock_permissions.has_permission.return_value = True

        # Configura a view com as permissions mockadas
        self.view.permissions = mock_permissions

        # Chama o método e verifica o resultado
        result = self.view.get_serializer_class()

        # Verifica que retorna o serializer com dinheiro
        assert result == ProcedureResourceSerializer
        # Verifica que a permissão foi checada corretamente
        mock_permissions.has_permission.assert_called_once_with("can_view_money")


class TestProcedureResourceSerializers:
    """Testes específicos para os serializers ProcedureResourceSerializer e ProcedureResourceWithoutMoneySerializer"""

    def setup_method(self):
        self.without_money_serializer = ProcedureResourceWithoutMoneySerializer()
        self.with_money_serializer = ProcedureResourceSerializer()

    def test_is_closed_so_with_service_order_closed(self):
        """Testa que is_closed_so retorna True quando o service_order está fechado"""
        # Mock do ProcedureResource com service_order fechado
        mock_procedure_resource = MagicMock()
        mock_service_order = MagicMock()
        mock_service_order.is_closed = True
        mock_procedure_resource.service_order = mock_service_order

        # Chama o método e verifica o resultado
        result = self.without_money_serializer.is_closed_so(mock_procedure_resource)

        # Verifica que retorna True quando service_order está fechado
        assert result is True

    def test_is_closed_so_with_service_order_open(self):
        """Testa que is_closed_so retorna False quando o service_order está aberto"""
        # Mock do ProcedureResource com service_order aberto
        mock_procedure_resource = MagicMock()
        mock_service_order = MagicMock()
        mock_service_order.is_closed = False
        mock_procedure_resource.service_order = mock_service_order

        # Chama o método e verifica o resultado
        result = self.without_money_serializer.is_closed_so(mock_procedure_resource)

        # Verifica que retorna False quando service_order está aberto
        assert result is False

    def test_is_closed_so_without_service_order(self):
        """Testa que is_closed_so retorna None quando não há service_order"""
        # Mock do ProcedureResource sem service_order
        mock_procedure_resource = MagicMock()
        mock_procedure_resource.service_order = None

        # Chama o método e verifica o resultado
        result = self.without_money_serializer.is_closed_so(mock_procedure_resource)

        # Verifica que retorna None quando não há service_order
        assert result is None

    def test_get_history_with_history_records(self):
        """Testa que get_history retorna lista de históricos formatados corretamente"""
        # Mock do ProcedureResource com histórico
        mock_procedure_resource = MagicMock()

        # Mock dos registros de histórico
        mock_history_1 = MagicMock()
        mock_history_1.__dict__ = {
            "_state": "some_state",
            "id": 1,
            "amount": 10.5,
            "created_at": "2023-01-01",
            "history_change_reason": "Criação inicial",
        }

        mock_history_2 = MagicMock()
        mock_history_2.__dict__ = {
            "_state": "some_state",
            "id": 2,
            "amount": 15.0,
            "created_at": "2023-01-02",
            "history_change_reason": "Atualização de quantidade",
        }

        mock_procedure_resource.history_procedure_resources.all.return_value = [
            mock_history_1,
            mock_history_2,
        ]

        # Chama o método e verifica o resultado
        result = self.with_money_serializer.get_history(mock_procedure_resource)

        # Verifica que retorna lista com históricos formatados
        expected_result = [
            {
                "id": 1,
                "amount": 10.5,
                "created_at": "2023-01-01",
                "history_change_reason": "Criação inicial",
            },
            {
                "id": 2,
                "amount": 15.0,
                "created_at": "2023-01-02",
                "history_change_reason": "Atualização de quantidade",
            },
        ]

        assert result == expected_result
        # Verifica que o campo _state foi removido
        for history_dict in result:
            assert "_state" not in history_dict

    def test_get_history_without_history_records(self):
        """Testa que get_history retorna lista vazia quando não há histórico"""
        # Mock do ProcedureResource sem histórico
        mock_procedure_resource = MagicMock()
        mock_procedure_resource.history.all.return_value = []

        # Chama o método e verifica o resultado
        result = self.with_money_serializer.get_history(mock_procedure_resource)

        # Verifica que retorna lista vazia
        assert result == []
