import json

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase

from ..models import ReportingExport

pytestmark = pytest.mark.django_db


class TestReportingExport(TestBase):
    model = "ReportingExport"

    def test_list_reporting_export(self, client):
        objects_count = ReportingExport.objects.count()
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

    def test_retrieve_reporting_export(self, client):
        instance = ReportingExport.objects.first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

    def test_create_reporting_export(self, client):
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "exportType": "SIMPLE",
                        "isInventory": True,
                        "filters": {"a": "b", "c": "d"},
                        "extraInfo": {"1": 2},
                    },
                    "relationships": {
                        "company": {
                            "data": {"type": "Company", "id": str(self.company.pk)}
                        }
                    },
                },
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_filter_type_reporting_export(self, client):
        response = client.get(
            path="/{}/?company={}&export_type={}&page_size=1".format(
                self.model, str(self.company.pk), "SIMPLE"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 2

    def test_filter_is_inventory_reporting_export(self, client):
        response = client.get(
            path="/{}/?company={}&is_inventory={}&page_size=1".format(
                self.model, str(self.company.pk), True
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_filter_created_at_reporting_export(self, client):
        response = client.get(
            path="/{}/?company={}&created_at_after={}&page_size=1".format(
                self.model, str(self.company.pk), "2024-06-20"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 2

    def test_update_reporting_export(self, client):
        instance = ReportingExport.objects.first()

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
                    "attributes": {
                        "exportType": "SIMPLE",
                        "isInventory": False,
                        "filters": {"a": "b", "c": "d"},
                        "extraInfo": {"1": 2},
                    },
                },
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_reporting_export(self, client):
        instance = ReportingExport.objects.first()

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

    @pytest.mark.parametrize(
        "rep_uuid,is_inventory,export_type,extra_info",
        [
            (
                "00000db3-a561-4387-ac47-d48fca2d6c24",
                False,
                "SIMPLE",
                {
                    "export_resources": True,
                    "export_photos": True,
                    "export_kind": True,
                    "export_date": True,
                    "export_description": True,
                },
            ),
            (
                "00000db3-a561-4387-ac47-d48fca2d6c24",
                False,
                "NORMAL",
                {
                    "export_resources": True,
                    "export_photos": True,
                    "export_kind": True,
                    "export_date": True,
                    "export_description": True,
                },
            ),
            ("00015140-5cf4-43b9-be76-fa2e21da0b1c", True, "SIMPLE", {}),
            ("00015140-5cf4-43b9-be76-fa2e21da0b1c", True, "NORMAL", {}),
        ],
    )
    def test_create_reporting_export_with_reps(
        self, client, rep_uuid, is_inventory, export_type, extra_info
    ):
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "exportType": export_type,
                        "isInventory": is_inventory,
                        "filters": {"uuid": rep_uuid, "sort": "created_at"},
                        "extraInfo": extra_info,
                    },
                    "relationships": {
                        "company": {
                            "data": {"type": "Company", "id": str(self.company.pk)}
                        }
                    },
                },
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_get_company_id(self, client):
        instance = ReportingExport.objects.first()

        assert instance.get_company_id == instance.company_id
        assert instance.get_company_id == self.company.pk

    def test_str_method(self, client):
        instance = ReportingExport.objects.first()

        expected_str = "[{}] {}: {}".format(
            instance.company.name, instance.uuid, instance.export_type
        )
        assert str(instance) == expected_str
