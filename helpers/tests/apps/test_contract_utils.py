from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

from helpers.apps.contract_utils import (
    calculate_contract_prices,
    get_provisioned_price,
    get_unit_price,
)


class TestContractUtils(TestCase):
    """Tests for contract utility functions"""

    def test_get_unit_price_with_direct_unit_price(self):
        """Tests get_unit_price when item has direct unit_price"""
        # Setup
        mock_item = Mock()
        mock_item.unit_price = 100.50

        # Execute
        result = get_unit_price(mock_item)

        # Verify
        assert result == 100.50

    def test_get_unit_price_with_contract_administration_resource(self):
        """Tests get_unit_price when item has contract_item_administration resource"""
        # Setup
        mock_item = Mock()
        mock_item.unit_price = None
        mock_item.contract_item_administration.resource.unit_price = 75.25

        # Execute
        result = get_unit_price(mock_item)

        # Verify
        assert result == 75.25

    def test_get_unit_price_returns_zero_when_no_price_available(self):
        """Tests get_unit_price returns 0 when no price is available"""
        # Setup
        mock_item = Mock()
        mock_item.unit_price = None
        mock_item.contract_item_administration = None

        # Execute
        result = get_unit_price(mock_item)

        # Verify
        assert result == 0

    def test_get_provisioned_price_success(self):
        """Tests get_provisioned_price when spend_schedule exists"""
        # Setup
        mock_contract = Mock()
        mock_contract.spend_schedule = {"month1": 1000, "month2": 1500, "month3": 2000}

        # Execute
        result = get_provisioned_price(mock_contract)

        # Verify
        assert result == 4500

    def test_get_provisioned_price_exception_handling(self):
        """Tests get_provisioned_price exception handling"""
        # Setup
        mock_contract = Mock()
        mock_contract.spend_schedule = Mock(side_effect=Exception("Test exception"))

        # Execute
        result = get_provisioned_price(mock_contract)

        # Verify
        assert result == 0


class TestCalculateContractPrices(TestCase):
    """Tests for the calculate_contract_prices function"""

    @patch("helpers.apps.contract_utils.Contract.objects.get")
    @patch("helpers.apps.contract_utils.get_total_price")
    @patch("helpers.apps.contract_utils.get_spent_price")
    @patch("helpers.apps.contract_utils.DisableSignals")
    def test_calculate_contract_prices_success(
        self,
        mock_disable_signals,
        mock_get_spent_price,
        mock_get_total_price,
        mock_contract_get,
    ):
        """Tests calculate_contract_prices with success"""
        # Setup
        contract_uuid = "test-uuid"
        mock_contract = Mock()
        mock_contract_get.return_value = mock_contract
        mock_get_total_price.return_value = Decimal("10000.00")
        mock_get_spent_price.return_value = Decimal("3000.00")

        # Execute
        calculate_contract_prices(contract_uuid)

        # Verify
        mock_contract_get.assert_called_once_with(uuid=contract_uuid)
        mock_contract.refresh_from_db.assert_called_once()
        mock_get_total_price.assert_called_once_with(mock_contract)
        mock_get_spent_price.assert_called_once_with(mock_contract)
        assert mock_contract.total_price == Decimal("10000.00")
        assert mock_contract.spent_price == Decimal("3000.00")
        mock_disable_signals.assert_called_once()
        mock_contract.save.assert_called_once()

    @patch("helpers.apps.contract_utils.Contract.objects.get")
    def test_calculate_contract_prices_contract_not_found(self, mock_contract_get):
        """Tests calculate_contract_prices when contract is not found"""
        # Setup
        from django.core.exceptions import ObjectDoesNotExist

        contract_uuid = "non-existent-uuid"
        mock_contract_get.side_effect = ObjectDoesNotExist(
            "Contract matching query does not exist"
        )

        # Execute & Verify
        with pytest.raises(ObjectDoesNotExist):
            calculate_contract_prices(contract_uuid)
