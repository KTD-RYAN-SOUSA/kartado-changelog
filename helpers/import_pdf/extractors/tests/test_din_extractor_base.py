from unittest.mock import MagicMock, Mock, patch

import pytest

from helpers.import_pdf.extractors.base import DINExtractor


class TestDINExtractorBase:
    """Testes para classe base DINExtractor."""

    @patch("helpers.import_pdf.extractors.base.fitz")
    def test_cannot_instantiate_abstract_class(self, mock_fitz):
        """Não deve ser possível instanciar DINExtractor diretamente."""
        mock_fitz.open.return_value = None

        # Tentar instanciar classe abstrata deve levantar TypeError
        with pytest.raises(TypeError) as exc_info:
            DINExtractor("fake.pdf")

        assert "abstract" in str(exc_info.value).lower()

    @patch("helpers.import_pdf.extractors.base.fitz")
    def test_concrete_class_must_implement_extract_images(self, mock_fitz):
        """Subclasse sem extract_images() deve levantar erro ao chamar método."""
        mock_fitz.open.return_value = None

        # Criar subclasse que não implementa extract_images
        class IncompleteExtractor(DINExtractor):
            pass

        # Não deve conseguir instanciar
        with pytest.raises(TypeError):
            IncompleteExtractor("fake.pdf")

    @patch("helpers.import_pdf.extractors.base.fitz")
    def test_concrete_class_with_extract_images_can_be_instantiated(self, mock_fitz):
        """Subclasse que implementa extract_images() pode ser instanciada."""
        mock_pdf = MagicMock()
        mock_fitz.open.return_value = mock_pdf

        # Criar subclasse completa
        class CompleteExtractor(DINExtractor):
            def extract_images(self, reportings):
                return {}

        # Deve conseguir instanciar
        extractor = CompleteExtractor("fake.pdf")

        assert extractor.pdf_path == "fake.pdf"
        assert extractor.pdf == mock_pdf
        mock_fitz.open.assert_called_once_with("fake.pdf")

    @patch("helpers.import_pdf.extractors.base.fitz")
    def test_extractor_stores_company(self, mock_fitz):
        """Extractor deve armazenar instância de company."""
        mock_fitz.open.return_value = None

        class TestExtractor(DINExtractor):
            def extract_images(self, reportings):
                return {}

        mock_company = Mock()
        extractor = TestExtractor("fake.pdf", company=mock_company)

        assert extractor.company == mock_company

    @patch("helpers.import_pdf.extractors.base.fitz")
    def test_abstract_method_raises_not_implemented_error(self, mock_fitz):
        """Chamar extract_images() em subclasse placeholder deve levantar erro."""
        mock_fitz.open.return_value = None

        class TestExtractor(DINExtractor):
            def extract_images(self, reportings):
                # Simula placeholder
                raise NotImplementedError("Not implemented yet")

        extractor = TestExtractor("fake.pdf")

        with pytest.raises(NotImplementedError):
            extractor.extract_images([])
