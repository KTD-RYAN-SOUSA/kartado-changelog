import json
from datetime import datetime

import pytest
from rest_framework import status

from apps.companies.models import Firm
from apps.daily_reports.models import (
    DailyReportContractUsage,
    DailyReportVehicle,
    DailyReportWorker,
    MultipleDailyReport,
)
from apps.resources.models import ContractItemAdministration
from apps.service_orders.models import MeasurementBulletin
from helpers.apps.daily_reports import create_and_update_contract_usage
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestDailyReportContractUsage(TestBase):
    model = "DailyReportContractUsage"

    @pytest.fixture
    def setup_test_data(self):
        """Setup test data for MDR filters."""
        firm = Firm.objects.first()
        adm = ContractItemAdministration.objects.first()
        bulletin = MeasurementBulletin.objects.first()

        # Create a MDR with specific date
        mdr = MultipleDailyReport.objects.create(
            company=self.company, date=datetime(2024, 1, 1), firm=firm
        )

        # Create vehicle
        vehicle = DailyReportVehicle.objects.create(
            company=self.company,
            contract_item_administration=adm,
            amount=1,
            measurement_bulletin=bulletin,
        )

        # Add to MDR
        mdr.multiple_daily_report_vehicles.add(vehicle)

        # Create contract usage (now done via BaseDailyReport create/update, not signals)
        create_and_update_contract_usage(vehicle)
        usage = DailyReportContractUsage.objects.get(vehicle=vehicle)

        # Manually populate M2M since it's added after vehicle creation
        usage.multiple_daily_reports.add(mdr)

        return usage

    def test_ensure_the_endpoint_is_read_only(self, client):
        """
        Ensures the endpoint doesn't support POST, PUT or DELETE
        """

        worker = DailyReportWorker.objects.first()
        usage = DailyReportContractUsage.objects.create(worker=worker)
        worker_id = str(worker.uuid)
        usage_id = str(usage.uuid)

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_200_OK

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "relationships": {
                        "worker": {
                            "data": {
                                "type": "DailyReportWorker",
                                "id": worker_id,
                            }
                        }
                    },
                }
            },
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

        response = client.put(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "id": usage_id}},
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

        response = client.delete(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "id": usage_id}},
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_executed_at_after_filter(self, client, setup_test_data):

        response = client.get(
            path="/{}/?company={}&creation_date_after=2020-05-27&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_executed_at_before_filter(self, client, setup_test_data):

        response = client.get(
            path="/{}/?company={}&creation_date_before=2025-05-27&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_get_contract_filter(self, client, setup_test_data):

        response = client.get(
            path="/{}/?company={}&contract=1cede63e-8dd7-45b0-a11a-c45e89c87874&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_get_contract_service_filter(self, client, setup_test_data):

        response = client.get(
            path="/{}/?company={}&contract_service=d9cbdaad-88d9-4427-aee7-952195166a00&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_get_measurement_bulletin_filter(self, client, setup_test_data):

        bulletin_uuid = str(MeasurementBulletin.objects.first().uuid)

        response = client.get(
            path="/{}/?company={}&measurement_bulletin=null,{}&page_size=1".format(
                self.model, str(self.company.pk), bulletin_uuid
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_firm_filter(self, client):
        """Test firm filter - filters by MDR's firm."""
        # Get a firm that belongs to the test company
        # (helper uses firm.company when worker has firm)
        firm = Firm.objects.filter(company=self.company).first()
        adm = ContractItemAdministration.objects.first()

        # Create a MDR with firm
        mdr = MultipleDailyReport.objects.create(
            company=self.company, date=datetime(2024, 1, 1), firm=firm
        )

        # Create a worker with firm (vehicles don't have firm field)
        worker = DailyReportWorker.objects.create(
            company=self.company,
            contract_item_administration=adm,
            firm=firm,
            amount=1,
        )

        # Add worker to MDR
        mdr.multiple_daily_report_workers.add(worker)

        # Create contract usage (now done via BaseDailyReport create/update, not signals)
        create_and_update_contract_usage(worker)
        usage = DailyReportContractUsage.objects.get(worker=worker)

        # Manually populate M2M since it's added after worker creation
        usage.multiple_daily_reports.add(mdr)

        firm_uuid = str(firm.uuid)

        response = client.get(
            path="/{}/?company={}&firm={}&page_size=1".format(
                self.model, str(self.company.pk), firm_uuid
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1
