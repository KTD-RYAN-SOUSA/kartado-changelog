import json

import pytest
from rest_framework import status

from apps.reportings.models import Reporting
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestInventory(TestBase):
    model = "Inventory"

    def test_list_inventory(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_inventory_without_queryset(self, client):

        false_permission(self.user, self.company, self.model, allowed="none")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        false_permission(self.user, self.company, self.model, allowed="self")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_inventory(self, client):

        obj = Reporting.objects.filter(
            company=self.company, occurrence_type__occurrence_kind="2"
        )[0]

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def request_with_classification_filter(self, client, filter_name):
        response = client.get(
            path="/{}/?company={}&page_size=1&{}=1".format(
                self.model, str(self.company.pk), filter_name
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_hole_classification_filter(self, client):
        self.request_with_classification_filter(client, "hole_classification")

    def test_sheet_classification_filter(self, client):
        self.request_with_classification_filter(client, "sheet_classification")

    def test_inventory_jobs_start_date(self, client):
        response = client.get(
            path="/{}/?company={}&inventory_jobs_start_date_after={}".format(
                self.model, str(self.company.pk), "2020-01-01"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_inventory_jobs_end_date(self, client):
        response = client.get(
            path="/{}/?company={}&inventory_jobs_end_date_after={}".format(
                self.model, str(self.company.pk), "2020-01-01"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_inventory_jobs_progress(self, client):
        response = client.get(
            path="/{}/?company={}&inventory_jobs_progress_min={}&inventory_jobs_progress_max={}".format(
                self.model, str(self.company.pk), 0.49, 0.51
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_inventory_jobs_combinations(self, client):
        response = client.get(
            path="/{}/?company={}&inventory_jobs_start_date_after={}&inventory_jobs_end_date_after={}".format(
                self.model, str(self.company.pk), "2020-01-01", "2020-01-01"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

        response = client.get(
            path="/{}/?company={}&inventory_jobs_start_date_after={}&inventory_jobs_progress_min={}&inventory_jobs_progress_max={}".format(
                self.model, str(self.company.pk), "2020-01-01", 0.49, 0.51
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

        response = client.get(
            path="/{}/?company={}&inventory_jobs_start_date_after={}&inventory_jobs_end_date_after={}&inventory_jobs_progress_min={}&inventory_jobs_progress_max={}".format(
                self.model, str(self.company.pk), "2020-01-01", "2020-01-01", 0.49, 0.51
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_inventory_fields(self, client):

        response = client.get(
            path="/{}/Choices/ExcelImport/?company={}".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
