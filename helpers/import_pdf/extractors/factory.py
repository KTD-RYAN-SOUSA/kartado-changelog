from helpers.import_pdf.exceptions import UnsupportedPDFFormatException

from .detector import FormatDetector
from .one_column import DINOneColumnExtractor
from .two_column import DINTwoColumnExtractor


class DINExtractorFactory:
    REGISTRY = {
        "one_column": DINOneColumnExtractor,
        "two_column": DINTwoColumnExtractor,
    }

    @staticmethod
    def create(pdf_path: str, company=None):
        format_type = FormatDetector.detect(pdf_path)

        extractor_cls = DINExtractorFactory.REGISTRY.get(format_type)

        if not extractor_cls:
            raise UnsupportedPDFFormatException()

        return extractor_cls(pdf_path, company=company), format_type
