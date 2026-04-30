from typing import Any, Dict, List

import fitz

from .base import DINExtractor


class DINOneColumnExtractor(DINExtractor):
    LOGO_THRESHOLD_Y = 50

    def extract_images(self, reportings: List[Dict[str, Any]]) -> List[str]:
        pdf = fitz.open(self.pdf_path)
        pages = len(pdf)
        image_codes = []

        reporting_idx = 0
        current_nc = None
        nc_img_counts = {}

        for page_num in range(pages):
            page = pdf.load_page(page_num)

            # Detectar se a página tem "Código Fiscalização:"
            header_rects = page.search_for("Código Fiscalização:")

            if header_rects:
                # Nova NC: avançar para o próximo reporting
                if reporting_idx < len(reportings):
                    current_nc = reportings[reporting_idx].get("supervision_code", "")
                    reporting_idx += 1
                else:
                    current_nc = None

            # Página sem reportings
            if not current_nc:
                continue

            # Y mínimo para coleta de imagens:
            # - Página com header: imagens abaixo do "Código Fiscalização:"
            # - Página de continuação (sem header): todas as imagens da página
            header_y = header_rects[0].y1 if header_rects else 0

            # Coletar imagens abaixo do header_y, ordenadas por posição vertical
            page_images = [image[-2] for image in page.get_images()]
            img_bboxes = [page.get_image_bbox(img) for img in page_images]
            min_y = max(header_y, self.LOGO_THRESHOLD_Y)
            img_bboxes = [bbox for bbox in img_bboxes if bbox.y0 >= min_y]
            img_bboxes = sorted(img_bboxes, key=lambda x: x.y0)

            img_matrix = fitz.Matrix(8, 8)
            for bbox in img_bboxes:
                pixmap = page.get_pixmap(matrix=img_matrix, clip=fitz.IRect(bbox))
                img_index = nc_img_counts.get(current_nc, 0)
                filename = f"{current_nc}_{img_index}.png"
                nc_img_counts[current_nc] = img_index + 1
                pixmap.save(self.temp_path + filename)
                image_codes.append(filename)

        return image_codes
