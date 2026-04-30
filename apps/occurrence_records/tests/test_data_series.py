import json
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from helpers.testing.fixtures import TestBase, false_permission

from ..const import data_series_kinds as data_kinds
from ..models import DataSeries, OccurrenceRecord, OccurrenceType

pytestmark = pytest.mark.django_db


class TestDataSeries(TestBase):
    model = "DataSeries"

    ATTRIBUTES = {
        "name": "Default Da",
        "operationalPosition": "example1",
        "fieldName": "exampleField",
        "dataType": "exampleDataType",
    }

    def test_data_series_list(self, client):
        """
        Ensures we can list using the DataSeries endpoint
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

    def test_data_series_without_company(self, client):
        """
        Ensures calling the DataSeries endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_data_series(self, client):
        """
        Ensures a specific DataSeries can be fetched using the uuid
        """

        instance = DataSeries.objects.first()

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

    def test_create_data_series(self, client):
        """
        Ensures a new DataSeries can be created using the endpoint
        """

        instrument_type_id = (
            OccurrenceType.objects.filter(company=self.company).first().pk
        )
        instrument_record_id = (
            OccurrenceRecord.objects.filter(company=self.company).first().pk
        )
        sih_monitoring_point_id = (
            OccurrenceRecord.objects.filter(company=self.company).first().pk
        )

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
                        "instrumentType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(instrument_type_id),
                            }
                        },
                        "instrumentRecord": {
                            "data": {
                                "type": "OccurrenceRecord",
                                "id": str(instrument_record_id),
                            }
                        },
                        "sihMonitoringPoint": {
                            "data": {
                                "type": "OccurrenceRecord",
                                "id": str(sih_monitoring_point_id),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_data_series_without_company_id(self, client):
        """
        Ensures a new DataSeries cannot be created
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

    def test_create_data_series_without_permission(self, client):
        """
        Ensures a new DataSeries cannot be created without
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

    def test_update_data_series(self, client):  # TODO
        """
        Ensure a DataSeries can be updated using the endpoint
        """

        instance = DataSeries.objects.first()

        # Change name to "Example"
        self.ATTRIBUTES["name"] = "Example UPDATED"

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

    def test_delete_data_series(self, client):
        """
        Ensure a DataSeries can be deleted using the endpoint
        """

        instance = DataSeries.objects.first()

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

    def test_get_data_without_instrument_record(self, client):
        """
        Ensures get_data returns validation error when instrument_record is not set
        """
        data_series = DataSeries.objects.create(
            name="Test Series",
            company=self.company,
            kind=data_kinds.SERIES_KIND,
            field_name="test_field",
        )

        response = client.get(
            path="/{}/{}/Data/?company={}".format(
                self.model, str(data_series.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            "kartado.error.data_series.filled_instrument_record_field_required_for_this_endpoint"
            in str(response.content)
        )

    def test_get_data_series_kind(self, client):
        """
        Tests get_data with SERIES_KIND data series
        """
        instrument_record = OccurrenceRecord.objects.filter(
            company=self.company
        ).first()
        data_series = DataSeries.objects.create(
            name="Test Series",
            company=self.company,
            kind=data_kinds.SERIES_KIND,
            field_name="form_data",
            instrument_record=instrument_record,
        )

        response = client.get(
            path="/{}/{}/Data/?company={}".format(
                self.model, str(data_series.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_get_data_series_kind_with_date_filter(self, client):
        """
        Tests get_data with SERIES_KIND data series using date filters
        """
        instrument_record = OccurrenceRecord.objects.filter(
            company=self.company
        ).first()
        data_series = DataSeries.objects.create(
            name="Test Series",
            company=self.company,
            kind=data_kinds.SERIES_KIND,
            field_name="form_data",
            instrument_record=instrument_record,
        )

        start_date = (timezone.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = timezone.now().strftime("%Y-%m-%d")

        response = client.get(
            path="/{}/{}/Data/?company={}&start_date={}&end_date={}".format(
                self.model,
                str(data_series.pk),
                str(self.company.pk),
                start_date,
                end_date,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_get_data_logic_kind(self, client):
        """
        Tests get_data with LOGIC_KIND data series
        """
        instrument_record = OccurrenceRecord.objects.filter(
            company=self.company
        ).first()
        data_series = DataSeries.objects.create(
            name="Test Logic",
            company=self.company,
            kind=data_kinds.LOGIC_KIND,
            instrument_record=instrument_record,
            json_logic={"==": [1, 1]},
        )

        response = client.get(
            path="/{}/{}/Data/?company={}".format(
                self.model, str(data_series.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_data_sih_kind_without_parameter(self, client):
        """
        Tests get_data with SIH_KIND data series without required parameter
        """
        instrument_record = OccurrenceRecord.objects.create(
            company=self.company, form_data={"uposto": "12345"}
        )
        data_series = DataSeries.objects.create(
            name="Test SIH",
            company=self.company,
            kind=data_kinds.SIH_KIND,
            instrument_record=instrument_record,
        )

        response = client.get(
            path="/{}/{}/Data/?company={}".format(
                self.model, str(data_series.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            "kartado.error.data_series.filled_sih_monitoring_parameter_field_required_for_sih_kind"
            in str(response.content)
        )

    def test_get_data_sih_last_value_kind(self, client):
        """
        Tests get_data with SIH_LAST_VALUE_KIND data series
        """
        instrument_record = OccurrenceRecord.objects.create(
            company=self.company, form_data={"uposto": "12345"}
        )
        monitoring_parameter = OccurrenceRecord.objects.create(
            company=self.company, form_data={"uabrev": "TEMP"}
        )
        data_series = DataSeries.objects.create(
            name="Test SIH Last Value",
            company=self.company,
            kind=data_kinds.SIH_LAST_VALUE_KIND,
            instrument_record=instrument_record,
            sih_monitoring_parameter=monitoring_parameter,
            field_name="value",
            sih_frequency="DAILY",
        )

        response = client.get(
            path="/{}/{}/Data/?company={}".format(
                self.model, str(data_series.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_data_series_kind_invalid_field_name(self, client):
        """
        Tests get_data with SERIES_KIND data series using an invalid field_name
        """
        instrument_record = OccurrenceRecord.objects.create(
            company=self.company,
            form_data={"test_field": "test_value"},
            datetime=timezone.now(),
        )

        data_series = DataSeries.objects.create(
            name="Test Series",
            company=self.company,
            kind=data_kinds.SERIES_KIND,
            field_name="non_existent_field",
            instrument_record=instrument_record,
        )

        OccurrenceRecord.objects.create(
            company=self.company,
            form_data={
                "instrument": str(instrument_record.uuid),
                "test_field": "test_value",
            },
            datetime=timezone.now(),
        )

        response = client.get(
            path="/{}/{}/Data/?company={}".format(
                self.model, str(data_series.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "kartado.error.data_series.invalid_data_series_field_name" in str(
            response.content
        )
