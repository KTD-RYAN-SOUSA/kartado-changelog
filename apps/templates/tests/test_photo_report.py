from datetime import datetime
from unittest.mock import patch

import pytest
from rest_framework import status

from apps.companies.models import Company
from apps.users.models import User
from helpers.testing.fixtures import TestBase

from ..models import PhotoReport

pytestmark = pytest.mark.django_db


@patch("apps.templates.models.PrivateMediaStorage")
class TestPhotoReport(TestBase):
    model = "PhotoReport"

    def test_create_default_values(self, mock_storage):
        """Verifica os valores padrão ao criar um PhotoReport."""
        photo_report = PhotoReport.objects.create(company=self.company)

        assert photo_report.export_type == "NewPhotoReport"
        assert photo_report.is_inventory is False
        assert photo_report.options == {}
        assert photo_report.done is False
        assert photo_report.error is False
        assert not photo_report.options_file
        assert not photo_report.exported_file
        assert photo_report.created_by is None

    def test_str_representation(self, mock_storage):
        """Verifica a representacao em string do PhotoReport."""
        photo_report = PhotoReport.objects.create(company=self.company)

        expected = "[{}] {}: {}".format(
            self.company.name, photo_report.uuid, photo_report.export_type
        )
        assert str(photo_report) == expected

    def test_get_company_id_property(self, mock_storage):
        """Verifica que a propriedade get_company_id retorna o pk da company."""
        photo_report = PhotoReport.objects.create(company=self.company)

        assert photo_report.get_company_id == self.company.pk

    def test_created_at_auto_populated(self, mock_storage):
        """Verifica que created_at e preenchido automaticamente."""
        photo_report = PhotoReport.objects.create(company=self.company)

        assert photo_report.created_at is not None
        assert isinstance(photo_report.created_at, datetime)

    @pytest.mark.parametrize(
        "export_type",
        [
            PhotoReport.NEW_PHOTO_REPORT,
            PhotoReport.ARTESP_REPORT,
        ],
    )
    def test_export_type_valid_values(self, mock_storage, client, export_type):
        """Cria PhotoReport via API com cada export_type valido e verifica HTTP 201."""
        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "exportType": export_type,
                    },
                    "relationships": {
                        "company": {
                            "data": {"type": "Company", "id": str(self.company.pk)}
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

    def test_export_type_invalid_via_api(self, mock_storage, client):
        """Rejeita criacao de PhotoReport com export_type invalido via API (HTTP 400)."""
        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "exportType": "InvalidType",
                    },
                    "relationships": {
                        "company": {
                            "data": {"type": "Company", "id": str(self.company.pk)}
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_company_cascade_delete(self, mock_storage):
        """Verifica que deletar a company remove o PhotoReport vinculado (CASCADE)."""
        company_extra = Company.objects.create(name="Company Extra para Cascade Test")
        photo_report = PhotoReport.objects.create(company=company_extra)
        photo_report_pk = photo_report.pk

        company_extra.delete()

        assert not PhotoReport.objects.filter(pk=photo_report_pk).exists()

    def test_created_by_set_null_on_user_delete(self, mock_storage):
        """Verifica que deletar o usuario define created_by como None (SET_NULL)."""
        user_extra = User.objects.create_user(
            username="user_extra_photo_report", password="senha123"
        )
        photo_report = PhotoReport.objects.create(
            company=self.company, created_by=user_extra
        )

        user_extra.delete()

        photo_report.refresh_from_db()
        assert photo_report.created_by is None
