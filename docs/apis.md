# Especificação de APIs

## Visão Geral da API
A API do Kartado segue o padrão REST com formatação JSON:API. Oferece endpoints para todas as funcionalidades do sistema, com autenticação via token e SAML2. O sistema possui endpoints específicos para cada ambiente de cliente (CCR, Engie) com URLs dedicadas e segregação completa de dados.

### Endpoints Mais Utilizados

1. **/api/Reporting/** (Apontamento)
  - Geração e download de relatórios relacionados a Apontamentos
  - Manipulação complexa de dados de Apontamento
  - Exportação para Excel

2. **/api/MultipleDailyReport/**
  - RDOs (Relatório Diário de Obra)
  - Alta frequência de uso
  - Processamento crítico

3. **/api/Company/** (Unidade)
  - Gestão de Unidades (Company)
  - Controle de unidades/segmentos
  - Base para segmentação de dados

### Endpoints Especiais de Apontamento

Alguns endpoints do módulo de Apontamentos merecem menção separada por fornecerem operações específicas além do CRUD básico:

- **/api/Reporting/CopyReportings/** — Cria cópias de apontamentos existentes mantendo (ou limpando) relacionamentos e anexos conforme parâmetros. Usado para duplicar apontamentos para reutilização.
- **/api/Reporting/BulkApproval/** — Endpoint para aprovações em lote, utilizado por operadores que precisam alterar o estado de múltiplos apontamentos seguindo regras de fluxo de aprovação.
- **/api/Reporting/ZipPicture/** — Gera e disponibiliza um ZIP com imagens/arquivos relacionados a um ou mais apontamentos (útil para download em massa).
- **/api/Reporting/Spreadsheet/** — Endpoints voltados à exportação/integração com painéis e ferramentas de BI (PowerBI), fornecendo formatos tabulares/planilhas.
- **/api/ReportingGeo/** e **/api/ReportingGisIntegration/** — Endpoints que expõem dados geoespaciais (GeoJSON/GeoFeature) para consumo por soluções GIS.

Observação: os caminhos e nomes de parâmetros usados pela API permanecem os mesmos; aqui apenas descrevemos o propósito de cada endpoint especial.

## Autenticação e Autorização

### Obtenção de Token
**POST** `/token/login/`
```json
{
  "data": {
    "type": "ObtainJSONWebToken",
    "attributes": {
      "username": "usuario",
      "password": "senha"
    }
  }
}
```

**Resposta**:
```json
{
  "data": {
    "type": "AuthToken",
    "attributes": {
      "token": "eyJ0eXA...",
      "user": {
        "uuid": "123e4567-e89b...",
        "username": "usuario",
        "email": "user@example.com"
      }
    }
  }
}
```

### Autenticação
- **Token**: `Authorization: Bearer <token>` (válido por 7 dias)
- **SAML2**: Para SSO corporativo
- **Basic Auth**: Em desenvolvimento
- **Session Auth**: Interface admin

## Endpoints

### Unidades e Usuários

#### GET /api/Company/ (Unidade)
**Descrição**: Lista Unidades acessíveis ao usuário
**Autenticação**: Requerida
**Parâmetros**:
- Query: search, ordering
- Filtros: active, parent

**Resposta de Sucesso**:
```json
{
  "data": [{
  "type": "Company",
    "id": "uuid",
    "attributes": {
      "name": "string",
      "active": true
    }
  }]
}
```

### Recursos e Contratos

#### GET /api/Resource/
**Descrição**: Lista recursos disponíveis
**Autenticação**: Requerida
**Parâmetros**:
- Query: search, type, company  # `company` refere-se à Unidade (Company)
- Filtros: active, contract

### Mapas e GIS

#### GET /api/ShapeFile/
**Descrição**: Lista arquivos shape
**Autenticação**: Requerida
**Parâmetros**:
- Query: type, company  # `company` refere-se à Unidade (Company)
- Filtros: format, status

#### GET /api/ShapeFile/{id}/GZIP/
**Descrição**: Download de arquivo shape comprimido
**Autenticação**: Requerida
**Formato**: application/gzip

### Dashboard

#### GET /api/dashboard/ResourceHistory/
**Descrição**: Histórico de recursos
**Autenticação**: Requerida
**Parâmetros**:
- Query: date_range, type

### Email e Notificações

#### POST /api/email_handler/QueuedEmail/
**Descrição**: Envia email para fila
**Autenticação**: Requerida
**Body**:
```json
{
  "to": "string",
  "subject": "string",
  "template": "string",
  "context": {}
}
```

### Programações (Job)

#### GET /api/Job/
**Descrição**: Lista Programações acessíveis ao usuário
**Autenticação**: Requerida
**Parâmetros**:
- Query: `company` (obrigatório), `search`, `ordering`
- Filtros: `archived`, `processing_async_creation`, `lot`, `progress__gte`, `progress__lte`, `auto_scheduling`

**Filtro `auto_scheduling`** (BooleanFilter):
- `auto_scheduling=True`: retorna Programações com `is_automatic=True` OU `has_auto_allocated_reportings=True` (Programações criadas automaticamente ou que receberam Apontamentos por auto-scheduling).
- `auto_scheduling=False`: retorna Programações com `is_automatic=False` E `has_auto_allocated_reportings=False` (apenas Programações 100% manuais).

**Campos retornados relacionados a auto-scheduling**:
- `is_automatic` (boolean): indica se a Programação foi criada automaticamente pelo sistema.
- `has_auto_allocated_reportings` (boolean): indica se a Programação possui Apontamentos alocados automaticamente.

**Exemplo de requisição**:
```
GET /api/Job/?company=<uuid>&auto_scheduling=True
Authorization: JWT <token>
Content-Type: application/vnd.api+json
```

## Rate Limiting
- 500 requisições/minuto por usuário
- Limites específicos por endpoint
- Headers: X-RateLimit-*

## Versionamento
- Versão atual: v1
- Path: /api/v1/
- Versionamento via Accept header

## Webhooks
Disponíveis para:
- Atualizações de status
- Novos registros
- Mudanças de estado
- Eventos de email

## OpenAPI/Swagger
Documentação interativa disponível em:
- Desenvolvimento: /api/docs/
- Staging: https://staging.api.hidros.roadlabs.com.br/api/docs/
- Produção: https://api.hidros.roadlabs.com.br/api/docs/