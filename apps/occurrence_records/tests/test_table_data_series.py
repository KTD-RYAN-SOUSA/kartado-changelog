import json

import pytest
from rest_framework import status

from apps.occurrence_records.models import OccurrenceRecord, TableDataSeries
from helpers.testing.fixtures import TestBase

from ..const import data_series_kinds

pytestmark = pytest.mark.django_db


class TestTableDataSeries(TestBase):
    model = "TableDataSeries"

    def test_list_table_data_series(self, client):
        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_table_data_series(self, client):
        # Create test OccurrenceRecord instances for the test
        occurrence_record = OccurrenceRecord.objects.create(
            company=self.company,
            created_by=self.user,
            number="TEST-001",
            properties=[],
            form_data={},
            form_metadata={},
            arcgis_ids={},
            distance_from_dam=0.0,
            reviews=0,
            editable=True,
            is_approved=False,
        )

        monitoring_point = OccurrenceRecord.objects.create(
            company=self.company,
            created_by=self.user,
            number="TEST-002",
            properties=[],
            form_data={},
            form_metadata={},
            arcgis_ids={},
            distance_from_dam=0.0,
            reviews=0,
            editable=True,
            is_approved=False,
        )

        data = {
            "data": {
                "type": self.model,
                "attributes": {
                    "name": "Test Data Series",
                    "kind": data_series_kinds.SERIES_KIND,
                    "field_name": "test_field",
                },
                "relationships": {
                    "company": {
                        "data": {
                            "type": "Company",
                            "id": str(self.company.pk),
                        }
                    },
                    "instrument_record": {
                        "data": {
                            "type": "OccurrenceRecord",
                            "id": str(occurrence_record.pk),
                        }
                    },
                    "sih_monitoring_point": {
                        "data": {
                            "type": "OccurrenceRecord",
                            "id": str(monitoring_point.pk),
                        }
                    },
                },
            }
        }

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=json.dumps(data),
        )

        assert response.status_code == status.HTTP_201_CREATED

    def test_update_table_data_series(self, client):
        data_series = TableDataSeries.objects.create(
            name="Test Data Series",
            kind=data_series_kinds.SERIES_KIND,
            field_name="test_field",
            company=self.company,
            created_by=self.user,
        )

        data = {
            "data": {
                "type": self.model,
                "id": str(data_series.pk),
                "attributes": {
                    "name": "Updated Data Series",
                },
            }
        }

        response = client.patch(
            path="/{}/{}/".format(self.model, str(data_series.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=json.dumps(data),
        )

        assert response.status_code == status.HTTP_200_OK

    def test_delete_table_data_series(self, client):
        data_series = TableDataSeries.objects.create(
            name="Test Data Series",
            kind=data_series_kinds.SERIES_KIND,
            field_name="test_field",
            company=self.company,
            created_by=self.user,
        )

        response = client.delete(
            path="/{}/{}/".format(self.model, str(data_series.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
