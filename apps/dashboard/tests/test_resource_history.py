from datetime import datetime, timedelta

import pytest
from rest_framework import status

from apps.service_orders.models import ProcedureResource
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestDashboardResourceHistory(TestBase):
    model = "ResourceHistory"

    def test_dash_resource_history_without_company(self, client):

        response = client.get(
            path="/{}/{}/".format("dashboard", self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_dash_resource_history_with_wrong_resource(self, client):

        response = client.get(
            path="/{}/{}/?company={}&resources={}".format(
                "dashboard", self.model, str(self.company.pk), "not_uuid"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_dash_resource_history(self, client):

        date_after = datetime.now() - timedelta(days=5000)
        date_before = datetime.now()

        resource = ProcedureResource.objects.filter(
            procedure__created_at__gte=(datetime.now() - timedelta(days=5000)),
            resource__company=self.company,
            approval_date__gt=date_after,
            approval_date__lte=date_before,
        ).first()

        response = client.get(
            path="/{}/{}/?company={}&resources={}&date_after={}&date_before={}".format(
                "dashboard",
                self.model,
                str(self.company.pk),
                str(resource.pk),
                date_after,
                date_before,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
