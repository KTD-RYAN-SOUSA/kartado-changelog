import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestDashboardReportingStats(TestBase):
    model = "ReportingStats"

    def test_dash_reporting_stats_without_company(self, client):

        response = client.get(
            path="/{}/{}/".format("dashboard", self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_dash_reporting_stats(self, client):

        data = "types"

        response = client.get(
            path="/{}/{}/?company={}&data={}".format(
                "dashboard", self.model, str(self.company.pk), data
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        data = "status"

        response = client.get(
            path="/{}/{}/?company={}&data={}".format(
                "dashboard", self.model, str(self.company.pk), data
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
