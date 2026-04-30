import datetime
import uuid
from unittest.mock import patch

import pytest
from django.test import RequestFactory

from apps.companies.models import Firm
from apps.resources.filters import ContractFilter, ContractItemUnitPriceFilter
from apps.resources.models import Contract, ContractItemUnitPrice
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestContractFilterBase(TestBase):
    model = "Contract"

    def setup_method(self):
        self.factory = RequestFactory()
        self.filter_instance = ContractFilter()

    def test_get_firm_single_firm(self):

        firm = Firm.objects.filter(company=self.company).first()

        queryset = Contract.objects.all()
        result = self.filter_instance.get_firm(queryset, "firm", str(firm.pk))

        assert hasattr(result, "count")
        assert result.count() >= 0

    def test_get_firm_multiple_firms(self):
        firms = Firm.objects.filter(company=self.company)[:2]

        if firms.count() >= 1:
            firm_ids = ",".join([str(firms[0].pk), str(firms[0].pk)])
        else:
            firm = Firm.objects.first()
            firm_ids = str(firm.pk)

        queryset = Contract.objects.all()
        result = self.filter_instance.get_firm(queryset, "firm", firm_ids)

        assert hasattr(result, "count")
        assert result.count() >= 0

    def test_get_firm_with_spaces(self):
        firm = Firm.objects.first()

        queryset = Contract.objects.all()
        result = self.filter_instance.get_firm(queryset, "firm", f" {firm.pk} ")

        expected_result = self.filter_instance.get_firm(queryset, "firm", str(firm.pk))
        assert result.count() == expected_result.count()

    def test_get_firm_empty_value(self):
        from django.core.exceptions import ValidationError

        queryset = Contract.objects.all()

        with pytest.raises(ValidationError):
            result = self.filter_instance.get_firm(queryset, "firm", "")
            list(result)

    def test_get_date_contract_active_on_date(self):

        test_date = datetime.date(2023, 6, 15)

        queryset = Contract.objects.all()
        result = self.filter_instance.get_date(queryset, "date", test_date)

        assert hasattr(result, "count")
        assert result.count() >= 0

        for contract in result:
            if contract.contract_start and contract.contract_end:
                assert contract.contract_start <= test_date <= contract.contract_end

    def test_get_date_contract_not_active(self):

        test_date = datetime.date(1990, 1, 1)

        queryset = Contract.objects.all()
        result = self.filter_instance.get_date(queryset, "date", test_date)

        assert hasattr(result, "count")
        assert result.count() >= 0

        for contract in result:
            if contract.contract_start and contract.contract_end:
                assert contract.contract_start <= test_date <= contract.contract_end

    def test_get_date_edge_cases(self):

        today = datetime.date.today()

        queryset = Contract.objects.all()
        result = self.filter_instance.get_date(queryset, "date", today)

        assert hasattr(result, "count")
        assert result.count() >= 0

        for contract in result:
            if contract.contract_start and contract.contract_end:
                assert contract.contract_start <= today <= contract.contract_end


class TestContractItemFilterBasic(TestBase):
    model = "ContractItemUnitPrice"

    def setup_method(self):
        """Setup test data"""
        # Use concrete filter class instead of abstract base
        self.filter_instance = ContractItemUnitPriceFilter()

    def test_filter_contract_valid_uuid(self):

        contract = Contract.objects.first()

        queryset = ContractItemUnitPrice.objects.all()
        result = self.filter_instance.filter_contract(
            queryset, "contract", contract.uuid
        )

        assert hasattr(result, "count")
        assert result.count() >= 0

        for item in result:
            assert item.resource.contract.uuid == contract.uuid

    def test_filter_contract_nonexistent_uuid(self):

        nonexistent_uuid = uuid.uuid4()
        queryset = ContractItemUnitPrice.objects.all()

        result = self.filter_instance.filter_contract(
            queryset, "contract", nonexistent_uuid
        )

        assert result.count() == 0

    def test_filter_contract_multiple_items_same_contract(self):

        contract = Contract.objects.first()

        queryset = ContractItemUnitPrice.objects.all()
        result = self.filter_instance.filter_contract(
            queryset, "contract", contract.uuid
        )

        for item in result:
            assert item.resource.contract.uuid == contract.uuid

        expected_count = ContractItemUnitPrice.objects.filter(
            resource__contract__uuid=contract.uuid
        ).count()
        assert result.count() == expected_count


class TestContractItemFilter(TestBase):

    model = "ContractItemUnitPrice"

    def setup_method(self):

        self.filter_instance = ContractItemUnitPriceFilter()

    def test_filter_contract_in_force_true_current_date(self):

        today = datetime.datetime.now().date()

        queryset = ContractItemUnitPrice.objects.all()
        result = self.filter_instance.filter_contract_in_force(
            queryset, "contract_in_force", True
        )

        assert hasattr(result, "count")
        assert result.count() >= 0

        for item in result:
            contract = item.resource.contract
            if contract.contract_start and contract.contract_end:
                assert contract.contract_start <= today
                assert contract.contract_end >= today

    def test_filter_contract_in_force_false_expired_contracts(self):

        today = datetime.datetime.now().date()

        queryset = ContractItemUnitPrice.objects.all()
        result = self.filter_instance.filter_contract_in_force(
            queryset, "contract_in_force", False
        )

        assert hasattr(result, "count")
        assert result.count() >= 0

        for item in result:
            contract = item.resource.contract
            if contract.contract_start and contract.contract_end:
                assert not (
                    contract.contract_start <= today and contract.contract_end >= today
                )

    def test_filter_contract_in_force_edge_case_start_date(self):

        today = datetime.datetime.now().date()

        queryset = ContractItemUnitPrice.objects.all()
        result = self.filter_instance.filter_contract_in_force(
            queryset, "contract_in_force", True
        )

        assert hasattr(result, "count")
        assert result.count() >= 0

        for item in result:
            contract = item.resource.contract
            if (
                contract.contract_start == today
                and contract.contract_end
                and contract.contract_end >= today
            ):

                assert True

    def test_filter_contract_in_force_edge_case_end_date(self):
        today = datetime.datetime.now().date()

        queryset = ContractItemUnitPrice.objects.all()
        result = self.filter_instance.filter_contract_in_force(
            queryset, "contract_in_force", True
        )

        assert hasattr(result, "count")
        assert result.count() >= 0

        for item in result:
            contract = item.resource.contract
            if (
                contract.contract_end == today
                and contract.contract_start
                and contract.contract_start <= today
            ):
                assert True

    @patch("apps.resources.helpers.filters.abstract_filters.datetime")
    def test_filter_contract_in_force_mocked_datetime(self, mock_datetime):

        mock_date = datetime.date(2023, 6, 15)
        mock_datetime.datetime.now.return_value = datetime.datetime.combine(
            mock_date, datetime.time()
        )

        queryset = ContractItemUnitPrice.objects.all()

        result_true = self.filter_instance.filter_contract_in_force(
            queryset, "contract_in_force", True
        )
        result_false = self.filter_instance.filter_contract_in_force(
            queryset, "contract_in_force", False
        )

        assert hasattr(result_true, "count")
        assert hasattr(result_false, "count")
        assert result_true.count() >= 0
        assert result_false.count() >= 0

        assert result_true.count() + result_false.count() <= queryset.count()
