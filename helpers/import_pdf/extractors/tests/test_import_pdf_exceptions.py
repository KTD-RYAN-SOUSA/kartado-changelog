import pytest

from helpers.import_pdf.exceptions import (
    MixedPDFFormatException,
    PageLimitExceededException,
    UnsupportedPDFFormatException,
)


class TestImportPDFExceptions:
    """Testes para exceções customizadas do módulo de importação DIN."""

    def test_unsupported_pdf_format_exception_default_message(self):
        """UnsupportedPDFFormatException deve ter mensagem padrão user-friendly."""
        exception = UnsupportedPDFFormatException()

        expected_message = "Não foi possível identificar o formato do arquivo. Verifique e tente novamente."
        assert str(exception) == expected_message
        assert isinstance(exception, Exception)

    def test_unsupported_pdf_format_exception_custom_message(self):
        """UnsupportedPDFFormatException deve aceitar mensagem customizada."""
        message = "Formato não suportado"
        exception = UnsupportedPDFFormatException(message)

        assert str(exception) == message
        assert isinstance(exception, Exception)

    def test_unsupported_pdf_format_exception_can_be_raised(self):
        """UnsupportedPDFFormatException deve poder ser levantada e capturada."""
        with pytest.raises(UnsupportedPDFFormatException) as exc_info:
            raise UnsupportedPDFFormatException("Teste")

        assert "Teste" in str(exc_info.value)

    def test_mixed_pdf_format_exception_default_message(self):
        """MixedPDFFormatException deve ter mensagem padrão user-friendly."""
        exception = MixedPDFFormatException()

        expected_message = "Não foi possível identificar o formato do arquivo. Verifique e tente novamente."
        assert str(exception) == expected_message
        assert isinstance(exception, Exception)

    def test_mixed_pdf_format_exception_custom_message(self):
        """MixedPDFFormatException deve aceitar mensagem customizada."""
        message = "PDF com formatos mistos"
        exception = MixedPDFFormatException(message)

        assert str(exception) == message
        assert isinstance(exception, Exception)

    def test_mixed_pdf_format_exception_can_be_raised(self):
        """MixedPDFFormatException deve poder ser levantada e capturada."""
        with pytest.raises(MixedPDFFormatException) as exc_info:
            raise MixedPDFFormatException("Página 2 diferente")

        assert "Página 2 diferente" in str(exc_info.value)

    def test_page_limit_exceeded_exception_creation(self):
        """PageLimitExceededException deve ser criada com limite e valor atual."""
        exception = PageLimitExceededException(limit=50, actual=75)

        assert exception.limit == 50
        assert exception.actual == 75
        expected_message = "Você excedeu o limite de 50 páginas por importação. Diminua a quantidade de páginas do arquivo PDF e tente novamente."
        assert str(exception) == expected_message
        assert isinstance(exception, Exception)

    def test_page_limit_exceeded_exception_can_be_raised(self):
        """PageLimitExceededException deve poder ser levantada e capturada."""
        with pytest.raises(PageLimitExceededException) as exc_info:
            raise PageLimitExceededException(limit=100, actual=150)

        assert "100 páginas" in str(exc_info.value)
        assert exc_info.value.limit == 100
        assert exc_info.value.actual == 150

    def test_exceptions_inherit_from_exception(self):
        """Todas as exceções devem herdar de Exception."""
        assert issubclass(UnsupportedPDFFormatException, Exception)
        assert issubclass(MixedPDFFormatException, Exception)
        assert issubclass(PageLimitExceededException, Exception)

    def test_exceptions_are_distinct(self):
        """Cada exceção deve ser uma classe distinta."""
        exc1 = UnsupportedPDFFormatException("test")
        exc2 = MixedPDFFormatException("test")
        exc3 = PageLimitExceededException(limit=10, actual=20)

        assert type(exc1) != type(exc2)
        assert type(exc2) != type(exc3)
        assert type(exc1) != type(exc3)
