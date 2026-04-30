import pytest
from rest_framework import status

from apps.services.models import MeasurementService
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestMeasurementService(TestBase):
    model = "MeasurementService"

    def test_list_measurement_service(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_measurement_service_without_queryset(self, client):

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

    def test_list_measurement_service_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_measurement_service(self, client):

        measurement_service = MeasurementService.objects.filter(
            service__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(measurement_service.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # __str__ method
        assert measurement_service.__str__()

        assert response.status_code == status.HTTP_200_OK

    def test_get_measurement_service_without_company(self, client):

        measurement_service = MeasurementService.objects.filter(
            service__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(measurement_service.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
