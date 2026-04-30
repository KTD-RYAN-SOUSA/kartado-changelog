"""
Classe base abstrata para extractors DIN.

Define interface comum para diferentes formatos de PDFs DIN.
"""

from abc import ABC, abstractmethod
from typing import List

import fitz


class DINExtractor(ABC):
    temp_path = "/tmp/pdf_import/"

    def __init__(self, pdf_path: str, company=None):
        self.pdf_path = pdf_path
        self.pdf = fitz.open(pdf_path)
        self.company = company

    @abstractmethod
    def extract_images(self) -> List[str]:
        """
        Extrai imagens do PDF e retorna lista de filenames.

        Este método deve ser implementado por subclasses com lógica
        específica para cada formato (1 coluna, 2 colunas, etc.).

        Returns:
            List[str]: Lista de filenames das imagens extraídas

        Raises:
            NotImplementedError: Se subclasse não implementar
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} deve implementar extract_images()"
        )
