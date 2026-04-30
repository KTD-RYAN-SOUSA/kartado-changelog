from typing import Optional

import fitz

from helpers.import_pdf.exceptions import (
    MixedPDFFormatException,
    PageLimitExceededException,
    UnsupportedPDFFormatException,
)


class FormatDetector:
    # Threshold para distinguir 1 coluna de 2 colunas por spread horizontal (em pixels)
    TWO_COLUMN_THRESHOLD = 150

    # Limite de paginas por importacao (CA-06)
    PAGE_LIMIT = 150

    # Threshold para ignorar logos e headers no topo da pagina (em pixels)
    LOGO_THRESHOLD_Y = 50

    # Imagens com largura relativa < threshold sao consideradas de meia coluna (two_column)
    TWO_COLUMN_IMAGE_WIDTH_RATIO = 0.6

    @staticmethod
    def detect(pdf_path: str) -> str:
        pdf = fitz.open(pdf_path)

        if len(pdf) == 0:
            raise UnsupportedPDFFormatException()

        if len(pdf) > FormatDetector.PAGE_LIMIT:
            raise PageLimitExceededException(
                limit=FormatDetector.PAGE_LIMIT, actual=len(pdf)
            )

        # Analisar todas as paginas e coletar o formato detectado em cada uma
        page_formats = []
        has_before_code_fiscalization = (
            False  # Se ja encontramos pelo menos 1 pagina com Código Fiscalização
        )

        for page_num in range(len(pdf)):
            page_format = FormatDetector._detect_page_format(pdf, page_num)

            if page_format is None:
                # Pagina sem imagens de conteudo — tolerada para ambos os formatos:
                # - Pode ser pagina de continuacao sem imagens (ex: somente texto, ou pagina em branco entre NC e continuacao)
                # - Pode ser uma página de duas colunas sem imagens (ex: somente texto)
                continue

            if page_format == "continuation":
                # Pagina de continuacao so e valida se ja houve uma pagina com Código Fiscalização antes
                if not has_before_code_fiscalization:
                    # Pagina de continuacao sem nenhuma pagina anterior com Código Fiscalização é suspeita — é um formato desconhecido ou PDF mal formado
                    raise UnsupportedPDFFormatException()
                # Pagina de continuacao valida
                page_formats.append("one_column")
                continue

            has_before_code_fiscalization = True
            page_formats.append(page_format)

        if not page_formats:
            # Nenhuma pagina do PDF contem imagens de conteudo
            raise UnsupportedPDFFormatException()

        # Verificar se todas as paginas possuem o mesmo formato
        unique_formats = set(page_formats)
        if len(unique_formats) > 1:
            # PDF com formatos mistos detectados — provavelmente mal formado ou com layout inconsistente, não podemos processar
            raise MixedPDFFormatException()

        detected_format = page_formats[0]
        return detected_format

    @staticmethod
    def _detect_page_format(pdf: fitz.Document, page_num: int) -> Optional[str]:
        """
        Detecta o formato de uma unica pagina.

        Retorna 'two_column', 'one_column', 'continuation' ou None (se a pagina nao tiver imagens de conteudo).
        imagens de conteudo (sem imagens ou somente headers/logos).

        Logica de deteccao:
        - 2 ou 3 "Codigo Fiscalizacao:" na pagina → two_column (certeza)
        - 0 "Codigo Fiscalizacao:" mas com imagens → one_column (fotos em uma página de continuacao, sem Código Fiscalização)
        - 1 "Codigo Fiscalizacao:" → desempate por spread X e largura das imagens
        """
        page = pdf.load_page(page_num)
        img_list = page.get_images()

        if not img_list:
            return None

        page_images = [image[-2] for image in img_list]  # -2 is the image name

        # Contar quantos apontamentos ("Código Fiscalização:") existem na pagina
        text = page.get_text("text")
        code_fiscalization_count = text.count("Código Fiscalização:")

        # Paginas de continuacao: 0 "Código Fiscalização:" mas com imagens de conteudo (fotos do "Código Fiscalização" anterior)
        # Nestas paginas as imagens aparecem mais acima (sem o espaco ocupado pelo header do "Código Fiscalização")
        # por isso nao passariam pelo LOGO_THRESHOLD_Y — usamos threshold menor so para o logo
        if code_fiscalization_count == 0:
            continuation_bboxes = []
            for img in page_images:
                bbox = page.get_image_bbox(img)
                if bbox.y0 < FormatDetector.LOGO_THRESHOLD_Y:
                    # Imagem no topo da pagina, provavelmente um logo/header residual — ignorada
                    continue
                continuation_bboxes.append(bbox)

            if continuation_bboxes:
                # Imagens de conteudo presentes mas nenhum "Código Fiscalização:" → pagina de continuacao
                return "continuation"
            return None

        # Coletar bboxes das imagens de conteudo (excluindo headers/logos)
        content_bboxes = []

        for img in page_images:
            bbox = page.get_image_bbox(img)

            if bbox.y0 < FormatDetector.LOGO_THRESHOLD_Y:
                # Imagem no topo da pagina, provavelmente um logo/header — ignorada
                continue

            content_bboxes.append(bbox)

        if not content_bboxes:
            return None

        # 2 ou 3 "Código Fiscalização:" → definitivamente two_column
        if code_fiscalization_count >= 2:
            # Página com múltiplos "Código Fiscalização:", certamete é formato two_column
            return "two_column"

        # 1 "Código Fiscalização:" → ambiguo; desempatar por spread X e largura relativa das imagens
        x_positions = [bbox.x0 for bbox in content_bboxes]
        page_width = page.rect.width

        if FormatDetector._has_two_columns(x_positions, content_bboxes, page_width):
            # Spread horizontal grande ou imagens de meia coluna → formato two_column
            return "two_column"

        # Spread horizontal pequeno e imagens ocupando quase toda a largura → formato one_column
        return "one_column"

    @staticmethod
    def _has_two_columns(
        x_positions: list,
        bboxes: list = None,
        page_width: float = None,
    ) -> bool:
        """
        Determina se as imagens de uma pagina indicam o formato de 2 colunas.

        Usado apenas como desempate quando ha exatamente 1 "Código Fiscalização" na pagina.

        Considera two_column se:
        - O spread horizontal (max X - min X) for maior que o threshold, indicando
          imagens lado a lado em duas colunas; OU
        - Alguma imagem tiver largura relativa menor que TWO_COLUMN_IMAGE_WIDTH_RATIO,
          indicando que a imagem ocupa apenas meia pagina (meia coluna).
        """
        if not x_positions:
            return False

        # Criterio 1: imagens em posicoes X muito diferentes (colunas lado a lado)
        x_spread = max(x_positions) - min(x_positions)
        if x_spread > FormatDetector.TWO_COLUMN_THRESHOLD:
            return True

        # Criterio 2: alguma imagem ocupa menos de 60% da largura da pagina (meia coluna)
        if bboxes and page_width:
            for bbox in bboxes:
                img_width_ratio = (bbox.x1 - bbox.x0) / page_width
                if img_width_ratio < FormatDetector.TWO_COLUMN_IMAGE_WIDTH_RATIO:
                    # Imagem ocupa menos de 60% da largura da pagina, indicando formato two_column
                    return True

        return False
