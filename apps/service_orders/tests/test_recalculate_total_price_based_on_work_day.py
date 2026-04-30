from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.service_orders.const.resource_approval_status import APPROVED_APPROVAL
from helpers.apps.contract_utils import recalculate_total_price_based_on_work_day


# Create a mock ResourceApprovalStatus class with the required APPROVED_APPROVAL attribute
class MockResourceApprovalStatus:
    APPROVED_APPROVAL = APPROVED_APPROVAL


@pytest.fixture
def bulk_update_mock():
    """Mock for the objects.bulk_update method"""
    return Mock()


@pytest.fixture
def type_mock(bulk_update_mock):
    """Mock for the type() function return value"""
    mock = Mock()
    mock.objects = Mock()
    mock.objects.bulk_update = bulk_update_mock
    return mock


@pytest.fixture
def bulletin():
    """Fixture to create a mock bulletin with all required attributes and methods"""
    mock_bulletin = Mock()

    mock_worker1 = Mock(amount=2, unit_price=Decimal("100.00"))
    mock_worker2 = Mock(amount=1, unit_price=Decimal("50.00"))
    workers_queryset = MagicMock()
    workers_queryset.__iter__.return_value = [mock_worker1, mock_worker2]

    workers_queryset.aggregate.return_value = {"total_price__sum": Decimal("125.00")}
    workers_queryset.model = None
    mock_bulletin.bulletin_workers.prefetch_related.return_value.filter.return_value = (
        workers_queryset
    )

    mock_equipment = Mock(amount=3, unit_price=Decimal("200.00"))
    equipments_queryset = MagicMock()
    equipments_queryset.__iter__.return_value = [mock_equipment]

    equipments_queryset.aggregate.return_value = {"total_price__sum": Decimal("300.00")}
    equipments_queryset.model = None
    mock_bulletin.bulletin_equipments.prefetch_related.return_value.filter.return_value = (
        equipments_queryset
    )

    mock_vehicle = Mock(amount=1, unit_price=Decimal("300.00"))
    vehicles_queryset = MagicMock()
    vehicles_queryset.__iter__.return_value = [mock_vehicle]

    vehicles_queryset.aggregate.return_value = {"total_price__sum": Decimal("150.00")}
    vehicles_queryset.model = None
    mock_bulletin.bulletin_vehicles.prefetch_related.return_value.filter.return_value = (
        vehicles_queryset
    )

    resources_queryset = Mock()
    resources_queryset.aggregate.return_value = {"total_price__sum": Decimal("150.00")}
    mock_bulletin.bulletin_resources.filter.return_value = resources_queryset

    mock_bulletin.work_day = 2

    return mock_bulletin


@patch("helpers.apps.contract_utils.type")
def test_recalculate_total_price_based_on_work_day(
    type_patch, bulletin, type_mock, bulk_update_mock
):
    """Test that total_price is calculated correctly based on work_day"""
    type_patch.return_value = type_mock

    recalculate_total_price_based_on_work_day(bulletin, MockResourceApprovalStatus)

    expected_total = Decimal("725.00")
    assert bulletin.save.called

    assert bulk_update_mock.call_count > 0

    bulletin.work_day = 4
    bulk_update_mock.reset_mock()

    bulletin.bulletin_workers.prefetch_related.return_value.filter.return_value.aggregate.return_value = {
        "total_price__sum": Decimal("62.50")
    }
    bulletin.bulletin_equipments.prefetch_related.return_value.filter.return_value.aggregate.return_value = {
        "total_price__sum": Decimal("150.00")
    }
    bulletin.bulletin_vehicles.prefetch_related.return_value.filter.return_value.aggregate.return_value = {
        "total_price__sum": Decimal("75.00")
    }

    recalculate_total_price_based_on_work_day(bulletin, MockResourceApprovalStatus)

    expected_total = Decimal("437.50")
    assert bulletin.total_price == expected_total
    assert bulletin.save.call_count == 2

    assert bulk_update_mock.call_count > 0


@patch("helpers.apps.contract_utils.type")
def test_recalculate_total_price_with_empty_values(type_patch, bulletin, type_mock):
    """Test that the function handles empty or None values gracefully"""
    type_patch.return_value = type_mock
    bulletin.bulletin_workers.prefetch_related.return_value.filter.return_value.aggregate.return_value = {
        "total_price__sum": None
    }
    bulletin.bulletin_equipments.prefetch_related.return_value.filter.return_value.aggregate.return_value = {
        "total_price__sum": None
    }
    bulletin.bulletin_vehicles.prefetch_related.return_value.filter.return_value.aggregate.return_value = {
        "total_price__sum": None
    }
    bulletin.bulletin_resources.filter.return_value.aggregate.return_value = {
        "total_price__sum": None
    }

    recalculate_total_price_based_on_work_day(bulletin, MockResourceApprovalStatus)

    expected_total = Decimal("0")
    assert bulletin.total_price == expected_total
    assert bulletin.save.called


@patch("helpers.apps.contract_utils.type")
def test_only_approved_resources_included(type_patch, bulletin, type_mock):
    """Test that only resources with APPROVED_APPROVAL status are included"""
    type_patch.return_value = type_mock

    recalculate_total_price_based_on_work_day(bulletin, MockResourceApprovalStatus)

    bulletin.bulletin_workers.prefetch_related.return_value.filter.assert_called_once_with(
        approval_status=MockResourceApprovalStatus.APPROVED_APPROVAL
    )
    bulletin.bulletin_equipments.prefetch_related.return_value.filter.assert_called_once_with(
        approval_status=MockResourceApprovalStatus.APPROVED_APPROVAL
    )
    bulletin.bulletin_vehicles.prefetch_related.return_value.filter.assert_called_once_with(
        approval_status=MockResourceApprovalStatus.APPROVED_APPROVAL
    )
    bulletin.bulletin_resources.filter.assert_called_once_with(
        approval_status=MockResourceApprovalStatus.APPROVED_APPROVAL
    )

    assert type_patch.called


@patch("helpers.apps.contract_utils.type")
def test_bulk_update_called_with_correct_args(
    type_patch, bulletin, type_mock, bulk_update_mock
):
    """Test that bulk_update is called with the correct arguments"""
    bulk_update_mock.reset_mock()
    type_patch.reset_mock()

    worker1 = Mock(amount=1, unit_price=Decimal("50.00"))
    worker2 = Mock(amount=2, unit_price=Decimal("100.00"))
    workers = [worker1, worker2]

    equipment1 = Mock(amount=3, unit_price=Decimal("200.00"))
    equipments = [equipment1]

    vehicle1 = Mock(amount=1, unit_price=Decimal("300.00"))
    vehicles = [vehicle1]

    workers_queryset = (
        bulletin.bulletin_workers.prefetch_related.return_value.filter.return_value
    )
    workers_queryset.__iter__.return_value = workers
    workers_queryset.model = None

    equipments_queryset = (
        bulletin.bulletin_equipments.prefetch_related.return_value.filter.return_value
    )
    equipments_queryset.__iter__.return_value = equipments
    equipments_queryset.model = None

    vehicles_queryset = (
        bulletin.bulletin_vehicles.prefetch_related.return_value.filter.return_value
    )
    vehicles_queryset.__iter__.return_value = vehicles
    vehicles_queryset.model = None

    bulletin.bulletin_workers.prefetch_related.return_value.filter.return_value.aggregate.return_value = {
        "total_price__sum": Decimal("125.00")
    }
    bulletin.bulletin_equipments.prefetch_related.return_value.filter.return_value.aggregate.return_value = {
        "total_price__sum": Decimal("300.00")
    }
    bulletin.bulletin_vehicles.prefetch_related.return_value.filter.return_value.aggregate.return_value = {
        "total_price__sum": Decimal("150.00")
    }
    bulletin.bulletin_resources.filter.return_value.aggregate.return_value = {
        "total_price__sum": Decimal("150.00")
    }

    type_patch.return_value = type_mock

    recalculate_total_price_based_on_work_day(bulletin, MockResourceApprovalStatus)

    assert (
        bulk_update_mock.call_count >= 3
    ), f"Expected at least 3 calls to bulk_update, but got {bulk_update_mock.call_count}"

    total_price_field_used = False
    for call_args in bulk_update_mock.call_args_list:
        args, kwargs = call_args
        if len(args) > 1 and args[1] == ["total_price"]:
            total_price_field_used = True
            break

    assert (
        total_price_field_used
    ), "bulk_update should be called with ['total_price'] as the fields parameter"
