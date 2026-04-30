from datetime import datetime, timedelta

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestDashboardTop5RecordLocal(TestBase):
    model = "Top5RecordLocal"

    def test_dash_top_record_local_without_company(self, client):

        response = client.get(
            path="/{}/{}/".format("dashboard", self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_dash_top_record_local(self, client):

        date_after = datetime.now() - timedelta(days=365)
        date_before = datetime.now()
        local_type = "cities"

        response = client.get(
            path="/{}/{}/?company={}&date_after={}&date_before={}&local_type={}".format(
                "dashboard",
                self.model,
                str(self.company.pk),
                date_after,
                date_before,
                local_type,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        local_type = "locations"

        response = client.get(
            path="/{}/{}/?company={}&date_after={}&date_before={}&local_type={}".format(
                "dashboard",
                self.model,
                str(self.company.pk),
                date_after,
                date_before,
                local_type,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
