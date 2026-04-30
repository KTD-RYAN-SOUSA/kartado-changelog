"""
Testes para o parâmetro group_by do endpoint ZipPicture

Card: KTD-10465 - Backend: Processar parâmetro group_by e preparar dados agrupados
"""
import json
from unittest.mock import Mock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.reportings.models import Reporting, ReportingFile
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestZipPicturesGroupBy(TestBase):
    """Testes para o parâmetro group_by no endpoint ZipPicture"""

    model = "Reporting"

    def _create_reporting_file_with_upload(self, reporting):
        """Helper para criar ReportingFile com upload mockado"""
        fake_image = SimpleUploadedFile(
            name="test_image.jpg",
            content=b"fake_image_content",
            content_type="image/jpeg",
        )

        with patch("storages.backends.s3boto3.S3Boto3Storage.url") as mock_url:
            mock_url.return_value = (
                "https://test-bucket.s3.amazonaws.com/test_image.jpg"
            )
            reporting_file = ReportingFile.objects.create(
                reporting=reporting,
                upload=fake_image,
                kind="photo",
            )

        return reporting_file

    @patch("apps.reportings.views.settings")
    @patch("apps.reportings.views.requests.post")
    @patch("apps.reportings.views.get_user_token")
    def test_group_by_default_serial(
        self, mock_token, mock_post, mock_settings, client
    ):
        """Teste: Sem parâmetro group_by, deve usar 'serial' como padrão"""
        mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
        mock_settings.BACKEND_URL = "http://backend.com"
        mock_token.return_value = "fake_token"
        mock_post.return_value = Mock(status_code=200)
        mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
        mock_settings.BACKEND_URL = "http://backend.com"

        # Usar reporting existente das fixtures
        reporting = Reporting.objects.filter(
            company=self.company, number__isnull=False
        ).first()
        self._create_reporting_file_with_upload(reporting)

        response = client.get(
            path=f"/Reporting/ZipPicture/?company={str(self.company.pk)}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == 200

        # Verificar que json_final foi enviado com group_by="serial"
        call_args = mock_post.call_args
        sent_data = json.loads(call_args[1]["data"])

        assert sent_data["group_by"] == "serial"

    @patch("apps.reportings.views.settings")
    @patch("apps.reportings.views.requests.post")
    @patch("apps.reportings.views.get_user_token")
    def test_group_by_invalid_fallback_serial(
        self, mock_token, mock_post, mock_settings, client
    ):
        """Teste: Valor inválido deve usar 'serial' como fallback"""
        mock_token.return_value = "fake_token"
        mock_post.return_value = Mock(status_code=200)
        mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
        mock_settings.BACKEND_URL = "http://backend.com"

        reporting = Reporting.objects.filter(
            company=self.company, number__isnull=False
        ).first()
        self._create_reporting_file_with_upload(reporting)

        response = client.get(
            path=f"/Reporting/ZipPicture/?company={str(self.company.pk)}&group_by=invalid",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == 200

        call_args = mock_post.call_args
        sent_data = json.loads(call_args[1]["data"])

        # Deve fazer fallback para "serial"
        assert sent_data["group_by"] == "serial"

    @patch("apps.reportings.views.settings")
    @patch("apps.reportings.views.requests.post")
    @patch("apps.reportings.views.get_user_token")
    def test_group_by_classe_with_occurrence_type(
        self, mock_token, mock_post, mock_settings, client
    ):
        """Teste: group_by=classe com occurrence_type definido"""
        mock_token.return_value = "fake_token"
        mock_post.return_value = Mock(status_code=200)
        mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
        mock_settings.BACKEND_URL = "http://backend.com"

        reporting = Reporting.objects.filter(
            company=self.company, occurrence_type__isnull=False, number__isnull=False
        ).first()
        self._create_reporting_file_with_upload(reporting)

        response = client.get(
            path=f"/Reporting/ZipPicture/?company={str(self.company.pk)}&group_by=classe",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == 200

        call_args = mock_post.call_args
        sent_data = json.loads(call_args[1]["data"])

        assert sent_data["group_by"] == "classe"
        # Verificar que group_key é o nome do occurrence_type
        first_item = sent_data["data"][0]
        assert isinstance(first_item["group_key"], str)
        assert first_item["group_key"] == reporting.occurrence_type.name
        assert "skip_image" not in first_item

    @patch("apps.reportings.views.settings")
    @patch("apps.reportings.views.requests.post")
    @patch("apps.reportings.views.get_user_token")
    def test_group_by_road_with_road_model(
        self, mock_token, mock_post, mock_settings, client
    ):
        """Teste: group_by=road com road definido"""
        mock_token.return_value = "fake_token"
        mock_post.return_value = Mock(status_code=200)
        mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
        mock_settings.BACKEND_URL = "http://backend.com"

        reporting = Reporting.objects.filter(
            company=self.company, road__isnull=False, number__isnull=False
        ).first()
        self._create_reporting_file_with_upload(reporting)

        response = client.get(
            path=f"/Reporting/ZipPicture/?company={str(self.company.pk)}&group_by=road",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == 200

        call_args = mock_post.call_args
        sent_data = json.loads(call_args[1]["data"])

        assert sent_data["group_by"] == "road"
        first_item = sent_data["data"][0]
        assert isinstance(first_item["group_key"], str)
        assert first_item["group_key"] == reporting.road.name
        assert "skip_image" not in first_item

    @patch("apps.reportings.views.settings")
    @patch("apps.reportings.views.requests.post")
    @patch("apps.reportings.views.get_user_token")
    def test_group_by_road_fallback_road_name(
        self, mock_token, mock_post, mock_settings, client
    ):
        """Teste: group_by=road sem road, mas com road_name"""
        mock_token.return_value = "fake_token"
        mock_post.return_value = Mock(status_code=200)
        mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
        mock_settings.BACKEND_URL = "http://backend.com"

        reporting = Reporting.objects.filter(company=self.company).first()
        reporting.road = None
        reporting.road_name = "SP 348"
        reporting.save()

        self._create_reporting_file_with_upload(reporting)

        response = client.get(
            path=f"/Reporting/ZipPicture/?company={str(self.company.pk)}&group_by=road",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == 200

        call_args = mock_post.call_args
        sent_data = json.loads(call_args[1]["data"])

        first_item = sent_data["data"][0]
        assert first_item["group_key"] == "SP 348"
        assert isinstance(first_item["group_key"], str)
        assert "skip_image" not in first_item

    @patch("apps.reportings.views.settings")
    @patch("apps.reportings.views.requests.post")
    @patch("apps.reportings.views.get_user_token")
    def test_group_by_serial_with_number(
        self, mock_token, mock_post, mock_settings, client
    ):
        """Teste: group_by=serial com reporting.number"""
        mock_token.return_value = "fake_token"
        mock_post.return_value = Mock(status_code=200)
        mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
        mock_settings.BACKEND_URL = "http://backend.com"

        reporting = Reporting.objects.filter(
            company=self.company, number__isnull=False
        ).first()
        self._create_reporting_file_with_upload(reporting)

        response = client.get(
            path=f"/Reporting/ZipPicture/?company={str(self.company.pk)}&group_by=serial",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == 200

        call_args = mock_post.call_args
        sent_data = json.loads(call_args[1]["data"])

        assert sent_data["group_by"] == "serial"
        first_item = sent_data["data"][0]
        assert first_item["group_key"] == reporting.number
        assert isinstance(first_item["group_key"], str)
        assert "skip_image" not in first_item

    @patch("apps.reportings.views.settings")
    @patch("apps.reportings.views.requests.post")
    @patch("apps.reportings.views.get_user_token")
    def test_group_by_none(self, mock_token, mock_post, mock_settings, client):
        """Teste: group_by=none → group_key=None"""
        mock_token.return_value = "fake_token"
        mock_post.return_value = Mock(status_code=200)
        mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
        mock_settings.BACKEND_URL = "http://backend.com"

        reporting = Reporting.objects.filter(
            company=self.company, number__isnull=False
        ).first()
        self._create_reporting_file_with_upload(reporting)

        response = client.get(
            path=f"/Reporting/ZipPicture/?company={str(self.company.pk)}&group_by=none",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == 200

        call_args = mock_post.call_args
        sent_data = json.loads(call_args[1]["data"])

        assert sent_data["group_by"] == "none"
        first_item = sent_data["data"][0]
        assert first_item["group_key"] is None
        assert "skip_image" not in first_item

    @patch("apps.reportings.views.settings")
    @patch("apps.reportings.views.requests.post")
    @patch("apps.reportings.views.get_user_token")
    def test_json_final_structure(self, mock_token, mock_post, mock_settings, client):
        """Teste: Verificar que json_final possui 'group_by' e não 'structure_by_serial'"""
        mock_token.return_value = "fake_token"
        mock_post.return_value = Mock(status_code=200)
        mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
        mock_settings.BACKEND_URL = "http://backend.com"

        reporting = Reporting.objects.filter(
            company=self.company, number__isnull=False
        ).first()
        self._create_reporting_file_with_upload(reporting)

        response = client.get(
            path=f"/Reporting/ZipPicture/?company={str(self.company.pk)}&group_by=classe",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == 200

        call_args = mock_post.call_args
        sent_data = json.loads(call_args[1]["data"])

        # Verificar presença de group_by
        assert "group_by" in sent_data
        assert sent_data["group_by"] == "classe"

        # Verificar ausência de structure_by_serial
        assert "structure_by_serial" not in sent_data

    @patch("apps.reportings.views.settings")
    @patch("apps.reportings.views.requests.post")
    @patch("apps.reportings.views.get_user_token")
    def test_json_data_no_reporting_serial(
        self, mock_token, mock_post, mock_settings, client
    ):
        """Teste: Verificar que items em 'data' NÃO possuem campo 'reporting_serial'"""
        mock_token.return_value = "fake_token"
        mock_post.return_value = Mock(status_code=200)
        mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
        mock_settings.BACKEND_URL = "http://backend.com"

        reporting = Reporting.objects.filter(
            company=self.company, number__isnull=False
        ).first()
        self._create_reporting_file_with_upload(reporting)

        response = client.get(
            path=f"/Reporting/ZipPicture/?company={str(self.company.pk)}&group_by=serial",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == 200

        call_args = mock_post.call_args
        sent_data = json.loads(call_args[1]["data"])

        # Verificar que nenhum item tem reporting_serial
        for item in sent_data["data"]:
            assert "reporting_serial" not in item
            # Mas deve ter group_key
            assert "group_key" in item

    @patch("apps.reportings.views.settings")
    @patch("apps.reportings.views.requests.post")
    @patch("apps.reportings.views.get_user_token")
    def test_group_key_always_string(
        self, mock_token, mock_post, mock_settings, client
    ):
        """Teste: Verificar que group_key é sempre string (exceto quando None)"""
        mock_token.return_value = "fake_token"
        mock_post.return_value = Mock(status_code=200)
        mock_settings.ZIP_DOWNLOAD_URL = "http://fake-url.com"
        mock_settings.BACKEND_URL = "http://backend.com"

        reporting = Reporting.objects.filter(
            company=self.company,
            occurrence_type__isnull=False,
            number__isnull=False,
        ).first()
        self._create_reporting_file_with_upload(reporting)

        # Testar com group_by=classe
        response = client.get(
            path=f"/Reporting/ZipPicture/?company={str(self.company.pk)}&group_by=classe",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == 200

        call_args = mock_post.call_args
        sent_data = json.loads(call_args[1]["data"])

        first_item = sent_data["data"][0]
        # group_key deve ser string
        assert isinstance(first_item["group_key"], str)

        # Testar com group_by=none (único caso onde group_key pode ser None)
        response2 = client.get(
            path=f"/Reporting/ZipPicture/?company={str(self.company.pk)}&group_by=none",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response2.status_code == 200

        call_args2 = mock_post.call_args
        sent_data2 = json.loads(call_args2[1]["data"])

        first_item2 = sent_data2["data"][0]
        # group_key deve ser None
        assert first_item2["group_key"] is None
