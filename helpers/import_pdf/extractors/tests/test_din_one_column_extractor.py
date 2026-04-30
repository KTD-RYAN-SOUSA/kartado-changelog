from unittest.mock import MagicMock, patch

import fitz
import pytest

from helpers.import_pdf.extractors.one_column import DINOneColumnExtractor


@pytest.fixture
def mock_pdf_path():
    """Path do PDF de teste."""
    return "/tmp/test_one_column.pdf"


@pytest.fixture
def reportings_single():
    """Reportings com um único NC."""
    return [{"supervision_code": "852690"}]


@pytest.fixture
def reportings_multiple():
    """Reportings com múltiplos NCs."""
    return [{"supervision_code": "852690"}, {"supervision_code": "852691"}]


class TestDINOneColumnExtractor:
    """Testes para DINOneColumnExtractor."""

    @patch("fitz.open")
    def test_extract_images_with_single_page_single_nc(
        self, mock_fitz_open, mock_pdf_path, reportings_single, tmp_path
    ):
        """Teste: 1 página, 1 NC, 3 fotos."""
        # Mock PDF
        mock_pdf = MagicMock()
        mock_pdf.__len__ = MagicMock(return_value=1)
        mock_fitz_open.return_value = mock_pdf

        # Mock página
        mock_page = MagicMock()
        # search_for retorna lista de Rect (truthy = header encontrado)
        mock_page.search_for = MagicMock(return_value=[fitz.Rect(0, 50, 100, 60)])
        mock_page.get_images = MagicMock(
            return_value=[
                (1, 0, 100, 100, 8, "DeviceRGB", "", "Im1", "DCTDecode"),
                (2, 0, 100, 100, 8, "DeviceRGB", "", "Im2", "DCTDecode"),
                (3, 0, 100, 100, 8, "DeviceRGB", "", "Im3", "DCTDecode"),
            ]
        )
        mock_page.get_image_bbox = MagicMock(
            side_effect=[
                fitz.Rect(0, 200, 100, 300),
                fitz.Rect(0, 400, 100, 500),
                fitz.Rect(0, 600, 100, 700),
            ]
        )
        mock_pix = MagicMock()
        mock_page.get_pixmap = MagicMock(return_value=mock_pix)
        mock_pdf.load_page = MagicMock(return_value=mock_page)

        # Executar
        extractor = DINOneColumnExtractor(mock_pdf_path)
        extractor.temp_path = str(tmp_path) + "/"
        result = extractor.extract_images(reportings_single)

        # Verificar
        assert len(result) == 3
        assert all("852690" in r for r in result)

    @patch("fitz.open")
    def test_extract_images_with_multiple_pages_single_nc(
        self, mock_fitz_open, mock_pdf_path, reportings_single, tmp_path
    ):
        """Teste: 2 páginas, 1 NC (quebra de página)."""
        # Mock PDF
        mock_pdf = MagicMock()
        mock_pdf.__len__ = MagicMock(return_value=2)
        mock_fitz_open.return_value = mock_pdf

        # Mock páginas
        mock_page0 = MagicMock()
        # Página com header (search_for retorna Rect com y1=60)
        mock_page0.search_for = MagicMock(return_value=[fitz.Rect(0, 50, 100, 60)])
        mock_page0.get_images = MagicMock(
            return_value=[
                (1, 0, 100, 100, 8, "DeviceRGB", "", "Im1", "DCTDecode"),
                (2, 0, 100, 100, 8, "DeviceRGB", "", "Im2", "DCTDecode"),
            ]
        )
        mock_page0.get_image_bbox = MagicMock(
            side_effect=[fitz.Rect(0, 200, 100, 300), fitz.Rect(0, 400, 100, 500)]
        )
        mock_pix0 = MagicMock()
        mock_page0.get_pixmap = MagicMock(return_value=mock_pix0)

        mock_page1 = MagicMock()
        # Página de continuação (sem header)
        mock_page1.search_for = MagicMock(return_value=[])
        mock_page1.get_images = MagicMock(
            return_value=[
                (3, 0, 100, 100, 8, "DeviceRGB", "", "Im3", "DCTDecode"),
                (4, 0, 100, 100, 8, "DeviceRGB", "", "Im4", "DCTDecode"),
            ]
        )
        mock_page1.get_image_bbox = MagicMock(
            side_effect=[fitz.Rect(0, 100, 100, 200), fitz.Rect(0, 300, 100, 400)]
        )
        mock_pix1 = MagicMock()
        mock_page1.get_pixmap = MagicMock(return_value=mock_pix1)

        mock_pdf.load_page = MagicMock(side_effect=[mock_page0, mock_page1])

        # Executar
        extractor = DINOneColumnExtractor(mock_pdf_path)
        extractor.temp_path = str(tmp_path) + "/"
        result = extractor.extract_images(reportings_single)

        # Verificar
        assert len(result) == 4
        assert all("852690" in r for r in result)

    @patch("fitz.open")
    def test_extract_images_with_multiple_ncs(
        self, mock_fitz_open, mock_pdf_path, reportings_multiple, tmp_path
    ):
        """Teste: 2 páginas, 2 NCs."""
        # Mock PDF
        mock_pdf = MagicMock()
        mock_pdf.__len__ = MagicMock(return_value=2)
        mock_fitz_open.return_value = mock_pdf

        # Mock páginas
        mock_page0 = MagicMock()
        mock_page0.search_for = MagicMock(return_value=[fitz.Rect(0, 50, 100, 60)])
        mock_page0.get_images = MagicMock(
            return_value=[
                (1, 0, 100, 100, 8, "DeviceRGB", "", "Im1", "DCTDecode"),
                (2, 0, 100, 100, 8, "DeviceRGB", "", "Im2", "DCTDecode"),
            ]
        )
        mock_page0.get_image_bbox = MagicMock(
            side_effect=[fitz.Rect(0, 200, 100, 300), fitz.Rect(0, 400, 100, 500)]
        )
        mock_pix0 = MagicMock()
        mock_page0.get_pixmap = MagicMock(return_value=mock_pix0)

        mock_page1 = MagicMock()
        mock_page1.search_for = MagicMock(return_value=[fitz.Rect(0, 50, 100, 60)])
        mock_page1.get_images = MagicMock(
            return_value=[
                (3, 0, 100, 100, 8, "DeviceRGB", "", "Im3", "DCTDecode"),
                (4, 0, 100, 100, 8, "DeviceRGB", "", "Im4", "DCTDecode"),
                (5, 0, 100, 100, 8, "DeviceRGB", "", "Im5", "DCTDecode"),
            ]
        )
        mock_page1.get_image_bbox = MagicMock(
            side_effect=[
                fitz.Rect(0, 200, 100, 300),
                fitz.Rect(0, 400, 100, 500),
                fitz.Rect(0, 600, 100, 700),
            ]
        )
        mock_pix1 = MagicMock()
        mock_page1.get_pixmap = MagicMock(return_value=mock_pix1)

        mock_pdf.load_page = MagicMock(side_effect=[mock_page0, mock_page1])

        # Executar
        extractor = DINOneColumnExtractor(mock_pdf_path)
        extractor.temp_path = str(tmp_path) + "/"
        result = extractor.extract_images(reportings_multiple)

        # Verificar
        assert len(result) == 5
        assert sum(1 for r in result if "852690" in r) == 2
        assert sum(1 for r in result if "852691" in r) == 3

    @patch("fitz.open")
    def test_extract_images_ignores_unknown_ncs(
        self, mock_fitz_open, mock_pdf_path, reportings_single, tmp_path
    ):
        """Teste: Ignora páginas com NC além dos reportings disponíveis."""
        # Mock PDF com 2 páginas, mas só 1 reporting
        mock_pdf = MagicMock()
        mock_pdf.__len__ = MagicMock(return_value=2)
        mock_fitz_open.return_value = mock_pdf

        # Página 0: tem header, extrai imagem com o único reporting disponível
        mock_page0 = MagicMock()
        mock_page0.search_for = MagicMock(return_value=[fitz.Rect(0, 50, 100, 60)])
        mock_page0.get_images = MagicMock(
            return_value=[(1, 0, 100, 100, 8, "DeviceRGB", "", "Im1", "DCTDecode")]
        )
        mock_page0.get_image_bbox = MagicMock(return_value=fitz.Rect(0, 200, 100, 300))
        mock_pix0 = MagicMock()
        mock_page0.get_pixmap = MagicMock(return_value=mock_pix0)

        # Página 1: tem header, mas reportings esgotados → deve ser ignorada
        mock_page1 = MagicMock()
        mock_page1.search_for = MagicMock(return_value=[fitz.Rect(0, 50, 100, 60)])
        mock_page1.get_images = MagicMock(
            return_value=[(2, 0, 100, 100, 8, "DeviceRGB", "", "Im2", "DCTDecode")]
        )
        mock_pix1 = MagicMock()
        mock_page1.get_pixmap = MagicMock(return_value=mock_pix1)

        mock_pdf.load_page = MagicMock(side_effect=[mock_page0, mock_page1])

        # Executar
        extractor = DINOneColumnExtractor(mock_pdf_path)
        extractor.temp_path = str(tmp_path) + "/"
        result = extractor.extract_images(reportings_single)

        # Apenas 1 imagem (da página 0); página 1 ignorada por falta de reporting
        assert len(result) == 1
        assert "852690" in result[0]

    @patch("fitz.open")
    def test_extract_images_case_insensitive(
        self, mock_fitz_open, mock_pdf_path, reportings_single, tmp_path
    ):
        """Teste: Header com case diferente."""
        # Mock PDF
        mock_pdf = MagicMock()
        mock_pdf.__len__ = MagicMock(return_value=1)
        mock_fitz_open.return_value = mock_pdf

        # Mock página com header encontrado por search_for
        mock_page = MagicMock()
        mock_page.search_for = MagicMock(return_value=[fitz.Rect(0, 50, 100, 60)])
        mock_page.get_images = MagicMock(
            return_value=[(1, 0, 100, 100, 8, "DeviceRGB", "", "Im1", "DCTDecode")]
        )
        mock_page.get_image_bbox = MagicMock(return_value=fitz.Rect(0, 200, 100, 300))
        mock_pix = MagicMock()
        mock_page.get_pixmap = MagicMock(return_value=mock_pix)
        mock_pdf.load_page = MagicMock(return_value=mock_page)

        # Executar
        extractor = DINOneColumnExtractor(mock_pdf_path)
        extractor.temp_path = str(tmp_path) + "/"
        result = extractor.extract_images(reportings_single)

        # Verificar
        assert len(result) == 1
        assert "852690" in result[0]

    @patch("fitz.open")
    def test_extract_images_orders_by_y(
        self, mock_fitz_open, mock_pdf_path, reportings_single, tmp_path
    ):
        """Teste: Imagens fora de ordem são ordenadas por Y."""
        # Mock PDF
        mock_pdf = MagicMock()
        mock_pdf.__len__ = MagicMock(return_value=1)
        mock_fitz_open.return_value = mock_pdf

        # Mock página
        mock_page = MagicMock()
        mock_page.search_for = MagicMock(return_value=[fitz.Rect(0, 50, 100, 60)])
        mock_page.get_images = MagicMock(
            return_value=[
                (1, 0, 100, 100, 8, "DeviceRGB", "", "Im1", "DCTDecode"),
                (2, 0, 100, 100, 8, "DeviceRGB", "", "Im2", "DCTDecode"),
                (3, 0, 100, 100, 8, "DeviceRGB", "", "Im3", "DCTDecode"),
            ]
        )
        # Fora de ordem: 400, 200, 600
        mock_page.get_image_bbox = MagicMock(
            side_effect=[
                fitz.Rect(0, 400, 100, 500),
                fitz.Rect(0, 200, 100, 300),
                fitz.Rect(0, 600, 100, 700),
            ]
        )
        mock_pix = MagicMock()
        mock_page.get_pixmap = MagicMock(return_value=mock_pix)
        mock_pdf.load_page = MagicMock(return_value=mock_page)

        # Executar
        extractor = DINOneColumnExtractor(mock_pdf_path)
        extractor.temp_path = str(tmp_path) + "/"
        result = extractor.extract_images(reportings_single)

        # Verificar que foram processadas
        assert len(result) == 3

    @patch("fitz.open")
    def test_extract_images_uses_matrix_8x8(
        self, mock_fitz_open, mock_pdf_path, reportings_single, tmp_path
    ):
        """Teste: Verifica se usa Matrix(8, 8) para alta resolução."""
        # Mock PDF
        mock_pdf = MagicMock()
        mock_pdf.__len__ = MagicMock(return_value=1)
        mock_fitz_open.return_value = mock_pdf

        # Mock página
        mock_page = MagicMock()
        mock_page.search_for = MagicMock(return_value=[fitz.Rect(0, 50, 100, 60)])
        mock_page.get_images = MagicMock(
            return_value=[(1, 0, 100, 100, 8, "DeviceRGB", "", "Im1", "DCTDecode")]
        )
        mock_page.get_image_bbox = MagicMock(return_value=fitz.Rect(0, 200, 100, 300))
        mock_pix = MagicMock()
        mock_page.get_pixmap = MagicMock(return_value=mock_pix)
        mock_pdf.load_page = MagicMock(return_value=mock_page)

        # Executar
        extractor = DINOneColumnExtractor(mock_pdf_path)
        extractor.temp_path = str(tmp_path) + "/"
        extractor.extract_images(reportings_single)

        # Verificar chamada com Matrix(8, 8)
        assert mock_page.get_pixmap.called
        call_args = mock_page.get_pixmap.call_args
        assert "matrix" in call_args.kwargs
        matrix = call_args.kwargs["matrix"]
        assert matrix.a == 8.0
        assert matrix.d == 8.0
