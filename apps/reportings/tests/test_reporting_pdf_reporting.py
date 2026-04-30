from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.reportings.helpers.gen.pdf_reporting import (
    PDFGeneratorBase,
    PDFGenericGenerator,
)
from apps.reportings.models import Reporting

pytestmark = pytest.mark.django_db


@pytest.fixture
def mock_reporting():
    reporting = MagicMock(spec=Reporting)
    reporting.company.custom_options = {
        "occurrencetype__fields__occurrencekind__selectoptions__options": [
            {"value": "1", "name": "Buraco"}
        ],
        "reporting__fields__direction__selectoptions__options": [
            {"value": "1", "name": "Norte"}
        ],
        "reporting__fields__lane__selectoptions__options": [
            {"value": "1", "name": "Faixa 1"}
        ],
        "reporting__fields__lot__selectoptions__options": [
            {"value": "1", "name": "Lote 1"}
        ],
        "reporting__pdfReporting__pdfReportingRightMargin": "10mm",
        "reporting__pdfReporting__footerTitle": "Título do Rodapé",
        "reporting__pdfReporting__footerSubtitle": "Subtítulo do Rodapé",
    }
    reporting.company.metadata = {}
    reporting.occurrence_type.occurrence_kind = "1"
    reporting.occurrence_type.name = "Buraco"
    reporting.form_data = {"campo1": "valor1", "campo2": "valor2"}
    reporting.reporting_files.count.return_value = 2

    file1 = MagicMock()
    file1.upload.name = "arquivo1.jpg"
    file1.description = "Descrição do arquivo 1"
    file1.datetime = datetime.now()

    file2 = MagicMock()
    file2.upload.name = "arquivo2.png"
    file2.description = "Descrição do arquivo 2"
    file2.datetime = datetime.now()

    reporting.reporting_files.all.return_value = [file1, file2]

    reporting.found_at = datetime.now()
    reporting.due_at = datetime.now()
    reporting.executed_at = datetime.now()
    reporting.number = "123"
    reporting.road_name = "BR-101"
    reporting.km = 100.5
    reporting.end_km = 101.0
    reporting.lane = "1"
    reporting.direction = "1"
    reporting.lot = "1"
    reporting.status = "Pendente"
    reporting.approval_step = "Aprovação"

    return reporting


@pytest.fixture
def mock_request():
    request = MagicMock()
    request.permissions_manager.has_permission.return_value = True
    return request


class TestPDFGeneratorBase:
    """Testes para a classe PDFGeneratorBase."""

    @patch("apps.reportings.helpers.gen.pdf_reporting.get_resized_url")
    def test_get_image_data(self, mock_get_resized_url, mock_reporting, mock_request):
        mock_get_resized_url.return_value = "https://example.com/resized-image.jpg"

        generator = PDFGeneratorBase(mock_request, mock_reporting, "template.html")
        image_data = generator.get_image_data()

        assert len(image_data) == 2
        assert image_data[0]["description"] == "Descrição do arquivo 1"
        assert image_data[0]["img_data"] == "https://example.com/resized-image.jpg"
        assert image_data[1]["is_last"] is True

        mock_get_resized_url.assert_called()

    def test_get_context(self, mock_reporting, mock_request):
        mock_inventory = mock_reporting.get_inventory.return_value
        mock_inventory.created_at.strftime.return_value = (
            "April"  # ou qualquer mês válido no month_map
        )

        generator = PDFGeneratorBase(mock_request, mock_reporting, "template.html")

        generator.get_image_data = MagicMock(return_value=[{"img_data": "url"}])

        context = generator.get_context()

        assert context["company"] == mock_reporting.company
        assert context["occurrence"] == mock_reporting
        assert context["road_name"] == mock_reporting.road_name
        assert context["km"] == mock_reporting.km
        assert context["images"] == [{"img_data": "url"}]
        assert context["form_fields"] == generator.form_fields

    @patch("apps.reportings.helpers.gen.pdf_reporting.render_to_string")
    def test_get_html_string(self, mock_render_to_string, mock_reporting, mock_request):
        mock_render_to_string.return_value = "<html>Conteúdo HTML</html>"

        generator = PDFGeneratorBase(mock_request, mock_reporting, "template.html")
        generator.context = {"key": "value"}

        html_string = generator.get_html_string()

        assert html_string == "<html>Conteúdo HTML</html>"
        mock_render_to_string.assert_called_once_with("template.html", {"key": "value"})

    @patch("apps.reportings.helpers.gen.pdf_reporting.boto3.client")
    @patch("apps.reportings.helpers.gen.pdf_reporting.requests.post")
    @patch("apps.reportings.helpers.gen.pdf_reporting.NamedTemporaryFile")
    def test_build_pdf_success(
        self, mock_temp_file, mock_post, mock_boto3, mock_reporting, mock_request
    ):
        mock_s3 = MagicMock()
        mock_boto3.return_value = mock_s3

        mock_temp_file_instance = MagicMock()
        mock_temp_file.return_value = mock_temp_file_instance
        mock_temp_file_instance.name = "/tmp/tempfile"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"out_path": "output/file.pdf"}
        mock_post.return_value = mock_response

        mock_s3.generate_presigned_url.return_value = "https://example.com/pdf-url"

        generator = PDFGeneratorBase(mock_request, mock_reporting, "template.html")
        generator.html_string = "<html>Conteúdo HTML</html>"
        generator.get_style_css = MagicMock(return_value="body { color: black; }")
        generator.get_context = MagicMock()
        generator.get_html_string = MagicMock(return_value="<html>Conteúdo HTML</html>")

        result = generator.build_pdf()

        assert result == "https://example.com/pdf-url"
        mock_boto3.assert_called()
        mock_s3.upload_file.assert_called()
        mock_post.assert_called()
        mock_s3.generate_presigned_url.assert_called()

    @patch("apps.reportings.helpers.gen.pdf_reporting.boto3.client")
    @patch("apps.reportings.helpers.gen.pdf_reporting.requests.post")
    @patch("apps.reportings.helpers.gen.pdf_reporting.NamedTemporaryFile")
    def test_build_pdf_timeout(
        self, mock_temp_file, mock_post, mock_boto3, mock_reporting, mock_request
    ):
        mock_s3 = MagicMock()
        mock_boto3.return_value = mock_s3

        mock_temp_file_instance = MagicMock()
        mock_temp_file.return_value = mock_temp_file_instance
        mock_temp_file_instance.name = "/tmp/tempfile"

        mock_response = MagicMock()
        mock_response.status_code = 504
        mock_post.return_value = mock_response

        # Configurar o S3 para simular que o arquivo foi criado após o timeout
        def head_object_side_effect(*args, **kwargs):
            return True

        mock_s3.head_object.side_effect = head_object_side_effect
        mock_s3.generate_presigned_url.return_value = "https://example.com/pdf-url"

        generator = PDFGeneratorBase(mock_request, mock_reporting, "template.html")
        generator.html_string = "<html>Conteúdo HTML</html>"
        generator.get_style_css = MagicMock(return_value="body { color: black; }")
        generator.get_context = MagicMock()
        generator.get_html_string = MagicMock(return_value="<html>Conteúdo HTML</html>")

        with patch("apps.reportings.helpers.gen.pdf_reporting.time.sleep"):
            result = generator.build_pdf()

        assert result == "https://example.com/pdf-url"
        mock_boto3.assert_called()
        mock_s3.upload_file.assert_called()
        mock_post.assert_called()
        mock_s3.generate_presigned_url.assert_called()


class TestPDFGenericGenerator:
    """Testes para a classe PDFGenericGenerator."""

    def test_init(self, mock_reporting, mock_request):
        """Testa a inicialização da classe PDFGenericGenerator."""
        pdf_config = {"key": "value"}
        generator = PDFGenericGenerator(
            mock_request, mock_reporting, "template.html", pdf_config
        )

        assert generator.headers == {
            "Accept": "*/*",
            "Content-Type": "application/vnd.api+json",
            "Authorization": "Basic ZW5naWU6ZXNzYVNlbmhhRGFFbmdpZVByZTIwMjM=",
        }

    @patch("apps.reportings.helpers.gen.pdf_reporting.requests.post")
    def test_get_response(self, mock_post, mock_reporting, mock_request):
        mock_post.return_value = "response"

        generator = PDFGenericGenerator(
            mock_request, mock_reporting, "template.html", {}
        )
        response = generator.get_response({"data": "payload"})

        assert response == "response"
        mock_post.assert_called_once_with(
            "https://staticmap.kartado.com.br/",
            data={"data": "payload"},
            headers=generator.headers,
        )

    def test_merge_features(self, mock_reporting, mock_request):
        main_feature = {"type": "FeatureCollection", "features": [{"id": "main"}]}

        second_features = [
            {"type": "FeatureCollection", "features": [{"id": "second1"}]},
            {"type": "FeatureCollection", "features": [{"id": "second2"}]},
        ]

        generator = PDFGenericGenerator(
            mock_request, mock_reporting, "template.html", {}
        )
        result = generator.merge_features(main_feature, second_features)

        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 3
        assert {"id": "main"} in result["features"]
        assert {"id": "second1"} in result["features"]
        assert {"id": "second2"} in result["features"]

    @patch("apps.reportings.helpers.gen.pdf_reporting.PDFGeneratorBase.get_html_string")
    def test_get_html_string(self, mock_super_get_html, mock_reporting, mock_request):
        """Testa o método get_html_string com substituições de margem."""
        mock_super_get_html.return_value = "margin: 42mm 16mm 45mm 16mm; top: -78pt;"

        generator = PDFGenericGenerator(
            mock_request, mock_reporting, "template.html", {}
        )
        html = generator.get_html_string()

        assert "margin: 42mm 16mm 45mm 16mm;" in html
        assert "top: -78pt;" in html
