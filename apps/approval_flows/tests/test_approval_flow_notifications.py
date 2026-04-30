import uuid
from datetime import date

import pytest
from rest_framework import status

from apps.reportings.models import Reporting
from apps.work_plans.models import Job
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestApprovalFlowNotifications(TestBase):
    model = "ApprovalFlowNotifications"

    def test_approval_flow_notifications(self, client):
        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_200_OK

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_approval_flow_notifications_response_structure(self, client):
        """Testa se a resposta contém os novos campos necessários para notificações clicáveis"""
        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "data" in data
        assert "notifications" in data["data"]
        assert "reporting" in data["data"]["notifications"]
        assert "multipleDailyReport" in data["data"]["notifications"]


class TestCheckNotificationAvailability(TestBase):
    model = "CheckNotificationAvailability"

    def test_check_availability_missing_params(self, client):
        """Testa erro quando parâmetros obrigatórios estão faltando"""
        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_check_availability_invalid_resource_type(self, client):
        """Testa erro quando resource_type é inválido"""
        response = client.get(
            path="/{}/?company={}&resource_type=invalid&resource_uuid={}".format(
                self.model, str(self.company.pk), str(uuid.uuid4())
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_check_availability_invalid_uuid(self, client):
        """Testa erro quando UUID é inválido"""
        response = client.get(
            path="/{}/?company={}&resource_type=reporting&resource_uuid=invalid-uuid".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_check_availability_reporting_not_found(self, client):
        """Testa resposta quando reporting não existe"""
        response = client.get(
            path="/{}/?company={}&resource_type=reporting&resource_uuid={}".format(
                self.model, str(self.company.pk), str(uuid.uuid4())
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["status"] == "unavailable"
        assert data["reason"] == "not_found"

    def test_check_availability_mdr_not_found(self, client):
        """Testa resposta quando MultipleDailyReport não existe"""
        response = client.get(
            path="/{}/?company={}&resource_type=multiple_daily_report&resource_uuid={}".format(
                self.model, str(self.company.pk), str(uuid.uuid4())
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["status"] == "unavailable"
        assert data["reason"] == "not_found"

    def test_check_availability_reporting_with_archived_job(self, client):
        """Testa que reporting com job arquivado retorna hasJob=False"""
        archived_job = Job.objects.create(
            company=self.company,
            number="ARCHIVED-JOB-001",
            start_date=date.today(),
            end_date=date.today(),
            archived=True,
        )

        reporting = Reporting.objects.create(
            company=self.company,
            job=archived_job,
            km=0.0,
            direction="Norte",
            lane="Faixa 1",
        )

        response = client.get(
            path="/{}/?company={}&resource_type=reporting&resource_uuid={}".format(
                self.model, str(self.company.pk), str(reporting.uuid)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["status"] == "available"
        assert data["hasJob"] is False
        assert data["jobUuid"] is None
        assert data["jobNumber"] is None
