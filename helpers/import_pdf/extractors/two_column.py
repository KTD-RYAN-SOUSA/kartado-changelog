import logging
from typing import Any, Dict, List

import fitz

from .base import DINExtractor


class DINTwoColumnExtractor(DINExtractor):
    def extract_images(self, reportings: List[Dict[str, Any]]) -> List[str]:
        pdf = fitz.open(self.pdf_path)
        pages = len(pdf)
        image_codes = []

        for page_num in range(pages):
            page = pdf.load_page(page_num)

            # Get images positions
            page_images = [
                image[-2] for image in page.get_images()  # -2 is the image name
            ]
            img_bboxes = [page.get_image_bbox(image) for image in page_images]
            img_bboxes = sorted(img_bboxes, key=lambda x: x.y0)

            # Get supervision codes
            r_in_page = reportings[page_num * 3 : (page_num * 3) + 3]
            supervision_codes = [r.get("supervision_code", "") for r in r_in_page]

            # Crop images from page
            img_matrix = fitz.Matrix(8, 8)
            for bbox in img_bboxes:
                # NOTE: Assumes there's a code for every image (even if the image is missing)
                # NOTE: If there are more than 3 images, it logs a warning and ignores the extra ones
                try:
                    if int(bbox.y0) in range(176, 200):
                        code = supervision_codes[0]
                    elif int(bbox.y0) in range(413, 440):
                        code = supervision_codes[1]
                    elif int(bbox.y0) in range(656, 680):
                        code = supervision_codes[2]
                    else:
                        logging.warning(
                            "Image was found outside fixed bounds. Ignoring..."
                        )
                        continue
                except IndexError:
                    logging.warning(
                        "Couldn't find code for fixed bound image. Ignoring..."
                    )
                    continue

                pixmap = page.get_pixmap(matrix=img_matrix, clip=fitz.IRect(bbox))
                filename = code.replace("Código Fiscalização: ", "").strip() + ".png"
                pixmap.save(self.temp_path + filename)
                image_codes.append(filename)

        return image_codes
