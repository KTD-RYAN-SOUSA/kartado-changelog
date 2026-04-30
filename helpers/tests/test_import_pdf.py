from collections import OrderedDict
from typing import Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest

from helpers.import_pdf.exceptions import (
    MixedPDFFormatException,
    UnsupportedPDFFormatException,
)
from helpers.import_pdf.extractors.factory import DINExtractorFactory
from helpers.import_pdf.read_pdf import ImportPDF

pytestmark = pytest.mark.django_db


class TestImportPDF:

    PDF_TEXT_FORMAT = """
Código Fiscalização: {}
Concessionária: {}
Lote: {}
Rodovia (SP): {}
Rodovia: {}
KM+MTS - Inicial: {}
KM+MTS - Final: {}
Sentido: {}
Atividade: {}
Observação: {}
Constatação - {}
Data Limite para Reparo - {}
"01/01/2024"
1
"""

    TEST_ENTRY_1 = OrderedDict(
        {
            "supervision_code": "999999",
            "dealership": "Concessionária 1",
            "lot": "0",
            "road_name": "SP 100",
            "road": "ROD TESTE",
            "km": "012 + 345",
            "end_km": "456 + 789",
            "direction": "Sul",
            "activity": "Reparo e reposição de cerca",
            "note": "",
            "found_at": "01/01/2024",
            "due_at": "02/01/2024",
        }
    )

    TEST_ENTRY_2 = OrderedDict(
        {
            "supervision_code": "999998",
            "dealership": "Concessionária 2",
            "lot": "7",
            "road_name": "SP 21",
            "road": "ROD TESTE 21",
            "km": "111 + 111",
            "end_km": "222 + 222",
            "direction": "Norte",
            "activity": "Varrição",
            "note": "Observações importantes",
            "found_at": "22/01/2024",
            "due_at": "01/01/2025",
        }
    )

    @pytest.fixture
    def import_pdf_mock(_):
        user = Mock()
        pdf_import = Mock()
        user.uuid = ""
        pdf_import.pk = ""
        pdf_import.company_id = ""
        pdf_import.company = None
        pdf_import.form_data = {}
        import_pdf = ImportPDF(pdf_import, user)
        import_pdf.road = None
        return import_pdf

    @classmethod
    def extract(
        cls, import_pdf: ImportPDF, entries_data: List[Dict], pdf_text_format: str
    ) -> bool:
        """Extracts reporting data from text string.
        The text string is simulated by concatenating
        the texts resulting from inserting each entry
        data into pdf_text_format.
        """
        entries_texts = [
            pdf_text_format.format(*list(entry_data.values()))
            for entry_data in entries_data
        ]
        pdf_text = "\n".join(entries_texts)

        with patch.object(ImportPDF, "refine_entries", Mock()), patch(
            "helpers.import_pdf.read_pdf.extract_text", Mock(return_value=pdf_text)
        ):
            extracted_data = import_pdf.extract_reportings()
        return extracted_data

    @classmethod
    def compare(cls, extracted_data: dict, entries_data: List[Dict]) -> bool:
        """Compares the "raw" extracted values,
        before refinement and form_data processing,
        returning whether all reporting fields were
        collected from the text string.
        """

        all_collected = True
        for i, extracted_entry in enumerate(extracted_data):
            test_entry = entries_data[i]
            for field in test_entry:
                all_collected &= extracted_entry[field].strip() == test_entry[field]
        return all_collected

    def test_extracted_entries(self, import_pdf_mock: ImportPDF):
        """Tests extracting reporting data from pdf
        Pdf extracted text string is simulated,
        Tests the "raw" extracted values,
        before refinement and form_data processing

        Uses "KM+MTS - Inicial:" and "KM+MTS - Final:"
        as km and end_km headings
        """

        test_entries = [TestImportPDF.TEST_ENTRY_1, TestImportPDF.TEST_ENTRY_2]
        extracted_data = TestImportPDF.extract(
            import_pdf_mock, test_entries, TestImportPDF.PDF_TEXT_FORMAT
        )
        assert TestImportPDF.compare(extracted_data, test_entries) is True

    def test_extracted_entries_with_alternative_heading(
        self, import_pdf_mock: ImportPDF
    ):
        """Tests extracting reporting data from pdf
        Pdf extracted text string is simulated,
        Tests the "raw" extracted values,
        before refinement and form_data processing

        Uses "Km+m - Inicial:" and "Km+m - Final:"
        as km and end_km headings
        """

        pdf_text_format = TestImportPDF.PDF_TEXT_FORMAT
        pdf_text_format.replace("KM+MTS - Inicial:", "Km+m - Inicial:")
        pdf_text_format.replace("KM+MTS - Final:", "Km+m - Final:")

        test_entries = [TestImportPDF.TEST_ENTRY_1, TestImportPDF.TEST_ENTRY_2]

        extracted_data = TestImportPDF.extract(
            import_pdf_mock, test_entries, TestImportPDF.PDF_TEXT_FORMAT
        )
        assert TestImportPDF.compare(extracted_data, test_entries) is True

    def test_extracted_missing_entries(self, import_pdf_mock: ImportPDF):
        """Tests extracting reporting data from pdf
        Pdf extracted text string is simulated,
        Tests the "raw" extracted values,
        before refinement and form_data processing

        Checks whether, during refinement phase,
        missing entry is identified and it's heading
        is appended to error field.
        """

        pdf_text_format = TestImportPDF.PDF_TEXT_FORMAT
        pdf_text_format.replace("Rodovia (SP):", "")
        entry = TestImportPDF.TEST_ENTRY_1.copy()
        entry["road_name"] = ""

        test_entries = [entry]

        extracted_data = TestImportPDF.extract(
            import_pdf_mock, test_entries, pdf_text_format
        )
        assert TestImportPDF.compare(extracted_data, test_entries) is True
        with patch.object(ImportPDF, "refine_direction", lambda _, d: d), patch.object(
            ImportPDF, "refine_notes", lambda *args: "Note"
        ):
            import_pdf_mock.refine_entries(extracted_data)
        column_errors = extracted_data[0]["column_errors"]
        assert "Rodovia (SP):" in column_errors

    def test_extracted_missing_entries_multiple_heading(
        self, import_pdf_mock: ImportPDF
    ):
        """Tests extracting reporting data from pdf
        Pdf extracted text string is simulated,
        Tests the "raw" extracted values,
        before refinement and form_data processing

        Checks whether, during refinement phase,
        missing entries are identified
        correctly for multiple heading field, and
        all possible headings are appended to error field.
        """

        pdf_text_format = TestImportPDF.PDF_TEXT_FORMAT
        pdf_text_format.replace("KM+MTS - Inicial:", "")
        entry = TestImportPDF.TEST_ENTRY_1.copy()
        entry["km"] = ""

        test_entries = [entry]

        extracted_data = TestImportPDF.extract(
            import_pdf_mock, test_entries, pdf_text_format
        )
        assert TestImportPDF.compare(extracted_data, test_entries) is True
        with patch.object(ImportPDF, "refine_direction", lambda _, d: d), patch.object(
            ImportPDF, "refine_road_name", lambda _, r: r
        ), patch.object(ImportPDF, "refine_notes", lambda *args: "Note"):
            import_pdf_mock.refine_entries(extracted_data)

        column_errors = extracted_data[0]["column_errors"]
        assert (
            "KM+MTS - Inicial:" in column_errors and "Km+m - Inicial:" in column_errors
        )


class TestImportPDFIntegration:
    """Integration tests for ImportPDF with DINExtractorFactory"""

    @pytest.fixture
    def import_pdf_mock(self):
        user = Mock()
        pdf_import = Mock()
        user.uuid = ""
        pdf_import.pk = ""
        pdf_import.company_id = ""
        pdf_import.company = None
        pdf_import.form_data = {}
        import_pdf = ImportPDF(pdf_import, user)
        import_pdf.road = None
        import_pdf.file_name = "/tmp/test.pdf"
        return import_pdf

    @pytest.fixture
    def mock_reportings(self):
        return [
            {"supervision_code": "123456"},
            {"supervision_code": "789012"},
            {"supervision_code": "345678"},
        ]

    def test_get_data_with_two_column_format(self, import_pdf_mock, mock_reportings):
        """Test get_data() successfully uses DINTwoColumnExtractor"""

        with patch.object(
            ImportPDF, "extract_reportings", return_value=mock_reportings
        ), patch.object(DINExtractorFactory, "create") as mock_factory:
            # Setup mock extractor
            mock_extractor = MagicMock()
            mock_extractor.extract_images.return_value = {
                "123456": {"url": "http://test.com/123456.png", "uuid": "uuid-1"},
                "789012": {"url": "http://test.com/789012.png", "uuid": "uuid-2"},
            }
            mock_factory.return_value = (mock_extractor, "two_column")

            result = import_pdf_mock.get_data()

            # Verify factory was called with correct path
            mock_factory.assert_called_once_with("/tmp/test.pdf")

            # Verify extractor was called with reportings
            mock_extractor.extract_images.assert_called_once_with(mock_reportings)

            # Verify result structure
            assert "reportings" in result
            assert "images" in result
            assert result["reportings"] == mock_reportings
            assert len(result["images"]) == 2

    def test_get_data_with_one_column_format(self, import_pdf_mock, mock_reportings):
        """Test get_data() successfully uses DINOneColumnExtractor"""

        with patch.object(
            ImportPDF, "extract_reportings", return_value=mock_reportings
        ), patch.object(DINExtractorFactory, "create") as mock_factory:
            # Setup mock extractor
            mock_extractor = MagicMock()
            mock_extractor.extract_images.return_value = {
                "123456": {"url": "http://test.com/123456.png", "uuid": "uuid-1"},
            }
            mock_factory.return_value = (mock_extractor, "one_column")

            result = import_pdf_mock.get_data()

            # Verify factory was called
            mock_factory.assert_called_once_with("/tmp/test.pdf")

            # Verify extractor was called
            mock_extractor.extract_images.assert_called_once_with(mock_reportings)

            # Verify result
            assert "images" in result
            assert len(result["images"]) == 1

    def test_get_data_with_unsupported_format(self, import_pdf_mock, mock_reportings):
        """Test get_data() propaga UnsupportedPDFFormatException para o chamador"""

        with patch.object(
            ImportPDF, "extract_reportings", return_value=mock_reportings
        ), patch.object(
            DINExtractorFactory,
            "create",
            side_effect=UnsupportedPDFFormatException("Unsupported format"),
        ):
            with pytest.raises(UnsupportedPDFFormatException):
                import_pdf_mock.get_data()

    def test_get_data_with_mixed_format(self, import_pdf_mock, mock_reportings):
        """Test get_data() propaga MixedPDFFormatException para o chamador"""

        with patch.object(
            ImportPDF, "extract_reportings", return_value=mock_reportings
        ), patch.object(
            DINExtractorFactory,
            "create",
            side_effect=MixedPDFFormatException("Mixed format detected"),
        ):
            with pytest.raises(MixedPDFFormatException):
                import_pdf_mock.get_data()

    def test_get_data_with_unexpected_error(self, import_pdf_mock, mock_reportings):
        """Test get_data() handles unexpected errors gracefully"""

        with patch.object(
            ImportPDF, "extract_reportings", return_value=mock_reportings
        ), patch.object(
            DINExtractorFactory, "create", side_effect=Exception("Unexpected error")
        ), patch(
            "helpers.import_pdf.read_pdf.sentry_sdk"
        ) as mock_sentry:
            result = import_pdf_mock.get_data()

            # Should capture exception in Sentry
            assert mock_sentry.capture_exception.called

            # Should return data with empty images
            assert "images" in result
            assert result["images"] == {}

    def test_get_data_with_no_reportings(self, import_pdf_mock):
        """Test get_data() returns empty dict when no reportings"""

        with patch.object(
            ImportPDF, "extract_reportings", return_value=[]
        ), patch.object(DINExtractorFactory, "create") as mock_factory:
            mock_factory.return_value = (MagicMock(), "two_column")
            result = import_pdf_mock.get_data()

            # Should return empty dict
            assert result == {}
