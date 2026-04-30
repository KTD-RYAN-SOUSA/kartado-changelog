"""
Exceções customizadas para importação de PDFs DIN.

Este módulo define exceções específicas do domínio de importação
de PDFs DIN, facilitando tratamento de erros e feedback ao usuário.
"""


class UnsupportedPDFFormatException(Exception):
    """PDF com formato não suportado."""

    def __init__(
        self,
        message="Não foi possível identificar o formato do arquivo. Verifique e tente novamente.",
    ):
        self.message = message
        super().__init__(self.message)


class MixedPDFFormatException(Exception):
    """PDF com páginas de formatos mistos (1+2 colunas)."""

    def __init__(
        self,
        message="Não foi possível identificar o formato do arquivo. Verifique e tente novamente.",
    ):
        self.message = message
        super().__init__(self.message)


class PageLimitExceededException(Exception):
    """PDF excede o limite de páginas permitido."""

    def __init__(self, limit, actual):
        self.limit = limit
        self.actual = actual
        self.message = f"Você excedeu o limite de {limit} páginas por importação. Diminua a quantidade de páginas do arquivo PDF e tente novamente."
        super().__init__(self.message)
