import json

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase, false_permission

from ..models import DailyReportOccurrence

pytestmark = pytest.mark.django_db


class TestDailyReportOccurrence(TestBase):
    model = "DailyReportOccurrence"

    ATTRIBUTES = {
        "description": "Testing occurrences",
        "starts_at": "10:36:27",
        "ends_at": "10:36:28",
        "impact_duration": "02:36:30",
        "extra_info": "Some kind of extra info",
    }

    def test_daily_report_occurrence_list(self, client):
        """
        Ensures we can list using the DailyReportOccurrence endpoint
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

    def test_daily_report_occurrence_without_company(self, client):
        """
        Ensures calling the DailyReportOccurrence endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_daily_report_occurrence(self, client):
        """
        Ensures a specific DailyReportOccurrence can be fetched using the uuid
        """

        instance = DailyReportOccurrence.objects.first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK

    def test_create_daily_report_occurrence(self, client):
        """
        Ensures a new DailyReportOccurrence can be created using the endpoint
        """

        firm = DailyReportOccurrence.objects.first().firm
        firm_id = firm.pk

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
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_daily_report_occurrence_without_company_id(self, client):
        """
        Ensures a new DailyReportOccurrence cannot be created
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

    def test_create_daily_report_occurrence_without_permission(self, client):
        """
        Ensures a new DailyReportOccurrence cannot be created without
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

    def test_update_daily_report_occurrence(self, client):
        """
        Ensure a DailyReportOccurrence can be updated using the endpoint
        """

        instance = DailyReportOccurrence.objects.first()

        # Change change extra_info
        self.ATTRIBUTES["extra_info"] = "New extra info"

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(instance.pk),
                    "attributes": self.ATTRIBUTES,
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_daily_report_occurrence(self, client):
        """
        Ensure a DailyReportOccurrence can be deleted using the endpoint
        """

        instance = DailyReportOccurrence.objects.first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_get_company_id(self, client):
        """
        Ensures the get_company_id property returns the correct company_id
        through the firm relationship
        """

        instance = DailyReportOccurrence.objects.first()

        assert instance.get_company_id == instance.firm.company_id
        assert instance.get_company_id == self.company.pk
