import json

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase

from ..models import ReportingInReporting

pytestmark = pytest.mark.django_db


class TestReportingInReporting(TestBase):
    model = "ReportingInReporting"

    def test_list_reporting_in_reporting(self, client):
        objects_count = ReportingInReporting.objects.count()
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        # The call was successful and the object count in the request is equal to
        # the object count in the database

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == objects_count

    @pytest.mark.parametrize(
        "param",
        [
            "53540f81-3fff-433f-8187-e6a67f274f57",
            "4b518ea1-5e65-4400-9929-eca2b0f87aef",
            "161d8498-f34a-4f3b-b962-052310752090",
        ],
    )
    def test_retrieve_reporting_relation(self, client, param):
        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(param), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

    def test_filter_parent_reporting_in_reporting(self, client):
        response = client.get(
            path="/{}/?company={}&parent={}&page_size=1".format(
                self.model, str(self.company.pk), "00016716-4db3-4f90-9762-85fbb02884cf"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 2

    def test_filter_child_reporting_in_reporting(self, client):
        response = client.get(
            path="/{}/?company={}&child={}&page_size=1".format(
                self.model, str(self.company.pk), "00015140-5cf4-43b9-be76-fa2e21da0b1c"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_filter_reporting_relation_reporting_in_reporting(self, client):
        response = client.get(
            path="/{}/?company={}&reporting_relation={}&page_size=1".format(
                self.model,
                str(self.company.pk),
                "4b518ea1-5e65-4400-9929-eca2b0f87aef,161d8498-f34a-4f3b-b962-052310752090",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 2

    def test_create_reporting_in_reporting(self, client):
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "relationships": {
                        "parent": {
                            "data": {
                                "type": "Reporting",
                                "id": "b377f326-1d77-4ad7-a891-d7eef4ed3397",
                            }
                        },
                        "child": {
                            "data": {
                                "type": "Reporting",
                                "id": "00016716-4db3-4f90-9762-85fbb02884cf",
                            }
                        },
                        "reporting_relation": {
                            "data": {
                                "type": "ReportingRelation",
                                "id": "ab8076db-7590-4e6c-83fa-a724e2d7133d",
                            }
                        },
                    },
                },
            },
        )

        # Object was not created successfully
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_reporting_in_reporting(self, client):
        instance = ReportingInReporting.objects.first()

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
                    "relationships": {
                        "reporting_relation": {
                            "data": {
                                "type": "ReportingRelation",
                                "id": "ab8076db-7590-4e6c-83fa-a724e2d7133d",
                            }
                        }
                    },
                }
            },
        )

        # The object has not changed
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_reporting_in_reporting(self, client):
        instance = ReportingInReporting.objects.first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was not deleted
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_company_id_property(self):
        """
        Test the get_company_id property of ReportingInReporting
        """
        # Get a ReportingInReporting instance
        reporting_in_reporting = ReportingInReporting.objects.first()

        # Test that get_company_id returns the correct company_id
        assert reporting_in_reporting.get_company_id == self.company.pk
        assert (
            reporting_in_reporting.get_company_id
            == reporting_in_reporting.reporting_relation.company_id
        )

        # Test the __str__ method while we're at it
        assert reporting_in_reporting.__str__()
