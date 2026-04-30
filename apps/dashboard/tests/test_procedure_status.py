from datetime import datetime, timedelta

import pytest
from rest_framework import status

from apps.companies.models import Firm
from apps.occurrence_records.models import OccurrenceType
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestDashboardProcedureStatus(TestBase):
    model = "ProcedureStatus"

    def test_dash_procedure_status_without_company(self, client):

        response = client.get(
            path="/{}/{}/".format("dashboard", self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_dash_procedure_status(self, client):

        date_after = datetime.now() - timedelta(days=365)
        date_before = datetime.now()
        firm = Firm.objects.filter(company=self.company).first()
        occtype = OccurrenceType.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}&date_after={}&date_before={}&firm={}&occurrence_type={}".format(
                "dashboard",
                self.model,
                str(self.company.pk),
                date_after,
                date_before,
                str(firm.pk),
                str(occtype.pk),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
