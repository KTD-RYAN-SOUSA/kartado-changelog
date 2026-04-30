from unittest.mock import patch

import pytest

from helpers.import_pdf.exceptions import (
    MixedPDFFormatException,
    UnsupportedPDFFormatException,
)
from helpers.import_pdf.extractors.factory import DINExtractorFactory
from helpers.import_pdf.extractors.one_column import DINOneColumnExtractor
from helpers.import_pdf.extractors.two_column import DINTwoColumnExtractor


class TestDINExtractorFactory:
    """Testes para factory de extractors DIN."""

    @patch("helpers.import_pdf.extractors.factory.FormatDetector")
    @patch("helpers.import_pdf.extractors.base.fitz")
    def test_factory_creates_one_column_extractor(
        self, mock_fitz, mock_format_detector
    ):
        """Factory deve criar DINOneColumnExtractor para PDF de 1 coluna."""
        # Mock do detector retornando formato de 1 coluna
        mock_format_detector.detect.return_value = "one_column"

        # Mock do fitz para abrir PDF (usado pelo __init__ do extractor)
        mock_fitz.open.return_value = None

        # Criar extractor (retorna tupla extractor, format_type)
        extractor, _ = DINExtractorFactory.create("fake_one_column.pdf")

        # Validar tipo e propriedades
        assert isinstance(extractor, DINOneColumnExtractor)
        assert extractor.pdf_path == "fake_one_column.pdf"
        mock_format_detector.detect.assert_called_once_with("fake_one_column.pdf")

    @patch("helpers.import_pdf.extractors.factory.FormatDetector")
    @patch("helpers.import_pdf.extractors.base.fitz")
    def test_factory_creates_two_column_extractor(
        self, mock_fitz, mock_format_detector
    ):
        """Factory deve criar DINTwoColumnExtractor para PDF de 2 colunas."""
        # Mock do detector retornando formato de 2 colunas
        mock_format_detector.detect.return_value = "two_column"

        # Mock do fitz para abrir PDF (usado pelo __init__ do extractor)
        mock_fitz.open.return_value = None

        # Criar extractor (retorna tupla extractor, format_type)
        extractor, _ = DINExtractorFactory.create("fake_two_column.pdf")

        # Validar tipo e propriedades
        assert isinstance(extractor, DINTwoColumnExtractor)
        assert extractor.pdf_path == "fake_two_column.pdf"
        mock_format_detector.detect.assert_called_once_with("fake_two_column.pdf")

    @patch("helpers.import_pdf.extractors.factory.FormatDetector")
    @patch("helpers.import_pdf.extractors.base.fitz")
    def test_factory_passes_company_to_extractor(self, mock_fitz, mock_format_detector):
        """Factory deve passar company para o extractor."""
        # Mock do detector
        mock_format_detector.detect.return_value = "one_column"

        # Mock do fitz (usado pelo __init__ do extractor)
        mock_fitz.open.return_value = None

        # Mock de company
        mock_company = "fake_company_instance"

        # Criar extractor com company (retorna tupla extractor, format_type)
        extractor, _ = DINExtractorFactory.create("fake.pdf", company=mock_company)

        # Validar que company foi passada
        assert extractor.company == mock_company

    @patch("helpers.import_pdf.extractors.factory.FormatDetector")
    def test_factory_propagates_mixed_format_exception(self, mock_format_detector):
        """Factory deve propagar MixedPDFFormatException do detector."""
        # Mock do detector levantando exceção de formato misto
        mock_format_detector.detect.side_effect = MixedPDFFormatException(
            "PDF com formatos mistos"
        )

        # Tentar criar extractor
        with pytest.raises(MixedPDFFormatException) as exc_info:
            DINExtractorFactory.create("fake_mixed.pdf")

        assert "formatos mistos" in str(exc_info.value)

    @patch("helpers.import_pdf.extractors.factory.FormatDetector")
    def test_factory_propagates_unsupported_format_exception(
        self, mock_format_detector
    ):
        """Factory deve propagar UnsupportedPDFFormatException do detector."""
        # Mock do detector levantando exceção de formato não suportado
        mock_format_detector.detect.side_effect = UnsupportedPDFFormatException(
            "Nenhuma imagem encontrada"
        )

        # Tentar criar extractor
        with pytest.raises(UnsupportedPDFFormatException) as exc_info:
            DINExtractorFactory.create("fake_no_images.pdf")

        assert "Nenhuma imagem" in str(exc_info.value)

    @patch("helpers.import_pdf.extractors.factory.FormatDetector")
    def test_factory_raises_for_unregistered_format(self, mock_format_detector):
        """Factory deve levantar exceção se formato não estiver no REGISTRY."""
        # Mock do detector retornando formato não registrado
        mock_format_detector.detect.return_value = "three_column"

        # Tentar criar extractor
        with pytest.raises(UnsupportedPDFFormatException) as exc_info:
            DINExtractorFactory.create("fake_three_column.pdf")

        assert "Não foi possível identificar o formato do arquivo" in str(
            exc_info.value
        )

    def test_factory_registry_contains_expected_formats(self):
        """REGISTRY deve conter formatos esperados."""
        registry = DINExtractorFactory.REGISTRY

        # Validar que formatos esperados estão no registry
        assert "one_column" in registry
        assert "two_column" in registry

        # Validar que classes corretas estão mapeadas
        assert registry["one_column"] == DINOneColumnExtractor
        assert registry["two_column"] == DINTwoColumnExtractor

    def test_factory_registry_is_dict(self):
        """REGISTRY deve ser um dicionário."""
        assert isinstance(DINExtractorFactory.REGISTRY, dict)

    @patch("helpers.import_pdf.extractors.factory.FormatDetector")
    @patch("helpers.import_pdf.extractors.base.fitz")
    def test_factory_create_is_static_method(self, mock_fitz, mock_format_detector):
        """create() deve ser método estático (não precisa de instância)."""
        # Mock necessário para não falhar
        mock_format_detector.detect.return_value = "one_column"
        mock_fitz.open.return_value = None

        # Chamar diretamente pela classe (sem instanciar), retorna tupla
        extractor, _ = DINExtractorFactory.create("fake.pdf")

        # Validar que funcionou
        assert isinstance(extractor, DINOneColumnExtractor)
