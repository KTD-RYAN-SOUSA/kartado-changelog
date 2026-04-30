import json

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase, false_permission

from ..models import DailyReportExternalTeam

pytestmark = pytest.mark.django_db


class TestDailyReport(TestBase):
    model = "DailyReportExternalTeam"

    ATTRIBUTES = {
        "contractNumber": "123ABC",
        "contractorName": "John",
        "amount": 2,
        "contractDescription": "Description goes here",
    }

    def test_daily_report_external_team_list(self, client):
        """
        Ensures we can list using the DailyReportExternalTeam endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 1

    def test_daily_report_external_team_without_company(self, client):
        """
        Ensures calling the DailyReportExternalTeam endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_daily_report_external_team(self, client):
        """
        Ensures a specific DailyReportExternalTeam can be fetched using the uuid
        """

        team = DailyReportExternalTeam.objects.first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(team.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK

    def test_create_daily_report_external_team(self, client):
        """
        Ensures a new DailyReportExternalTeam can be created using the endpoint
        """

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_daily_report_external_team_without_company_id(self, client):
        """
        Ensures a new DailyReportExternalTeam cannot be created
        without a company id
        """

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_daily_report_external_team_without_permission(self, client):
        """
        Ensures a new DailyReportExternalTeam cannot be created without
        the proper permissions
        """

        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_daily_report_external_team(self, client):
        """
        Ensure a DailyReportExternalTeam can be updated using the endpoint
        """

        team = DailyReportExternalTeam.objects.first()

        # Change amount from 2 to 3 for the update
        self.ATTRIBUTES["amount"] = 3

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(team.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(team.pk),
                    "attributes": self.ATTRIBUTES,
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_daily_report_external_team(self, client):
        """
        Ensure a DailyReportExternalTeam can be deleted using the endpoint
        """

        team = DailyReportExternalTeam.objects.first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(team.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT
