import json
from datetime import datetime, timedelta

import pytest
from rest_framework import status

from apps.services.models import Measurement, MeasurementService, ServiceUsage
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestMeasurement(TestBase):
    model = "Measurement"

    def test_list_measurement(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_measurement_without_queryset(self, client):

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

    def test_list_measurement_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_measurement(self, client):

        measurement = Measurement.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(measurement.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_measurement_without_company(self, client):

        measurement = Measurement.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(measurement.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_measurement(self, client):

        usage = ServiceUsage.objects.filter(
            service__company=self.company, measurement__isnull=True
        )[0]
        reporting = usage.reporting

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "number": "test",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                        "endDate": (
                            datetime.now().replace(microsecond=0) + timedelta(days=1)
                        ).isoformat(),
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "reportings": {
                            "data": [{"type": "Reporting", "id": str(reporting.pk)}]
                        },
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        content = json.loads(response.content)
        obj_created = Measurement.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

    def test_create_measurement_with_no_previous(self, client):

        Measurement.objects.filter(company=self.company).delete()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "number": "test",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                        "endDate": (
                            datetime.now().replace(microsecond=0) + timedelta(days=1)
                        ).isoformat(),
                    },
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

        assert response.status_code == status.HTTP_201_CREATED

    def test_create_measurement_with_wrong_dates(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "number": "test",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                        "endDate": (
                            datetime.now().replace(microsecond=0) - timedelta(days=1)
                        ).isoformat(),
                    },
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

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_measurement(self, client):

        measurement = MeasurementService.objects.filter(
            service__isnull=False,
            measurement__company=self.company,
            measurement__approved=False,
        )[0].measurement

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(measurement.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(measurement.pk),
                    "attributes": {
                        "number": "update_test",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                        "endDate": (
                            datetime.now().replace(microsecond=0) + timedelta(days=1)
                        ).isoformat(),
                    },
                    "relationships": {},
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

    def test_update_measurement_approved(self, client):

        measurement = Measurement.objects.filter(
            company=self.company, approved=True
        ).first()
        if not measurement:
            measurement = Measurement.objects.create(
                number="test",
                start_date=datetime.now().replace(microsecond=0).isoformat(),
                end_date=(
                    datetime.now().replace(microsecond=0) + timedelta(days=1)
                ).isoformat(),
                company=self.company,
                approved=True,
            )

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(measurement.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(measurement.pk),
                    "attributes": {"number": "update_test"},
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_measurement_with_time_overlap(self, client):

        measurement = Measurement.objects.filter(company=self.company).first()

        new_measurement = Measurement.objects.create(
            number="test",
            start_date=datetime.now().replace(microsecond=0).isoformat(),
            end_date=(
                datetime.now().replace(microsecond=0) + timedelta(days=1)
            ).isoformat(),
            company=self.company,
        )

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(measurement.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(measurement.pk),
                    "attributes": {
                        "number": "update_test",
                        "startDate": new_measurement.start_date,
                        "endDate": new_measurement.end_date,
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_measuremente(self, client):

        measurement = Measurement.objects.filter(company=self.company).first()

        response = client.delete(
            path="/{}/{}/".format(self.model, str(measurement.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_dnit_rdo_measurement(self, client):

        measurement = Measurement.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/RDO/?company={}".format(
                self.model, str(measurement.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_transports_measurement(self, client):

        measurement = Measurement.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/Transports/?company={}".format(
                self.model, str(measurement.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_update_services_measurement(self, client):

        measurement_service = MeasurementService.objects.filter(
            measurement__company=self.company
        ).first()
        measurement = measurement_service.measurement

        response = client.post(
            path="/{}/{}/UpdateServices/?company={}".format(
                self.model, str(measurement.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_summary_measurement(self, client):

        measurements = set(
            MeasurementService.objects.filter(
                measurement__company=self.company
            ).values_list("measurement_id", flat=True)
        )
        measurement = (
            Measurement.objects.filter(company=self.company)
            .exclude(previous_measurement_id__in=measurements)
            .first()
        )

        response = client.get(
            path="/{}/{}/Summary/?company={}".format(
                self.model, str(measurement.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
