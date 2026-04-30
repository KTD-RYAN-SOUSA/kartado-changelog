import json
import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.companies.models import Company, Entity
from apps.daily_reports.models import DailyReportContractUsage
from apps.files.models import GenericFile
from apps.resources.models import Contract
from apps.service_orders.models import ProcedureResource, ServiceOrderResource
from helpers.apps.preview_download_export import PreviewDownloadExport


@pytest.fixture
def mock_contract():
    contract = MagicMock(spec=Contract)
    contract.extra_info = {
        "r_c_number": "123",
        "accounting_classification": "Classification",
    }
    contract.name = "Test Contract"
    contract.contract_start = datetime.now()
    contract.contract_end = datetime.now()
    contract.performance_months = 12

    # Mock related objects
    contract.subcompany = None
    contract.firm.name = "Test Subcompany"
    contract.status.name = "Active"
    contract.uuid = "5320d4a1-6885-488f-af7b-590471850f53"

    return contract


@pytest.fixture
def mock_daily_report_worker():
    """Fixture for DailyReportContractUsage."""
    usage = MagicMock()

    # Mock worker instance
    worker = MagicMock()
    worker.resource_name = "Worker Resource"
    worker.resource_unit = "Hour"
    worker.amount = 8
    worker.unit_price = 50
    worker.total_price = 400
    worker.creation_date = datetime.now()
    worker.approval_status = "APPROVED_APPROVAL"
    worker.created_by.get_full_name.return_value = "Jane Doe"

    # Mock contract item administration
    contract_item = MagicMock()
    contract_item.contract_item_administration_services.exists.return_value = True
    contract_item.contract_item_administration_services.first.return_value.description = (
        "Admin Service"
    )
    contract_item.sort_string = "1.1"
    contract_item.entity.name = "Admin Entity"

    worker.contract_item_administration = contract_item

    # Mock multiple daily reports
    mdr = MagicMock()
    mdr.number = "MDR-001"
    worker.multiple_daily_reports.exists.return_value = True
    worker.multiple_daily_reports.all.return_value = [mdr]

    # Set up usage object
    usage.worker = worker
    usage.equipment = None
    usage.vehicle = None

    return usage


@pytest.fixture
def mock_daily_report_equipment():
    """Fixture for DailyReportContractUsage."""
    usage = MagicMock()

    # Mock equipment instance
    equipment = MagicMock()
    equipment.resource_name = "Equipment Resource"
    equipment.resource_unit = "Hour"
    equipment.amount = 8
    equipment.unit_price = 50
    equipment.total_price = 400
    equipment.creation_date = datetime.now()
    equipment.approval_status = "APPROVED_APPROVAL"
    equipment.created_by.get_full_name.return_value = "Jane Doe"

    # Mock contract item administration
    contract_item = MagicMock()
    contract_item.contract_item_administration_services.exists.return_value = True
    contract_item.contract_item_administration_services.first.return_value.description = (
        "Admin Service"
    )
    contract_item.sort_string = "1.2"
    contract_item.entity.name = "Admin Entity"

    equipment.contract_item_administration = contract_item

    # Mock multiple daily reports
    mdr = MagicMock()
    mdr.number = "MDR-001"
    equipment.multiple_daily_reports.exists.return_value = True
    equipment.multiple_daily_reports.all.return_value = [mdr]

    # Set up usage object
    usage.equipment = equipment
    usage.worker = None
    usage.vehicle = None

    return usage


@pytest.fixture
def mock_daily_report_vehicle():
    """Fixture for DailyReportContractUsage."""
    usage = MagicMock()

    # Mock vehicle instance
    vehicle = MagicMock()
    vehicle.resource_name = "vehicle Resource"
    vehicle.resource_unit = "Hour"
    vehicle.amount = 8
    vehicle.unit_price = 50
    vehicle.total_price = 400
    vehicle.creation_date = datetime.now()
    vehicle.approval_status = "APPROVED_APPROVAL"
    vehicle.created_by.get_full_name.return_value = "Jane Doe"

    # Mock contract item administration
    contract_item = MagicMock()
    contract_item.contract_item_administration_services.exists.return_value = True
    contract_item.contract_item_administration_services.first.return_value.description = (
        "Admin Service"
    )
    contract_item.sort_string = "1.3"
    contract_item.entity.name = "Admin Entity"

    vehicle.contract_item_administration = contract_item

    # Mock multiple daily reports
    mdr = MagicMock()
    mdr.number = "MDR-001"
    vehicle.multiple_daily_reports.exists.return_value = True
    vehicle.multiple_daily_reports.all.return_value = [mdr]

    # Set up usage object
    usage.vehicle = vehicle
    usage.worker = None
    usage.equipment = None

    return usage


@pytest.fixture
def mock_procedure_resource():
    """Fixture for ProcedureResource."""
    procedure = MagicMock()

    # Mock resource
    resource = MagicMock()
    resource.name = "Test Resource"
    resource.unit = "Unit"
    procedure.resource = resource

    # Mock service order resource and entity
    service_order = MagicMock()
    service_order.entity.name = "Test Entity"
    procedure.service_order_resource = service_order

    # Mock dates and user
    procedure.creation_date = datetime.now()
    procedure.created_by.get_full_name.return_value = "John Doe"

    # Mock reporting
    reporting = MagicMock()
    reporting.number = "REP-001"
    procedure.reporting = reporting

    # Mock approval and amounts
    procedure.approval_status = "APPROVED_APPROVAL"
    procedure.amount = 10
    procedure.unit_price = 100
    procedure.total_price = 1000

    # Mock measurement bulletin
    bulletin = MagicMock()
    bulletin.number = "MB-001"
    procedure.measurement_bulletin = bulletin

    # Mock approval date
    procedure.approval_date = datetime.now()

    return procedure


class TestPreviewDownloadExport:
    """Tests for PreviewDownload export functionality."""

    @patch("helpers.apps.preview_download_export.boto3.client")
    def test_init(self, mock_boto3):
        """Test initialization of PreviewDownloadExport."""
        export = PreviewDownloadExport(company_name="Test Company")

        assert export.company_name == "Test Company"
        assert "[Kartado] Prévia de valores de medição" in export.filename
        assert "media/private/" in export.object_name
        mock_boto3.assert_called_once()

    def test_get_contract_data(self, mock_contract):
        """Test contract data extraction."""
        export = PreviewDownloadExport(company_name="Test Company")
        export.contract = mock_contract

        contract_data = export.get_contract_data()

        assert len(contract_data) == 8
        assert contract_data[0] == "123"  # object_number
        assert contract_data[1] == "Test Subcompany"  # subcompany_name
        assert contract_data[2] == "Test Contract"  # contract_name
        assert contract_data[5] == "Classification"  # accounting
        assert contract_data[6] == "Active"  # contract_status
        assert contract_data[7] == 12  # performance_months

    @patch("helpers.apps.preview_download_export.boto3.client")
    def test_get_s3_url(self, mock_boto3):
        """Test S3 URL generation."""
        mock_s3 = MagicMock()
        mock_boto3.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = "https://example.com/file.xlsx"

        export = PreviewDownloadExport(company_name="Test Company")
        url = export.get_s3_url()

        assert url == "https://example.com/file.xlsx"
        mock_s3.generate_presigned_url.assert_called_once()

    def test_get_procedure_resource_data(self):
        """Test procedure resource data formatting."""
        export = PreviewDownloadExport(company_name="Test Company")

        # Mock procedure resource
        procedure_resource = MagicMock()
        procedure_resource.resource.name = "Resource Name"
        procedure_resource.resource.unit = "Unit"
        procedure_resource.service_order_resource.entity.name = "Entity"
        procedure_resource.creation_date = datetime.now()
        procedure_resource.created_by.get_full_name.return_value = "John Doe"
        procedure_resource.reporting.number = "REP-001"
        procedure_resource.approval_status = "APPROVED_APPROVAL"
        procedure_resource.amount = 10
        procedure_resource.unit_price = 100
        procedure_resource.total_price = 1000

        data = export.get_procedure_resource_data(procedure_resource)

        assert len(data) == 15
        assert data[0] == "PREÇO UNITÁRIO"
        assert data[3] == "Resource Name"
        assert data[4] == 10
        assert data[5] == "Unit"
        assert data[8] == "John Doe"
        assert data[12] == "Aprovado"

    @pytest.mark.django_db
    @patch("helpers.apps.preview_download_export.Contract.objects.get")
    @patch("helpers.apps.preview_download_export.load_workbook")
    @patch("helpers.apps.preview_download_export.PreviewDownloadExport.upload_file")
    def test_generate_file(
        self, mock_upload, mock_load_workbook, mock_contract_get, mock_contract
    ):
        """Test file generation process."""
        # Configure the mock to return our mock_contract
        mock_contract_get.return_value = mock_contract

        export = PreviewDownloadExport(
            company_name="Test Company",
            contract_uuid="5320d4a1-6885-488f-af7b-590471850f53",
            work_days=1,
        )

        mock_wb = MagicMock()
        mock_load_workbook.return_value = mock_wb

        # Mock querysets
        export.procedure_queryset = []
        export.daily_queryset = []

        export.generate_file()

        # Verify contract was queried with correct UUID
        mock_contract_get.assert_called_once_with(
            uuid="5320d4a1-6885-488f-af7b-590471850f53"
        )
        mock_load_workbook.assert_called_once()
        mock_upload.assert_called_once()

    def test_get_daily_report_data(self, mock_daily_report_worker):
        """Test administration data extraction."""
        export = PreviewDownloadExport(company_name="Test Company", work_days=1)

        data = export.get_daily_report_data(mock_daily_report_worker)

        assert len(data) == 15
        assert data[0] == "ADMINISTRAÇÃO"
        assert data[1] == "Admin Service"
        assert data[2] == "1.1"
        assert data[3] == "Worker Resource"
        assert data[4] == 8  # amount
        assert data[5] == "Hour"
        assert data[6] == "Admin Entity"
        assert data[8] == "Jane Doe"
        assert data[9] == 50  # unit_price
        assert data[10] == 400  # total_price
        assert data[11] == "MDR-001"
        assert data[12] == "Aprovado"

    def test_get_daily_report_data_with_different_prices(
        self, mock_daily_report_worker
    ):
        """Test administration data with different price calculations."""
        export = PreviewDownloadExport(
            company_name="Test Company",
            work_days=1,  # Changed to test price calculation
        )

        # Test when unit_price is None
        mock_daily_report_worker.worker.unit_price = None
        mock_daily_report_worker.worker.resource_unit_price = 50

        data = export.get_daily_report_data(mock_daily_report_worker)

        assert data[9] == 50  # Should use resource_unit_price
        assert data[10] == (8 * 50) / 1  # total_price calculation with work_days

    def test_get_daily_report_data_missing_values(self, mock_daily_report_worker):
        """Test administration data handling with missing values."""
        export = PreviewDownloadExport(company_name="Test Company")

        # Remove optional values
        mock_daily_report_worker.worker.created_by = None
        mock_daily_report_worker.worker.multiple_daily_reports.exists.return_value = (
            False
        )
        mock_daily_report_worker.worker.approval_date = None
        mock_daily_report_worker.worker.measurement_bulletin = None

        data = export.get_daily_report_data(mock_daily_report_worker)

        assert data[8] == ""  # created_by
        assert data[11] == ""  # mdr_number
        assert data[13] is None  # approval_date
        assert data[14] == ""  # bulletin_number

    @pytest.mark.django_db
    @patch("helpers.apps.preview_download_export.Contract.objects.get")
    @patch("helpers.apps.preview_download_export.boto3.client")
    @patch("helpers.apps.preview_download_export.load_workbook")
    def test_fill_workbook(
        self,
        mock_load_workbook,
        mock_boto3,
        mock_contract_get,
        mock_daily_report_worker,
        mock_procedure_resource,
        mock_contract,
        mock_daily_report_equipment,
        mock_daily_report_vehicle,
    ):
        """Test workbook filling with administration items."""
        # Configure Contract.objects.get mock
        mock_contract_get.return_value = mock_contract

        # Initialize export
        export = PreviewDownloadExport(
            company_name="Test Company",
            contract_uuid="5320d4a1-6885-488f-af7b-590471850f53",
            work_days=1,
        )
        # Mock workbook and worksheet
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        # Mock max_row property
        mock_ws.max_row = 1

        cells = {}
        cell_calls = []

        def mock_cell(**kwargs):
            cell = MagicMock()
            row = kwargs.get("row", 1)
            column = kwargs.get("column", 1)
            cells[(row, column)] = cell
            cell_calls.append(kwargs)
            return cell

        mock_ws.cell = mock_cell
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb
        export.wb = mock_wb

        # Set querysets
        export.daily_queryset = [
            mock_daily_report_worker,
            mock_daily_report_vehicle,
            mock_daily_report_equipment,
        ]
        export.procedure_queryset = [mock_procedure_resource]

        # Execute
        export.fill_workbook()

        # Verify first row is 2 (header is row 1)
        first_row = min(
            call["row"] for call in cell_calls if isinstance(call["row"], int)
        )
        assert first_row == 2, f"Expected first row to be 2, got {first_row}"

    @pytest.mark.django_db
    def test_init_with_file_uuid(self, mock_contract):
        """Test initialization with file UUID that loads procedure and daily querysets."""
        # Create test UUIDs
        procedure_uuid = uuid.uuid4()
        daily_uuid = uuid.uuid4()
        file_content = [
            [str(procedure_uuid)],  # Procedure UUIDs
            [str(daily_uuid)],  # Daily UUIDs
        ]

        file_uuid = uuid.uuid4()
        generic_file = GenericFile.objects.create(pk=file_uuid)
        temp_path = "/tmp/preview_download_uuid/"
        os.makedirs(temp_path, exist_ok=True)
        json_name = "{}.json".format(str(file_uuid))
        json_file_path = temp_path + json_name
        with open(json_file_path, "w") as outfile:
            json.dump(file_content, outfile)

        json_file = open(json_file_path, "rb")
        generic_file.file.save(json_name, ContentFile(json_file.read()))

        # Create real Contract instance instead of using mock
        contract = Contract.objects.create(
            name="Test Contract",
            contract_start=timezone.now(),
            contract_end=timezone.now() + timedelta(days=365),
        )

        # Create Entity for ServiceOrderResource
        entity = Entity.objects.create(
            name="Test Entity", company=Company.objects.first()
        )

        # Create ServiceOrderResource with real Contract
        service_order_resource = ServiceOrderResource.objects.create(
            contract=contract, entity=entity
        )

        # Create test instances with real UUIDs
        _ = ProcedureResource.objects.create(
            uuid=procedure_uuid,
            creation_date=timezone.now(),
            service_order_resource=service_order_resource,
            amount=10,
            unit_price=100,
            total_price=1000,
        )
        _ = DailyReportContractUsage.objects.create(uuid=daily_uuid)

        # Initialize exporter with file UUID
        export = PreviewDownloadExport(
            file_uuid=str(generic_file.uuid), company_name="Test Company"
        )

        # Verify querysets were loaded correctly
        assert export.procedure_queryset.count() == 1
        assert export.daily_queryset.count() == 1

        # Verify correct instances were loaded
        assert str(export.procedure_queryset.first().uuid) == str(procedure_uuid)
        assert str(export.daily_queryset.first().uuid) == str(daily_uuid)
