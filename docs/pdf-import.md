# Importação de PDF DIN ARTESP

## Visão Geral

Sistema de importação multi-formato para PDFs de Não Conformidades (NC) do padrão DIN ARTESP. Detecta automaticamente o formato do PDF (1 coluna ou 2 colunas) e aplica o extrator apropriado para extrair dados tabulares e imagens.

**Épico de Referência**: KTD-10265
**Implementação**: `helpers/import_pdf/extractors/`
**Testes**: `tests/import_pdf/extractors/`

## Arquitetura

### Padrões de Design Utilizados

#### 1. Factory Pattern (DINExtractorFactory)
Responsável por criar a instância correta do extrator baseado no formato detectado.

```python
from helpers.import_pdf.extractors.factory import DINExtractorFactory

# Factory cria extrator e detecta formato automaticamente
extractor, pdf_format = DINExtractorFactory.create(pdf_path, company=company)
# pdf_format será "one_column" ou "two_column"

# Extrator recebe reportings e retorna lista de filenames salvos
image_filenames = extractor.extract_images(reportings)
```

**Localização**: `helpers/import_pdf/extractors/factory.py`

**Assinatura**: `create(pdf_path: str, company=None) -> Tuple[DINExtractor, str]`

#### 2. Strategy Pattern (Extractors)
Diferentes estratégias de extração para cada formato de PDF.

- `DINOneColumnExtractor` - Para PDFs com 1 coluna
- `DINTwoColumnExtractor` - Para PDFs com 2 colunas

**Localização**: `helpers/import_pdf/extractors/one_column.py`, `two_column.py`

#### 3. Template Method Pattern (DINExtractor)
Classe base abstrata que define o fluxo de extração comum.

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class DINExtractor(ABC):
    temp_path = "/tmp/pdf_import/"

    def __init__(self, pdf_path: str, company=None):
        self.pdf_path = pdf_path
        self.pdf = fitz.open(pdf_path)
        self.company = company

    @abstractmethod
    def extract_images(self, reportings: List[Dict[str, Any]]) -> List[str]:
        """
        Extrai imagens do PDF e salva em disco.
        Implementado por cada extrator específico.

        Args:
            reportings: Lista de dicionários com dados dos apontamentos

        Returns:
            List[str]: Lista de filenames das imagens salvas
        """
        raise NotImplementedError
```

**Localização**: `helpers/import_pdf/extractors/base.py`

### Componentes Principais

```
helpers/import_pdf/extractors/
├── __init__.py              # Exports públicos
├── base.py                  # DINExtractor (classe base abstrata)
├── factory.py               # DINExtractorFactory
├── detector.py              # FormatDetector
├── one_column.py            # DINOneColumnExtractor
├── two_column.py            # DINTwoColumnExtractor
└── exceptions.py            # Exceções customizadas
```

## Formatos de PDF Suportados

### 1. Formato de 1 Coluna

**Características**:
- Uma única coluna de dados por página
- Suporta várias fotos por NC
- Pode ter page breaks (NC dividida em múltiplas páginas)
- Header identificador: `"Código Fiscalização: XXXXX"`

**Estrutura**:
```
┌─────────────────────────┐
│ Código Fiscalização: 123│
├─────────────────────────┤
│ Campo 1: Valor          │
│ Campo 2: Valor          │
│ ...                     │
│ [Foto 1] [Foto 2]       │
│ [Foto 3] [Foto 4]       │
└─────────────────────────┘
```

**Posições Y fixas**: Não possui (extração dinâmica baseada em texto)

### 2. Formato de 2 Colunas

**Características**:
- Até 3 NC por página
- **1 foto por NC** (nome da imagem: {nc}.png)
- Sem page breaks (NC sempre em uma página)
- Layout fixo e previsível

**Estrutura**:
```
┌────────────┬────────────┐
│ NC 1       │ NC 2       │
├────────────┼────────────┤
│ Campo: Val │ Campo: Val │
│ Campo: Val │ Campo: Val │
│ [Foto]     │ [Foto]     │
└────────────┴────────────┘
```

**Posições Y fixas** (importantes para extração):
- Header superior: Y 176-200
- Header central: Y 413-440
- Header inferior: Y 656-680

## Diferenças Críticas entre Formatos

### ⚠️ IMPORTANTE: Headers NÃO são Idênticos

Durante a implementação do KTD-10265, assumimos inicialmente que os headers (campos do cabeçalho) eram idênticos entre os formatos. **Isso estava ERRADO**.

A **ordem das colunas é diferente** entre formatos, necessitando o mapeamento `PROPERTY_TO_HEADING_ONE_COLUMN`.

#### Comparação Real dos Headers

| Campo (Property) | 2 Colunas | 1 Coluna | Posição 2-col | Posição 1-col |
|-----------------|-----------|----------|---------------|---------------|
| Código Fiscalização | ✅ | ✅ | 1 | 1 |
| km Inicial | ✅ | ✅ | 2 | 3 |
| km Final | ✅ | ✅ | 3 | 4 |
| Pista | ✅ | ✅ | 4 | 2 |
| Faixa | ✅ | ✅ | 5 | 5 |
| Data da Fiscalização | ✅ | ✅ | 6 | 6 |
| ... | ... | ... | ... | ... |

**Solução Implementada**: `PROPERTY_TO_HEADING_ONE_COLUMN` em `helpers/import_pdf/read_pdf.py:279`

```python
PROPERTY_TO_HEADING_ONE_COLUMN = {
    "occurrence_code": "Código Fiscalização",
    "initial_km": "km Inicial",
    "final_km": "km Final",
    "track": "Pista",
    # Mapeamento completo da ordem correta
}
```

### Tabela Comparativa Completa

| Aspecto | 1 Coluna | 2 Colunas |
|---------|----------|-----------|
| **Layout** | Dinâmico | Fixo |
| **NCs por página** | 1 | 3 |
| **Fotos por NC** | (variável) | **1** |
| **Page breaks** | ✅ Sim | ❌ Não |
| **Detecção** | Header "Código Fiscalização" | Posições Y fixas |
| **Ordem de headers** | **DIFERENTE** | Padrão |
| **Extração** | Baseada em texto | Baseada em posição |
| **Complexidade** | Alta | Média |

## Detecção de Formato (FormatDetector)

### Como Funciona

O `FormatDetector` analisa o PDF e determina automaticamente o formato através de análise sofisticada de cada página.

**Localização**: `helpers/import_pdf/extractors/detector.py`

**Constantes importantes**:
```python
TWO_COLUMN_THRESHOLD = 150  # Spread horizontal mínimo (pixels)
PAGE_LIMIT = X  # Limite de páginas por importação
LOGO_THRESHOLD_Y = 50  # Ignora logos/headers no topo
TWO_COLUMN_IMAGE_WIDTH_RATIO = 0.6  # Largura relativa para detectar meia coluna
```

**Algoritmo de detecção por página**:
1. Conta quantos "Código Fiscalização:" aparecem na página:
   - **2 ou 3 ocorrências** → definitivamente `two_column`
   - **0 ocorrências com imagens** → página de continuação (`one_column`)
   - **1 ocorrência** → desempate por critérios abaixo

2. **Desempate** (quando há exatamente 1 "Código Fiscalização:"):
   - Analisa spread horizontal das imagens (diferença entre posições X)
   - Verifica largura relativa das imagens
   - Se spread > 150px OU largura < 60% da página → `two_column`
   - Caso contrário → `one_column`

3. **Validação global**:
   - Verifica se todas as páginas têm o mesmo formato
   - Ignora páginas sem imagens de conteúdo
   - Valida páginas de continuação (só válidas após página com "Código Fiscalização:")

**Exemplo de uso**:
```python
from helpers.import_pdf.extractors.detector import FormatDetector

# Retorna "one_column" ou "two_column"
pdf_format = FormatDetector.detect(pdf_path)

if pdf_format == "one_column":
    print("PDF de 1 coluna detectado")
elif pdf_format == "two_column":
    print("PDF de 2 colunas detectado")
```

**Assinatura**: `detect(pdf_path: str) -> str`

### Exceções Lançadas

#### 1. `UnsupportedPDFFormatException`
Lançada quando:
- PDF está vazio (0 páginas)
- Nenhuma página contém imagens de conteúdo
- Página de continuação sem página anterior com "Código Fiscalização:"

#### 2. `MixedPDFFormatException`
Lançada quando:
- PDF contém páginas com formatos diferentes (ex: páginas 1-3 são `two_column`, página 4 é `one_column`)

#### 3. `PageLimitExceededException`
Lançada quando:
- PDF excede o limite de 50 páginas

**Exemplo de tratamento**:
```python
from helpers.import_pdf.exceptions import (
    UnsupportedPDFFormatException,
    MixedPDFFormatException,
    PageLimitExceededException
)

try:
    pdf_format = FormatDetector.detect(pdf_path)
except UnsupportedPDFFormatException:
    # PDF não é formato DIN ARTESP válido
    pass
except MixedPDFFormatException:
    # PDF tem formatos mistos (inconsistente)
    pass
except PageLimitExceededException as e:
    # PDF tem mais de 50 páginas
    print(f"Limite: {e.limit}, Atual: {e.actual}")
```

## Extractors

### DINOneColumnExtractor

**Responsabilidade**: Extrair dados de PDFs no formato de 1 coluna.

**Localização**: `helpers/import_pdf/extractors/one_column.py`

**Características**:
- Extração dinâmica baseada em texto
- Suporta múltiplas fotos (várias fotos por NC) com índice: `{nc}_{index}.png`
- Detecta e consolida page breaks
- Usa `PROPERTY_TO_HEADING_ONE_COLUMN` para mapear headers
- Retorna lista de imagens por NC (não objeto único)

**Fluxo de extração**:
1. Identifica início de NC pelo header "Código Fiscalização"
2. Extrai campos de dados linha por linha
3. Detecta page breaks e agrupa dados da mesma NC
4. Extrai imagens associadas com nomenclatura indexada (`{nc}_0.png`, `{nc}_1.png`, etc)
5. Retorna dicionário `images_info` com listas de objetos {"url", "uuid"} por NC

**Exemplo de saída** (estrutura `images_info`):
```python
# Formato: {nc_code: [{"url": url, "uuid": uuid}, ...]}
# Cada NC tem uma LISTA de imagens (suporta várias fotos)
{
    "12345": [
        {"url": "s3://bucket/12345_0.png", "uuid": "uuid-1"},
        {"url": "s3://bucket/12345_1.png", "uuid": "uuid-2"},
        {"url": "s3://bucket/12345_2.png", "uuid": "uuid-3"}
    ],
    "12346": [
        {"url": "s3://bucket/12346_0.png", "uuid": "uuid-4"},
        {"url": "s3://bucket/12346_1.png", "uuid": "uuid-5"}
    ]
    # ... mais NCs
}
```

**Formato de arquivo**: `{nc}_{index}.png` (ex: `12345_0.png`, `12345_1.png`)

**Testes**: `tests/import_pdf/extractors/test_one_column_extractor.py`

### DINTwoColumnExtractor

**Responsabilidade**: Extrair dados de PDFs no formato de 2 colunas.

**Localização**: `helpers/import_pdf/extractors/two_column.py`

**Características**:
- Extração baseada em posições Y fixas
- Extrai somente 1 foto por NC com nomenclatura simples: `{nc}.png`
- Sem suporte a page breaks
- Retrocompatível com código legado (migrado de `read_pdf.py:539-589`)
- Retorna objeto único por NC (não lista)

**Posições Y importantes**:
```python
Y_RANGES = {
    "header_top": (176, 200),
    "header_mid": (413, 440),
    "header_bot": (656, 680)
}
```

**Fluxo de extração**:
1. Processa página por página
2. Para cada página, extrai até 3 NCs (layout fixo)
3. Usa posições Y fixas para localizar headers
4. Extrai exatamente 1 imagem por NC com nome `{nc}.png`
5. Retorna dicionário `images_info` com objetos {"url", "uuid"} por NC (não lista)

**Exemplo de saída** (estrutura `images_info`):
```python
# Formato: {nc_code: {"url": url, "uuid": uuid}}
# Cada NC tem um OBJETO com uma única imagem
{
    "12345": {
        "url": "s3://bucket/12345.png",
        "uuid": "uuid-1"
    },
    "12346": {
        "url": "s3://bucket/12346.png",
        "uuid": "uuid-2"
    },
    "12347": {
        "url": "s3://bucket/12347.png",
        "uuid": "uuid-3"
    }
    # ... mais NCs
}
```

**Formato de arquivo**: `{nc}.png` (ex: `12345.png`)

**Testes**: `tests/import_pdf/extractors/test_two_column_extractor.py` (8 testes, 100% pass)

## Integração com ImportPDF

### Fluxo Completo

O sistema de extração é integrado no método `ImportPDF.get_data()` em `helpers/import_pdf/read_pdf.py`.

**Localização**: `helpers/import_pdf/read_pdf.py` (linhas 641-676)

```python
from helpers.import_pdf.extractors.factory import DINExtractorFactory
from helpers.import_pdf.exceptions import (
    UnsupportedPDFFormatException,
    MixedPDFFormatException,
    PageLimitExceededException,
)

class ImportPDF:
    temp_path = "/tmp/pdf_import/"

    def get_data(self):
        pdf_format = None
        images_info = {}
        extractor = None

        # Passo 1: Criar extractor e detectar formato
        try:
            extractor, pdf_format = DINExtractorFactory.create(self.file_name, self.company)
            # pdf_format será "one_column" ou "two_column"
        except (
            UnsupportedPDFFormatException,
            MixedPDFFormatException,
            PageLimitExceededException,
        ) as e:
            logging.error(f"PDF format error: {str(e)}")
            raise
        except Exception as e:
            logging.error(f"Unexpected error creating extractor: {str(e)}")
            sentry_sdk.capture_exception(e)

        # Passo 2: Extrair reportings com base no formato detectado
        reportings = self.extract_reportings(pdf_format)

        # Passo 3: Extrair imagens e fazer upload
        if extractor and reportings:
            try:
                # Extrai imagens e salva em disco
                image_filenames = extractor.extract_images(reportings)
                # Faz upload para S3 e gera estrutura images_info
                images_info = self.upload_images(image_filenames)
            except Exception as e:
                logging.error(f"Unexpected error extracting images: {str(e)}")
                sentry_sdk.capture_exception(e)
                images_info = {}

        # Passo 4: Retornar dados estruturados
        if reportings:
            result = {"reportings": reportings, "images": images_info}
            if pdf_format:
                result["pdf_format"] = pdf_format
            return result
        else:
            return {}
```

### Etapas do Processo

1. **Factory cria extrator e detecta formato**:
   - `DINExtractorFactory.create(pdf_path, company)` retorna `(extractor, pdf_format)`
   - Formato pode ser `"one_column"` ou `"two_column"`
   - Lança exceções se PDF for inválido

2. **Extrai dados dos reportings**:
   - `self.extract_reportings(pdf_format)` extrai dados tabulares do PDF
   - Retorna lista de dicionários com campos dos apontamentos
   - Inclui `supervision_code` usado para nomear imagens

3. **Extrai e salva imagens**:
   - `extractor.extract_images(reportings)` processa todas as páginas
   - Salva imagens em `/tmp/pdf_import/` com nomenclatura adequada
   - Retorna lista de filenames: `["12345_0.png", "12345_1.png", ...]`

4. **Upload para S3**:
   - `self.upload_images(filenames)` faz upload e gera URLs
   - Retorna estrutura `images_info`:
     - **1 coluna**: `{nc: [{"url": "...", "uuid": "..."},...]}`
     - **2 colunas**: `{nc: {"url": "...", "uuid": "..."}}`

### Tratamento de Erros

```python
@task
def parse_pdf_to_json(pdf_import_id, user_id):
    try:
        pdf_import = PDFImport.objects.get(pk=pdf_import_id)
        user = User.objects.get(pk=user_id)
    except PDFImport.DoesNotExist as e:
        sentry_sdk.capture_exception(e)
        logging.error("PDFImport instance doesn't exist for this PK")
    except User.DoesNotExist as e:
        sentry_sdk.capture_exception(e)
        logging.error("User instance doesn't exist for this PK")
    else:
        try:
            parsed_pdf_import = ImportPDF(pdf_import, user).get_pdf_import()
            parsed_pdf_import.save()
            logging.info("PDF parsing done!")
        except (
            UnsupportedPDFFormatException,
            MixedPDFFormatException,
            PageLimitExceededException,
        ) as e:
            # Exceções esperadas de validação de formato
            logging.error(f"PDF format validation failed: {str(e)}")
            pdf_import.error = True
            pdf_import.description = str(e)
            pdf_import.save()
        except Exception as e:
            # Exceções inesperadas
            sentry_sdk.capture_exception(e)
            logging.error(f"Unexpected error parsing PDF: {str(e)}")
            pdf_import.error = True
            pdf_import.save()
```

**Benefícios da Arquitetura**:
- ✅ Suporte a 1 coluna e 2 colunas com detecção automática
- ✅ Separação clara de responsabilidades (Factory, Detector, Extractors)
- ✅ Exceções específicas para diferentes tipos de erro
- ✅ Código mais limpo e testável
- ✅ Fácil adicionar novos formatos no futuro
- ✅ 100% retrocompatível com formato 2 colunas

## Exceções

Todas as exceções estão documentadas na seção **"Detecção de Formato (FormatDetector)"** acima.

**Localização**: `helpers/import_pdf/exceptions.py`

**Resumo**:
- `UnsupportedPDFFormatException` - PDF não é formato DIN ARTESP válido
- `MixedPDFFormatException` - PDF tem formatos mistos (páginas inconsistentes)
- `PageLimitExceededException` - PDF excede 50 páginas


## Bibliotecas Utilizadas

### PyMuPDF (fitz)
**Propósito**: Manipulação de PDF, extração de imagens, análise de layout.

**Instalação**: `poetry add pymupdf`

**Uso principal**:
```python
import fitz

doc = fitz.open(pdf_path)
page = doc[0]
images = page.get_images()
```

**Documentação**: https://pymupdf.readthedocs.io/

### pdfminer
**Propósito**: Extração de texto e análise de estrutura do PDF.

**Instalação**: `poetry add pdfminer.six`

**Uso principal**:
```python
from pdfminer.high_level import extract_text

text = extract_text(pdf_path)
```

**Documentação**: https://pdfminer-docs.readthedocs.io/

## Testes

### Cobertura de Testes

**Total de testes**: 56 testes
- KTD-10767 (base + detector + factory): 42 testes
- KTD-10768 (two_column extractor): 8 testes ✅ PASS
- KTD-10769 (one_column extractor): Planejado
- KTD-10770 (integração ImportPDF): 6 testes

**Localização**: `tests/import_pdf/extractors/`

### Executar Testes

```bash
# Todos os testes de extractors
docker compose exec app poetry run pytest tests/import_pdf/extractors/

# Testes específicos
docker compose exec app poetry run pytest tests/import_pdf/extractors/test_two_column_extractor.py

# Com coverage
docker compose exec app poetry run pytest tests/import_pdf/extractors/ --cov=helpers.import_pdf.extractors
```

### Fixtures Importantes

```python
# conftest.py
@pytest.fixture
def sample_one_column_pdf():
    """PDF de teste com formato 1 coluna"""
    return fitz.open("fixtures/din_one_column.pdf")

@pytest.fixture
def sample_two_column_pdf():
    """PDF de teste com formato 2 colunas"""
    return fitz.open("fixtures/din_two_column.pdf")

@pytest.fixture
def mixed_format_pdf():
    """PDF com formatos mistos (para teste de exceção)"""
    return fitz.open("fixtures/din_mixed.pdf")
```

## Validações e Regras de Negócio

### 1. Formato Consistente
**Regra**: PDF não pode ter formatos mistos (1-col e 2-col no mesmo arquivo).

**Validação**: `FormatDetector.detect_format()` valida todas as páginas.

**Exceção**: `MixedPDFFormatException`

### 2. Ordem de Headers
**Regra**: Headers têm ordem DIFERENTE entre 1-col e 2-col.

**Implementação**: `PROPERTY_TO_HEADING_ONE_COLUMN` mapeia corretamente.

**Impacto**: Crítico para extração correta de dados.

### 3. Quantidade de Fotos
**Regra**:
- 1 coluna: várias fotos por NC (variável) - formato `{nc}_{index}.png`
- 2 colunas: **1 foto por NC** - formato `{nc}.png`

**Validação**: Extractors validam quantidade de imagens extraídas.

**Estrutura de dados**:
- 1 coluna: `{nc_code: [{"url": "...", "uuid": "..."}, ...]}` (lista)
- 2 colunas: `{nc_code: {"url": "...", "uuid": "..."}}` (objeto único)

### 4. Tamanho de Arquivo
**Regra**: Mesmo limite que outros arquivos (100MB por upload).

**Validação**: Django/DRF FileField validation.

### 5. Tipo de Arquivo
**Regra**: Somente arquivos PDF são aceitos.

**Validação**: MIME type check no upload.

## Lições Aprendidas (KTD-10265)

### ❌ Erro Crítico: Assumir Headers Idênticos

**O que aconteceu**:
- Documentação inicial do épico dizia que headers eram "✅ Idêntico"
- Assumimos isso sem validação empírica
- Usuário enviou vários exemplos de PDFs reais
- Não comparamos os PDFs para validar a documentação
- Durante implementação, descobrimos que **headers têm ordem diferente**
- Precisamos criar `PROPERTY_TO_HEADING_ONE_COLUMN` (rework)
- Epic transbordou do tempo planejado

**Lição Aprendida**:
> **Documentação descreve o DESIGN, mas DADOS REAIS descrevem a REALIDADE.**

**Princípio**:
1. Sempre validar documentação contra exemplos reais
2. Quando usuário envia exemplos, sempre confirmar se os dados enviados são válidos comparado com o planejado, para evitar divergências Silenciosas.
3. Criar tabelas comparativas de dados ANTES de implementar
4. Questionar suposições com dados empíricos

### ✅ Acertos

1. **Padrões de Design**: Factory + Strategy + Template Method funcionaram perfeitamente
2. **Testes**: 100% retrocompatibilidade validada
3. **Exceções**: Tratamento específico facilitou debugging
4. **Separação de responsabilidades**: Código mais limpo e manutenível

## Próximos Passos (Roadmap)

### Planejado
- [ ] Implementação completa de `DINOneColumnExtractor` (KTD-10769)
- [ ] Testes de integração end-to-end
- [ ] Suporte a mais variações de layout DIN
- [ ] Cache de formato detectado para melhor performance

### Futuro
- [ ] Suporte a outros padrões além de DIN ARTESP
- [ ] OCR para PDFs escaneados
- [ ] Validação de dados extraídos contra schemas
- [ ] Dashboard de monitoramento de importações

## Referências

### Código
- `helpers/import_pdf/extractors/` - Implementação principal
- `helpers/import_pdf/read_pdf.py` - Classe ImportPDF
- `tests/import_pdf/extractors/` - Testes

### Documentação
- `.claude/sessions/KTD-10265/` - Épico completo
- `.claude/sessions/KTD-10265/KTDS/` - Cards individuais (10767-10770)
- `.claude/sessions/KTD-10265/KTD-10265-arquitetura.md` - Arquitetura inicial

### Padrões de Design
- Factory Pattern: https://refactoring.guru/design-patterns/factory-method
- Strategy Pattern: https://refactoring.guru/design-patterns/strategy
- Template Method: https://refactoring.guru/design-patterns/template-method

### Bibliotecas
- PyMuPDF: https://pymupdf.readthedocs.io/
- pdfminer.six: https://pdfminer-docs.readthedocs.io/
