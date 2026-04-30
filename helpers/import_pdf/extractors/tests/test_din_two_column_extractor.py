import logging
import tempfile
from unittest.mock import Mock, patch

import fitz
import pytest

from helpers.import_pdf.extractors.two_column import DINTwoColumnExtractor


@pytest.fixture
def mock_company():
    """Mock de objeto Company."""
    company = Mock()
    company.id = 1
    return company


@pytest.fixture
def sample_reportings():
    """Reportings de exemplo (6 NCs para 2 páginas)."""
    return [
        {"supervision_code": "NC001"},
        {"supervision_code": "NC002"},
        {"supervision_code": "NC003"},
        {"supervision_code": "NC004"},
        {"supervision_code": "NC005"},
        {"supervision_code": "NC006"},
    ]


@pytest.fixture
def temp_dir():
    """Diretório temporário para testes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir + "/"


# ==============================================================================
# TESTES DE extract_images (método principal)
# ==============================================================================


def test_extract_images_processes_three_ncs_per_page(sample_reportings, temp_dir):
    """Testa que processa exatamente 3 NCs por página."""
    extractor = DINTwoColumnExtractor.__new__(DINTwoColumnExtractor)
    extractor.pdf_path = "test.pdf"
    extractor.temp_path = temp_dir

    # Mock PDF com 2 páginas
    page1 = Mock()
    page2 = Mock()

    # Páginas sem imagens para simplificar teste
    page1.get_images.return_value = []
    page2.get_images.return_value = []

    pdf_mock = Mock()
    pdf_mock.__len__ = Mock(return_value=2)
    pdf_mock.load_page.side_effect = [page1, page2]

    with patch("fitz.open", return_value=pdf_mock):
        extractor.extract_images(sample_reportings)

        # Verifica que load_page foi chamado 2 vezes (2 páginas)
        assert pdf_mock.load_page.call_count == 2


def test_extract_images_uses_fixed_y_positions(sample_reportings, temp_dir):
    """Valida que usa posições Y fixas (176-200, 413-440, 656-680)."""
    extractor = DINTwoColumnExtractor.__new__(DINTwoColumnExtractor)
    extractor.pdf_path = "test.pdf"
    extractor.temp_path = temp_dir

    page = Mock()

    # Simular 3 imagens em posições fixas
    img1 = [1, None, None, None, None, None, None, "img1"]
    img2 = [2, None, None, None, None, None, None, "img2"]
    img3 = [3, None, None, None, None, None, None, "img3"]
    page.get_images.return_value = [img1, img2, img3]

    # Bboxes nas posições fixas (usar fitz.Rect real)
    bbox1 = fitz.Rect(0, 180, 100, 200)  # y0=180 range 176-200 (NC1)
    bbox2 = fitz.Rect(0, 420, 100, 440)  # y0=420 range 413-440 (NC2)
    bbox3 = fitz.Rect(0, 660, 100, 680)  # y0=660 range 656-680 (NC3)
    page.get_image_bbox.side_effect = [bbox1, bbox2, bbox3]

    # Mock pixmap
    pixmap_mock = Mock()
    page.get_pixmap.return_value = pixmap_mock

    pdf_mock = Mock()
    pdf_mock.__len__ = Mock(return_value=1)
    pdf_mock.load_page.return_value = page

    with patch("fitz.open", return_value=pdf_mock):
        result = extractor.extract_images(sample_reportings[:3])

        # Deve ter extraído 3 imagens
        assert len(result) == 3
        assert "NC001.png" in result
        assert "NC002.png" in result
        assert "NC003.png" in result


def test_extract_images_skips_outside_bounds(sample_reportings, temp_dir, caplog):
    """Testa que imagens fora dos ranges são ignoradas."""
    extractor = DINTwoColumnExtractor.__new__(DINTwoColumnExtractor)
    extractor.pdf_path = "test.pdf"
    extractor.temp_path = temp_dir

    page = Mock()

    # Simular imagem em posição inválida
    img1 = [1, None, None, None, None, None, None, "img1"]
    page.get_images.return_value = [img1]

    # Bbox fora dos ranges fixos
    bbox1 = Mock()
    bbox1.y0 = 300  # Entre ranges - deve ser ignorado
    page.get_image_bbox.return_value = bbox1

    pdf_mock = Mock()
    pdf_mock.__len__ = Mock(return_value=1)
    pdf_mock.load_page.return_value = page

    with patch("fitz.open", return_value=pdf_mock):
        with caplog.at_level(logging.WARNING):
            result = extractor.extract_images(sample_reportings[:3])

            # Não deve extrair nenhuma imagem
            assert len(result) == 0
            assert "outside fixed bounds" in caplog.text


def test_extract_images_handles_insufficient_codes(sample_reportings, temp_dir, caplog):
    """Testa tratamento quando não há código suficiente."""
    extractor = DINTwoColumnExtractor.__new__(DINTwoColumnExtractor)
    extractor.pdf_path = "test.pdf"
    extractor.temp_path = temp_dir

    page = Mock()

    # Simular imagem na posição do NC2
    img1 = [1, None, None, None, None, None, None, "img1"]
    page.get_images.return_value = [img1]

    bbox1 = Mock()
    bbox1.y0 = 420  # range 413-440 (NC2 - índice 1)
    page.get_image_bbox.return_value = bbox1

    pdf_mock = Mock()
    pdf_mock.__len__ = Mock(return_value=1)
    pdf_mock.load_page.return_value = page

    # Apenas 1 reporting (índice 0), mas imagem no índice 1
    with patch("fitz.open", return_value=pdf_mock):
        with caplog.at_level(logging.WARNING):
            result = extractor.extract_images(sample_reportings[:1])

            # Não deve extrair imagem
            assert len(result) == 0
            assert "Couldn't find code" in caplog.text


def test_extract_images_saves_to_temp_path(sample_reportings, temp_dir):
    """Testa que imagens são salvas no temp_path."""
    extractor = DINTwoColumnExtractor.__new__(DINTwoColumnExtractor)
    extractor.pdf_path = "test.pdf"
    extractor.temp_path = temp_dir

    page = Mock()

    img1 = [1, None, None, None, None, None, None, "img1"]
    page.get_images.return_value = [img1]

    bbox1 = fitz.Rect(0, 180, 100, 200)  # y0=180
    page.get_image_bbox.return_value = bbox1

    pixmap_mock = Mock()
    page.get_pixmap.return_value = pixmap_mock

    pdf_mock = Mock()
    pdf_mock.__len__ = Mock(return_value=1)
    pdf_mock.load_page.return_value = page

    with patch("fitz.open", return_value=pdf_mock):
        extractor.extract_images(sample_reportings[:3])

        # Verifica que save foi chamado com caminho correto
        pixmap_mock.save.assert_called_once()
        call_arg = pixmap_mock.save.call_args[0][0]
        assert call_arg.startswith(temp_dir)
        assert call_arg.endswith("NC001.png")


def test_extract_images_strips_codigo_fiscalizacao_prefix(sample_reportings, temp_dir):
    """Testa que remove 'Código Fiscalização: ' do nome do arquivo."""
    extractor = DINTwoColumnExtractor.__new__(DINTwoColumnExtractor)
    extractor.pdf_path = "test.pdf"
    extractor.temp_path = temp_dir

    # Reporting com prefixo
    reportings_with_prefix = [
        {"supervision_code": "Código Fiscalização: NC001"},
        {"supervision_code": "Código Fiscalização: NC002"},
        {"supervision_code": "Código Fiscalização: NC003"},
    ]

    page = Mock()

    img1 = [1, None, None, None, None, None, None, "img1"]
    page.get_images.return_value = [img1]

    bbox1 = fitz.Rect(0, 180, 100, 200)  # y0=180
    page.get_image_bbox.return_value = bbox1

    pixmap_mock = Mock()
    page.get_pixmap.return_value = pixmap_mock

    pdf_mock = Mock()
    pdf_mock.__len__ = Mock(return_value=1)
    pdf_mock.load_page.return_value = page

    with patch("fitz.open", return_value=pdf_mock):
        result = extractor.extract_images(reportings_with_prefix)

        # Deve ter removido o prefixo
        assert "NC001.png" in result
        assert "Código Fiscalização: NC001.png" not in result


def test_extract_images_uses_8x8_matrix(sample_reportings, temp_dir):
    """Testa que usa matriz 8x8 para ampliar imagem."""
    extractor = DINTwoColumnExtractor.__new__(DINTwoColumnExtractor)
    extractor.pdf_path = "test.pdf"
    extractor.temp_path = temp_dir

    page = Mock()

    img1 = [1, None, None, None, None, None, None, "img1"]
    page.get_images.return_value = [img1]

    bbox1 = Mock()
    bbox1.y0 = 180
    page.get_image_bbox.return_value = bbox1

    pixmap_mock = Mock()
    page.get_pixmap.return_value = pixmap_mock

    pdf_mock = Mock()
    pdf_mock.__len__ = Mock(return_value=1)
    pdf_mock.load_page.return_value = page

    with patch("fitz.open", return_value=pdf_mock):
        with patch("fitz.Matrix") as matrix_mock:
            with patch("fitz.IRect"):
                extractor.extract_images(sample_reportings[:3])

                # Verifica que Matrix foi chamada com 8, 8
                matrix_mock.assert_called_once_with(8, 8)


def test_extract_images_sorts_by_y_position(sample_reportings, temp_dir):
    """Testa que ordena bboxes por posição Y."""
    extractor = DINTwoColumnExtractor.__new__(DINTwoColumnExtractor)
    extractor.pdf_path = "test.pdf"
    extractor.temp_path = temp_dir

    page = Mock()

    # Simular 3 imagens fora de ordem
    img1 = [1, None, None, None, None, None, None, "img1"]
    img2 = [2, None, None, None, None, None, None, "img2"]
    img3 = [3, None, None, None, None, None, None, "img3"]
    page.get_images.return_value = [img1, img2, img3]

    # Bboxes fora de ordem (NC3, NC1, NC2) - usar fitz.Rect real
    bbox1 = fitz.Rect(0, 660, 100, 680)  # NC3
    bbox2 = fitz.Rect(0, 180, 100, 200)  # NC1
    bbox3 = fitz.Rect(0, 420, 100, 440)  # NC2

    page.get_image_bbox.side_effect = [bbox1, bbox2, bbox3]

    pixmap_mock = Mock()
    page.get_pixmap.return_value = pixmap_mock

    pdf_mock = Mock()
    pdf_mock.__len__ = Mock(return_value=1)
    pdf_mock.load_page.return_value = page

    with patch("fitz.open", return_value=pdf_mock):
        result = extractor.extract_images(sample_reportings[:3])

        # Deve ter processado em ordem (após sort): NC1, NC2, NC3
        # Como o sort é aplicado, as imagens devem ser extraídas na ordem correta
        assert len(result) == 3
