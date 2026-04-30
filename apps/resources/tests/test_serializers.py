from unittest.mock import Mock, patch

import pytest

from apps.resources.models import Contract
from apps.resources.serializers import BaseContractItemSerializer, ContractSerializer

pytestmark = pytest.mark.django_db


class TestContractSerializer:
    def test_contract_serializer_get_provisioned_price_with_data(self):
        spend_schedule_data = {
            "janeiro": 1000.50,
            "fevereiro": 2500.75,
            "março": 1800.25,
        }
        contract = Contract.objects.create(
            name="Contrato com Schedule",
            contract_start="2024-01-01",
            contract_end="2025-01-01",
            spend_schedule=spend_schedule_data,
        )

        context = {"firms": []}
        serializer = ContractSerializer(contract, context=context)
        provisioned_price = serializer.get_provisioned_price(contract)
        expected_total = sum(spend_schedule_data.values())

        assert provisioned_price == expected_total

        data = serializer.data
        assert "provisioned_price" in data
        assert data["provisioned_price"] == expected_total

    def test_contract_serializer_get_provisioned_price_empty_data(self):
        contract_empty = Contract.objects.create(
            name="Contrato Schedule Vazio",
            contract_start="2024-01-01",
            contract_end="2025-01-01",
            spend_schedule={},
        )

        contract_none = Contract.objects.create(
            name="Contrato Schedule None",
            contract_start="2024-01-01",
            contract_end="2025-01-01",
            spend_schedule=None,
        )

        context = {"firms": []}
        serializer_empty = ContractSerializer(contract_empty, context=context)
        serializer_none = ContractSerializer(contract_none, context=context)

        assert serializer_empty.get_provisioned_price(contract_empty) == 0
        assert serializer_none.get_provisioned_price(contract_none) == 0

        data_empty = serializer_empty.data
        data_none = serializer_none.data

        assert "provisioned_price" in data_empty
        assert "provisioned_price" in data_none
        assert data_empty["provisioned_price"] == 0
        assert data_none["provisioned_price"] == 0


class TestBaseContractItemSerializer:
    def test_get_pending_price_with_no_resource(self):
        mock_obj = Mock()
        mock_obj.resource = None

        with patch(
            "apps.resources.serializers.get_board_item_relation_qs", return_value=None
        ):
            serializer = BaseContractItemSerializer()
            result = serializer.get_pending_price(mock_obj)

            assert result is None

    def test_get_pending_price_exception_handling(self):
        from apps.service_orders.const import resource_approval_status

        mock_obj = Mock()
        mock_resource = Mock()
        mock_obj.resource = mock_resource

        mock_instance = Mock()
        mock_instance.approval_status = resource_approval_status.WAITING_APPROVAL
        mock_instance.total_price = "invalid_price"

        mock_resource.serviceorderresource_procedures.all.return_value = [mock_instance]

        with patch(
            "apps.resources.serializers.get_board_item_relation_qs", return_value=None
        ):
            serializer = BaseContractItemSerializer()
            result = serializer.get_pending_price(mock_obj)

            assert result == 0.0

    def test_get_pending_price_with_board_item_relation_qs(self):
        from apps.service_orders.const import resource_approval_status

        mock_obj = Mock()
        mock_obj.resource = Mock()

        mock_board_item = Mock()
        mock_board_item.approval_status = resource_approval_status.WAITING_APPROVAL
        mock_board_item.total_price = 100.0

        with patch(
            "apps.resources.serializers.get_board_item_relation_qs",
            return_value=[mock_board_item],
        ):
            serializer = BaseContractItemSerializer()
            result = serializer.get_pending_price(mock_obj)

            assert result == 100.0

    def test_get_pending_price_with_resource_procedures(self):
        from apps.service_orders.const import resource_approval_status

        mock_obj = Mock()
        mock_resource = Mock()
        mock_obj.resource = mock_resource

        mock_procedure = Mock()
        mock_procedure.approval_status = resource_approval_status.WAITING_APPROVAL
        mock_procedure.total_price = 250.0

        mock_resource.serviceorderresource_procedures.all.return_value = [
            mock_procedure
        ]

        with patch(
            "apps.resources.serializers.get_board_item_relation_qs", return_value=None
        ):
            serializer = BaseContractItemSerializer()
            result = serializer.get_pending_price(mock_obj)

            assert result == 250.0

    def test_get_pending_price_with_daily_report_instances(self):
        from apps.daily_reports.models import DailyReportWorker
        from apps.service_orders.const import resource_approval_status

        mock_obj = Mock()
        mock_resource = Mock()
        mock_resource.unit_price = 50.0
        mock_obj.resource = mock_resource

        mock_worker = Mock(spec=DailyReportWorker)
        mock_worker.approval_status = resource_approval_status.WAITING_APPROVAL
        mock_worker.total_price = None
        mock_worker.amount = 4.0

        mock_resource.serviceorderresource_procedures.all.return_value = [mock_worker]

        with patch(
            "apps.resources.serializers.get_board_item_relation_qs", return_value=None
        ):
            serializer = BaseContractItemSerializer()
            result = serializer.get_pending_price(mock_obj)

            assert result == 200.0

    def test_get_pending_price_with_unit_price_calculation(self):
        from apps.service_orders.const import resource_approval_status

        mock_obj = Mock()
        mock_resource = Mock()
        mock_obj.resource = mock_resource

        mock_instance = Mock()
        mock_instance.approval_status = resource_approval_status.WAITING_APPROVAL
        mock_instance.total_price = None
        mock_instance.unit_price = 25.0
        mock_instance.amount = 3.0

        mock_resource.serviceorderresource_procedures.all.return_value = [mock_instance]

        with patch(
            "apps.resources.serializers.get_board_item_relation_qs", return_value=None
        ):
            serializer = BaseContractItemSerializer()
            result = serializer.get_pending_price(mock_obj)

            assert result == 75.0

    def test_get_pending_price_with_non_waiting_approval_status(self):
        from apps.service_orders.const import resource_approval_status

        mock_obj = Mock()
        mock_resource = Mock()
        mock_obj.resource = mock_resource

        mock_instance = Mock()
        mock_instance.approval_status = resource_approval_status.APPROVED_APPROVAL
        mock_instance.total_price = 100.0

        mock_resource.serviceorderresource_procedures.all.return_value = [mock_instance]

        with patch(
            "apps.resources.serializers.get_board_item_relation_qs", return_value=None
        ):
            serializer = BaseContractItemSerializer()
            result = serializer.get_pending_price(mock_obj)

            assert result == 0.0

    def test_get_pending_price_accumulates_multiple_instances(self):
        from apps.service_orders.const import resource_approval_status

        mock_obj = Mock()
        mock_resource = Mock()
        mock_obj.resource = mock_resource

        mock_instance1 = Mock()
        mock_instance1.approval_status = resource_approval_status.WAITING_APPROVAL
        mock_instance1.total_price = 100.0

        mock_instance2 = Mock()
        mock_instance2.approval_status = resource_approval_status.WAITING_APPROVAL
        mock_instance2.total_price = 150.0

        mock_resource.serviceorderresource_procedures.all.return_value = [
            mock_instance1,
            mock_instance2,
        ]

        with patch(
            "apps.resources.serializers.get_board_item_relation_qs", return_value=None
        ):
            serializer = BaseContractItemSerializer()
            result = serializer.get_pending_price(mock_obj)

            assert result == 250.0
