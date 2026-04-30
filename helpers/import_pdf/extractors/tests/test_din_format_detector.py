from unittest.mock import MagicMock, patch

import pytest

from helpers.import_pdf.exceptions import (
    MixedPDFFormatException,
    UnsupportedPDFFormatException,
)
from helpers.import_pdf.extractors.detector import FormatDetector


class TestFormatDetector:
    """Testes para detecção de formato DIN."""

    def test_has_two_columns_with_wide_spread(self):
        """Posições X com spread > 150px devem indicar 2 colunas."""
        # Simula imagens em posições muito diferentes (2 colunas)
        x_positions = [50, 80, 350, 380]  # spread = 330px
        result = FormatDetector._has_two_columns(x_positions)

        assert result is True

    def test_has_two_columns_with_narrow_spread(self):
        """Posições X com spread < 150px devem indicar 1 coluna."""
        # Simula imagens centralizadas (1 coluna)
        x_positions = [250, 270, 290, 300]  # spread = 50px
        result = FormatDetector._has_two_columns(x_positions)

        assert result is False

    def test_has_two_columns_with_exact_threshold(self):
        """Spread exatamente no threshold deve ser considerado 1 coluna."""
        # spread = 150px (exatamente no threshold)
        x_positions = [100, 250]  # spread = 150px
        result = FormatDetector._has_two_columns(x_positions)

        # Threshold é >, não >=, então 150px = 1 coluna
        assert result is False

    def test_has_two_columns_with_empty_list(self):
        """Lista vazia de posições deve retornar False."""
        result = FormatDetector._has_two_columns([])

        assert result is False

    def test_has_two_columns_with_single_position(self):
        """Uma única posição deve retornar False (spread = 0)."""
        result = FormatDetector._has_two_columns([250])

        assert result is False

    @patch("helpers.import_pdf.extractors.detector.fitz")
    def test_detect_two_column_format(self, mock_fitz):
        """PDF de 2 colunas deve ser detectado corretamente."""
        # Configurar mock de PDF com 2 colunas
        mock_pdf = MagicMock()
        mock_pdf.__len__.return_value = 1
        mock_fitz.open.return_value = mock_pdf

        # Mock da primeira página
        mock_page = MagicMock()
        mock_pdf.load_page.return_value = mock_page

        # Imagens como tuplas (image[-2] = nome da imagem)
        mock_page.get_images.return_value = [
            (1, 0, 100, 100, 8, "DeviceRGB", "", "img1", "DCTDecode"),
            (2, 0, 100, 100, 8, "DeviceRGB", "", "img2", "DCTDecode"),
        ]

        # 2 "Código Fiscalização:" → diretamente two_column
        mock_page.get_text.return_value = (
            "Código Fiscalização: NC001\nCódigo Fiscalização: NC002\n"
        )

        bbox1 = MagicMock()
        bbox1.y0 = 100  # > 50, não é logo
        bbox2 = MagicMock()
        bbox2.y0 = 300

        mock_page.get_image_bbox.side_effect = [bbox1, bbox2]

        # Testar detecção
        format_type = FormatDetector.detect("fake_path.pdf")

        assert format_type == "two_column"
        mock_fitz.open.assert_called_once_with("fake_path.pdf")

    @patch("helpers.import_pdf.extractors.detector.fitz")
    def test_detect_one_column_format(self, mock_fitz):
        """PDF de 1 coluna deve ser detectado corretamente."""
        # Configurar mock de PDF com 1 coluna
        mock_pdf = MagicMock()
        mock_pdf.__len__.return_value = 1
        mock_fitz.open.return_value = mock_pdf

        # Mock da primeira página
        mock_page = MagicMock()
        mock_pdf.load_page.return_value = mock_page

        # Imagens como tuplas
        mock_page.get_images.return_value = [
            (1, 0, 100, 100, 8, "DeviceRGB", "", "img1", "DCTDecode"),
            (2, 0, 100, 100, 8, "DeviceRGB", "", "img2", "DCTDecode"),
        ]

        # 1 "Código Fiscalização:" → usa desempate por spread X e largura
        mock_page.get_text.return_value = "Código Fiscalização: NC001\n"

        # Largura da página para cálculo do ratio
        mock_page.rect.width = 600

        # Bboxes: spread X pequeno (< 150) e imagens largas (> 60% de 600px)
        bbox1 = MagicMock()
        bbox1.y0 = 100  # > 50, não é logo
        bbox1.x0 = 50
        bbox1.x1 = 550  # largura = 500, ratio = 0.83 > 0.6
        bbox2 = MagicMock()
        bbox2.y0 = 300
        bbox2.x0 = 60
        bbox2.x1 = 540  # largura = 480, ratio = 0.80 > 0.6

        mock_page.get_image_bbox.side_effect = [bbox1, bbox2]

        # Testar detecção
        format_type = FormatDetector.detect("fake_path.pdf")

        assert format_type == "one_column"
        mock_fitz.open.assert_called_once_with("fake_path.pdf")

    @patch("helpers.import_pdf.extractors.detector.fitz")
    def test_reject_pdf_without_images(self, mock_fitz):
        """PDF sem imagens deve levantar UnsupportedPDFFormatException."""
        # Configurar mock de PDF sem imagens
        mock_pdf = MagicMock()
        mock_pdf.__len__.return_value = 1
        mock_fitz.open.return_value = mock_pdf

        mock_page = MagicMock()
        mock_pdf.load_page.return_value = mock_page
        mock_page.get_images.return_value = []  # Sem imagens

        # Testar que exceção é levantada
        with pytest.raises(UnsupportedPDFFormatException) as exc_info:
            FormatDetector.detect("fake_path.pdf")

        # Verifica mensagem user-friendly (CA-04)
        assert "Não foi possível identificar o formato do arquivo" in str(
            exc_info.value
        )

    @patch("helpers.import_pdf.extractors.detector.fitz")
    def test_reject_empty_pdf(self, mock_fitz):
        """PDF vazio deve levantar UnsupportedPDFFormatException."""
        # Configurar mock de PDF vazio
        mock_pdf = MagicMock()
        mock_pdf.__len__.return_value = 0  # PDF vazio
        mock_fitz.open.return_value = mock_pdf

        # Testar que exceção é levantada
        with pytest.raises(UnsupportedPDFFormatException) as exc_info:
            FormatDetector.detect("fake_path.pdf")

        # Verifica mensagem user-friendly (CA-04)
        assert "Não foi possível identificar o formato do arquivo" in str(
            exc_info.value
        )

    @patch("helpers.import_pdf.extractors.detector.fitz")
    def test_reject_mixed_format_pdf(self, mock_fitz):
        """PDF com formatos mistos deve levantar MixedPDFFormatException."""
        # Configurar mock de PDF com 2 páginas
        mock_pdf = MagicMock()
        mock_pdf.__len__.return_value = 2
        mock_fitz.open.return_value = mock_pdf

        # Página 1: two_column (2 "Código Fiscalização:")
        mock_page1 = MagicMock()
        mock_page1.get_images.return_value = [
            (1, 0, 100, 100, 8, "DeviceRGB", "", "img1", "DCTDecode"),
            (2, 0, 100, 100, 8, "DeviceRGB", "", "img2", "DCTDecode"),
        ]
        mock_page1.get_text.return_value = (
            "Código Fiscalização: NC001\nCódigo Fiscalização: NC002\n"
        )
        bbox1_p1 = MagicMock()
        bbox1_p1.y0 = 100
        bbox2_p1 = MagicMock()
        bbox2_p1.y0 = 300
        mock_page1.get_image_bbox.side_effect = [bbox1_p1, bbox2_p1]

        # Página 2: one_column (1 "Código Fiscalização:", spread X pequeno, imagens largas)
        mock_page2 = MagicMock()
        mock_page2.get_images.return_value = [
            (3, 0, 100, 100, 8, "DeviceRGB", "", "img3", "DCTDecode"),
            (4, 0, 100, 100, 8, "DeviceRGB", "", "img4", "DCTDecode"),
        ]
        mock_page2.get_text.return_value = "Código Fiscalização: NC003\n"
        mock_page2.rect.width = 600
        bbox1_p2 = MagicMock()
        bbox1_p2.y0 = 100
        bbox1_p2.x0 = 50
        bbox1_p2.x1 = 550
        bbox2_p2 = MagicMock()
        bbox2_p2.y0 = 300
        bbox2_p2.x0 = 60
        bbox2_p2.x1 = 540
        mock_page2.get_image_bbox.side_effect = [bbox1_p2, bbox2_p2]

        mock_pdf.load_page.side_effect = [mock_page1, mock_page2]

        # Testar que exceção é levantada
        with pytest.raises(MixedPDFFormatException) as exc_info:
            FormatDetector.detect("fake_path.pdf")

        # Verifica mensagem user-friendly (CA-04)
        assert "Não foi possível identificar o formato do arquivo" in str(
            exc_info.value
        )

    @patch("helpers.import_pdf.extractors.detector.fitz")
    def test_pages_without_images_are_skipped(self, mock_fitz):
        """Páginas sem imagens devem ser toleradas (não geram erro)."""
        # Configurar mock de PDF com 2 páginas
        mock_pdf = MagicMock()
        mock_pdf.__len__.return_value = 2
        mock_fitz.open.return_value = mock_pdf

        # Página 1: two_column (2 "Código Fiscalização:")
        mock_page1 = MagicMock()
        mock_page1.get_images.return_value = [
            (1, 0, 100, 100, 8, "DeviceRGB", "", "img1", "DCTDecode"),
            (2, 0, 100, 100, 8, "DeviceRGB", "", "img2", "DCTDecode"),
        ]
        mock_page1.get_text.return_value = (
            "Código Fiscalização: NC001\nCódigo Fiscalização: NC002\n"
        )
        bbox1 = MagicMock()
        bbox1.y0 = 100
        bbox2 = MagicMock()
        bbox2.y0 = 300
        mock_page1.get_image_bbox.side_effect = [bbox1, bbox2]

        # Página 2: SEM imagens
        mock_page2 = MagicMock()
        mock_page2.get_images.return_value = []

        mock_pdf.load_page.side_effect = [mock_page1, mock_page2]

        # Deve detectar formato da página 1 e tolerar página 2 sem imagens
        format_type = FormatDetector.detect("fake_path.pdf")

        assert format_type == "two_column"
        # Não deve levantar exceção

    @patch("helpers.import_pdf.extractors.detector.fitz")
    def test_validate_all_pages_with_consistent_format(self, mock_fitz):
        """Todas as páginas com mesmo formato devem passar validação."""
        # Configurar mock de PDF com 3 páginas, todas two_column
        mock_pdf = MagicMock()
        mock_pdf.__len__.return_value = 3
        mock_fitz.open.return_value = mock_pdf

        def make_two_column_page():
            page = MagicMock()
            page.get_images.return_value = [
                (1, 0, 100, 100, 8, "DeviceRGB", "", "img1", "DCTDecode"),
                (2, 0, 100, 100, 8, "DeviceRGB", "", "img2", "DCTDecode"),
            ]
            page.get_text.return_value = (
                "Código Fiscalização: NC001\nCódigo Fiscalização: NC002\n"
            )
            bbox1 = MagicMock()
            bbox1.y0 = 100
            bbox2 = MagicMock()
            bbox2.y0 = 300
            page.get_image_bbox.side_effect = [bbox1, bbox2]
            return page

        mock_pdf.load_page.side_effect = [
            make_two_column_page(),
            make_two_column_page(),
            make_two_column_page(),
        ]

        # Deve detectar formato e validar sem erros
        format_type = FormatDetector.detect("fake_path.pdf")

        assert format_type == "two_column"
        # Não deve levantar exceção
