# Funcionalidades

## Funcionalidades Principais e Críticas

### 1. Processamento de Apontamentos (/Reporting/)
**Descrição**: Módulo central de Apontamentos (anteriormente "Reporting"). Gerencia o ciclo de vida dos apontamentos rodoviários, desde a criação (entrada de dados por formulários dinâmicos) até aprovação, anexos e integração com painéis e GIS.

Principais características:
- Registro e edição de Apontamentos com dados geoespaciais (ponto, geometry e propriedades)
- Formulários dinâmicos por Classe (occurrence_type) com campos que alimentam `form_data` e `form_metadata`
- Fluxo de aprovação configurável por Unidade via `ApprovalFlow` / `ApprovalStep` / `ApprovalTransition`
- Anexos e imagens gerenciados (limite de 100MB por arquivo) com processamento automático em AWS Lambda (resizes 400px/1000px)
- APIs para exportação e painéis (endpoints tipo `/Reporting/Spreadsheet/` para uso em PowerBI)
- Mensagens e notificações vinculadas ao Apontamento (ReportingMessage)

Modelo de dados e nomenclaturas (termos usados na documentação):
- Apontamento (Reporting): registro principal com UUID e Serial (campo `number`)
- Unidade (Company): unidade/cliente à qual o apontamento pertence
- Equipe (Firm): equipe/responsável técnico associada ao apontamento
- Classe (OccurrenceType): definição do conjunto de campos do formulário e regras
- Arquivos de Apontamento (ReportingFile): imagens/arquivos anexos

Detalhes funcionais

- Formulários dinâmicos
	- `form_data`: JSON chave/valor onde cada chave é o apiName do campo definido na Classe e o valor é o preenchido pelo usuário.
	- `form_metadata`: metadados por campo que descrevem comportamento/validações e campos com lógica/auto-preenchimento (ex.: cálculo de área a partir de comprimento e largura).
	- Tipos de campo suportados: texto, numérico (int/float), seleção/seleção múltipla, data/hora e campos com lógica (json-logic).

- Fluxo de aprovação
	- Fluxos são definidos por `ApprovalFlow` e vinculados à Unidade/Modelo.
	- Cada passo do fluxo é um `ApprovalStep` ("passo de aprovação").
	- As transições entre passos usam `ApprovalTransition` e compõem a máquina de estados do processo de aprovação.
	- Diferentes modelos podem ter fluxos distintos; o apontamento armazena o passo atual em `approval_step`.

- Geoespacial e cálculos auxiliares
	- O campo `end_km` pode ser definido manualmente ou calculado pela função `calculate_end_km` (ver `helpers/km_converter.py`).
	- O campo `geometry` aceita `GeometryCollection` ao persistir no banco; a API normalmente expõe os dados geográficos via a classe `FeatureCollectionField` (`helpers/fields.py`) em vez do raw `geometry`.

- Arquivos e imagens
	- Limite de upload por arquivo: 100MB.
	- Controle de acesso aos arquivos baseado em permissões por usuário/Unidade.
	- Imagens processadas por Lambdas que geram versões otimizadas (400px e 1000px) e armazenam em buckets S3 dedicados.

- Endpoints e integrações
	- Endpoints principais: `/api/Reporting/` (CRUD), `/api/Reporting/CopyReportings/`, `/api/Reporting/BulkApproval/`, `/api/Reporting/ZipPicture/` e endpoints GIS (`ReportingGeo`, `ReportingGisIntegration`).
	- Export/Spreadsheet endpoints usados para integração com PowerBI/painéis.
	- Integração via API padrão para criação/consulta; notificações internas enviadas quando uma `ReportingMessage` é criada.

- Performance e cache
	- Cache aplicado a recursos estáticos como `OccurrenceType`.
	- Índices de banco configurados para campos de acesso frequente (ex.: Serial/`number`, timestamps).

Observações e limites
- O esquema MVT (Django) e a arquitetura multi-tenant (Unidades com bases isoladas) continuam válidos e impactam o desenho das APIs e permissões.
- A seção acima substitui e centraliza as informações relacionadas ao módulo de Apontamentos; quaisquer referências antigas a "Reporting" devem ser entendidas como "Apontamento" neste contexto.

### Programações (Job)
**Descrição**: Módulo de Programações (modelo `Job`) que agrupa e organiza Apontamentos em unidades de trabalho — por exemplo, ordens de inspeção, laudos ou coleções de apontamentos a serem executados por uma Equipe.

Principais características:
- Agrupamento de Apontamentos por `Job` (Programação) com campos de controle (datas, responsável, progresso e contagens de apontamentos executados).
- Suporte a criação de Apontamentos de várias origens: adição direta, a partir de Inventories (inventários), via inspeção (`inspection`), ou por operações de "recuperation" (recuperação/recuperação em massa).
- Processamento síncrono para pequenas cargas e processamento assíncrono em batches para volumes elevados (via `JobAsyncBatch`).
- Regras de sincronização móvel que limitam quando uma Programação pode ser baixada para um app mobile (`can_be_synced`, `processing_async_creation`).

Mapeamento de campos (terminologia usada na documentação):
- Programação (`Job`): representa a unidade de trabalho.
- Unidade (`company` / `Company`): Unidade/cliente à qual a Programação pertence.
- Equipe (`firm` / `Firm`): Equipe responsável ou executora.
- Serial (`number`): campo `number` do modelo, exposto como "Serial".
- Classe (`occurrence_type`): tipo de ocorrência usado quando a Programação cria Apontamentos por inventário/recuperação.

Campos e relacionamentos importantes (resumo):
- `uuid`, `number` (Serial), `title`, `description`
- `company` (Unidade), `firm` (Equipe), `worker` (usuário executor)
- `start_date`, `end_date`, `progress`, `executed_reportings`, `reporting_count`
- Relacionamentos com Apontamentos: `reportings` M2M; referência a `inspection`/`parent_inventory` quando aplicável
- Flags/batch: `creating_batches`, `pending_inventory_to_reporting_id`, `job_async_batches` (JobAsyncBatch)

Fluxos de criação e atualização
- Adição direta de Apontamentos: é possível criar/associar Apontamentos diretamente a um Job (lista explícita de `reportings`).
- A partir de Inventory (inventário): o sistema pode transformar itens de Inventory em Apontamentos e adicioná-los ao Job. Para grandes volumes, a criação é feita em batches assíncronos (`JobAsyncBatch`) e processada por `process_job_async_batch` em `apps/work_plans/asynchronous.py`.
	- Existem dois tipos de batch: `FILTERED` (mapeamentos origin→target por `sheet_inventory_occurrence_type_mapper_for_inspection`) e `MANUAL` (combina inventários com uma lista manual de `occurrence_types`).
	- O campo `menu` (ForeignKey para `RecordMenu`) é obrigatório — regra de negócio que vincula os Apontamentos gerados a um menu específico. A validação é feita no serializer (`apps/work_plans/serializers.py`).
- A partir de `inspection`: criar Reportings baseados em inspeções anteriores (funções helper específicas).
- Recuperation (recuperação): criação de Programações/Apontamentos a partir de processos de recuperação/Retrieval; existem helpers específicos para criar itens de "recuperation".

Regras Programação ↔ Apontamento
- Ao adicionar Apontamentos a uma Programação:
	- Se o Apontamento tem um status (ServiceOrderActionStatus) de ordem menor que 2, é automaticamente atualizado para o status de ordem 2. Esta é uma regra fixa, aplicada globalmente para todas as Unidades.
	- O helper `update_reportings_fields` associa os Apontamentos ao Job e atualiza campos calculados (`progress`, `executed_reportings`, `reporting_count`).
- Ao remover Apontamentos do Job:
	- O status anterior do Apontamento só é restaurado se não houve alteração de status enquanto ele estava vinculado à Programação.
	- Se o status foi alterado durante o vínculo com a Programação, o novo status é mantido.
- Regras de execução: A definição de "executado" é controlada por `company.metadata['executed_status_order']`, que é um valor numérico obrigatório e único para cada Unidade — não é permitido ter ordens repetidas.

Sincronização móvel (mobile sync) e limites
- A propriedade `can_be_synced` (exposta por `JobSerializer`/`JobWithReportingLimitSerializer`) é calculada com base em dois fatores principais:
	1. A flag `processing_async_creation` (quando True indica que a criação de Apontamentos está sendo processada em background e, portanto, não é seguro sincronizar ainda).
	2. O total de Apontamentos da Programação comparado com `company.metadata['max_reportings_by_job']` — se o `reporting_count` exceder esse limite, a Programação não é permitida para sincronização mobile por padrão.
- Observação: exceções podem existir via permissões; o comportamento atual está implementado no serializer e nas views (`apps/work_plans/views.py`). Deve-se documentar se roles/flags específicas devem forçar a sincronização mesmo quando o limite for excedido.

Processamento assíncrono (JobAsyncBatch)
- Quando um Job recebe muitos inventários para conversão em Apontamentos, o sistema cria instâncias `JobAsyncBatch` e processa em lotes (`process_job_async_batch`).
- O processamento:
	- Desconecta sinais calculados temporariamente para otimizar criação em massa.
	- Cria Reportings em memória e persiste via `bulk_create_with_history` antes de associar ao Job.
	- Ao final de todos os batches do Job, o campo `pending_inventory_to_reporting_id` é limpo e o Job é salvo para recalcular totais.

Endpoints e ações relevantes
- `CheckAsyncCreation`: ação para checar se há criação assíncrona em andamento para a Programação.
- `SyncInfo`: endpoint que retorna informações úteis para a sincronização mobile (contagens, arquivos, limites).
- `BulkArchive`: arquivar/desarquivar lotes de Programações. Quando usado com `removeUnexecutedReportings=True`, desassocia (mas não deleta) Apontamentos não-executados. Ao desarquivar uma Programação, os Apontamentos previamente removidos não são re-associados.

Watchers e notificações
- Todos os visualizadores da Programação (watchers) recebem notificações quando eventos relevantes ocorrem, como criação de uma nova Programação.
- Os watchers incluem todos os usuários/equipes/sub-unidades configurados via `watcher_firms`, `watcher_users`, `watcher_subcompanies`.
- Templates de email para criação/atualização de Job existem em `apps/work_plans/templates/email/` e são disparadas automaticamente via serializers/views.

Auto-Scheduling (Programações Automáticas)

O sistema suporta alocação automática de Apontamentos em Programações com base em regras configuradas por Unidade. A funcionalidade é ativada via `company.metadata["auto_scheduling_jobs"]` e executada automaticamente quando um novo Apontamento é criado (via signal `post_save` do Reporting) ou importado via Excel.

Campos do modelo Job relacionados ao auto-scheduling:
- `is_automatic` (BooleanField, default=False): indica que a Programação foi criada automaticamente pelo sistema de auto-scheduling.
- `has_auto_allocated_reportings` (BooleanField, default=False): indica que a Programação possui Apontamentos alocados automaticamente, mesmo que a Programação em si tenha sido criada manualmente.

Fluxo do auto-scheduling:
1. **Verificação de habilitação**: O sistema verifica se `auto_scheduling_jobs.enabled` está True no metadata da Unidade.
2. **Verificação de elegibilidade**: O Apontamento deve atender a todas as condições: não estar vinculado a nenhuma Programação, ter sido criado após a `activation_date` configurada e possuir uma Equipe (`firm`) associada.
3. **Match de regras**: O sistema percorre as regras configuradas em `auto_scheduling_jobs.rules` e tenta encontrar uma regra que corresponda ao Apontamento. Tipos de match suportados:
   - `occurrence_type`: compara o UUID do tipo de ocorrência do Apontamento com `match_value`.
   - `occurrence_kind`: compara o `occurrence_kind` do tipo de ocorrência com `match_value`.
   - `form_field`: compara um campo específico de `form_data` (via `field_api_name`) com `field_value`. Suporta valores string (comparação direta) e array (verifica se o valor está contido na lista).
4. **Busca de Programação existente**: O sistema busca uma Programação válida para alocar o Apontamento, priorizando Programações com menor `reporting_count` e, em caso de empate, a mais recente (`start_date` DESC). Programações arquivadas, expiradas ou no limite de `max_reportings_per_job` são excluídas.
5. **Criação de nova Programação**: Se nenhuma Programação válida for encontrada, o sistema cria uma nova com: `is_automatic=True`, `has_auto_allocated_reportings=True`, `start_date` = hoje, `end_date` = hoje + `deadline_days` (23:59:59), e descrição no formato `[DD/MM] - {nome_equipe} - Automática`.
6. **Vinculação e atualização de status**: O Apontamento é vinculado à Programação e, se seu status tiver ordem menor que 2, é atualizado para o status de ordem 2 (mesma regra de vinculação manual).
7. **Watchers**: O criador do Apontamento é adicionado como watcher do Job, e a Equipe é adicionada como watcher firm.

Configuração no metadata da Unidade (`company.metadata["auto_scheduling_jobs"]`):
```json
{
  "enabled": true,
  "activation_date": "2026-02-01T00:00:00Z",
  "search_window_days": 7,
  "max_reportings_per_job": 100,
  "rules": [
    {
      "match_type": "occurrence_type",
      "match_value": "<uuid-da-classe>",
      "deadline_days": 7
    },
    {
      "match_type": "occurrence_kind",
      "match_value": "conservação",
      "deadline_days": 5
    },
    {
      "match_type": "form_field",
      "field_api_name": "priority",
      "field_value": "high",
      "deadline_days": 3
    }
  ]
}
```

Parâmetros de configuração:
- `enabled` (bool): ativa/desativa o auto-scheduling para a Unidade.
- `activation_date` (string ISO 8601): data a partir da qual Apontamentos são elegíveis. Apontamentos criados antes desta data são ignorados.
- `search_window_days` (int, default=7): janela de busca em dias para encontrar Programações existentes.
- `max_reportings_per_job` (int, default=100): limite máximo de Apontamentos por Programação.
- `rules` (array): lista de regras de match, processadas na ordem. A primeira regra que corresponder é usada.
  - `match_type` (string): tipo de match (`occurrence_type`, `occurrence_kind`, `form_field`).
  - `match_value` (string): valor para comparação (UUID para `occurrence_type`, texto para `occurrence_kind`).
  - `field_api_name` (string, apenas para `form_field`): nome da API do campo em `form_data`.
  - `field_value` (string, apenas para `form_field`): valor esperado do campo.
  - `deadline_days` (int, default=7): prazo em dias para a Programação criada automaticamente.

Pontos de disparo:
- Signal `post_save` de Reporting (`apps/reportings/signals.py`): disparado quando `created=True`.
- Importação via Excel (`helpers/import_excel/read_excel.py`): disparado após salvar um novo Reporting importado (quando `is_edit=False`).

Filtro de API:
- O endpoint `/api/Job/` aceita o parâmetro `auto_scheduling` (boolean) para filtrar Programações:
  - `auto_scheduling=True`: retorna Programações com `is_automatic=True` OU `has_auto_allocated_reportings=True`.
  - `auto_scheduling=False`: retorna apenas Programações com ambos campos False (100% manuais).

Referências de implementação (arquivos chave)
- Model e campos: `apps/work_plans/models.py` (modelo `Job`, `JobAsyncBatch`)
- Serializers/validações e lógica de criação/atualização: `apps/work_plans/serializers.py`
- Endpoints e actions: `apps/work_plans/views.py`
- Processamento assíncrono: `apps/work_plans/asynchronous.py` (função `process_job_async_batch`)
- Helpers de negócio e atualizações de Apontamento: `helpers/apps/job.py` (funções `update_reportings_fields`, `calculate_fields`, `get_sync_jobs_info_from_uuids`)
- Auto-scheduling: `helpers/apps/auto_scheduling.py` (função `process_auto_scheduling`)
- Signal de auto-scheduling: `apps/reportings/signals.py` (função `auto_schedule_reporting`)
- Testes de auto-scheduling: `helpers/tests/test_auto_scheduling.py`

Notas e recomendações
- Documentar explicitamente a necessidade do campo `menu` nos fluxos inventário/recuperação quando aplicável.
- Validar se `company.metadata['max_reportings_by_job']` e `executed_status_order` estão configurados para todas as Unidades; incluir isso nas checklists de onboarding de Unidade.
- Considerar exibir no app mobile um estado claro quando `processing_async_creation` estiver True (por exemplo: "Programação sendo processada — tente novamente mais tarde").

### 2. Gestão de Unidades e Usuários (/Company/)
**Descrição**: Sistema de gerenciamento de Unidades (Company), subempresas e usuários com diferentes níveis de acesso.
**Componentes**:
- Unidades (Company)
- Subempresas (SubCompany)
- Grupos de Unidades (CompanyGroup)
- Usuários em Unidades (UserInCompany)
- Solicitações de Acesso (AccessRequest)

### 2. Controle de Recursos e Contratos
**Descrição**: Gerenciamento de recursos, contratos e medições.
**Componentes**:
- Recursos (Resource)
- Contratos (Contract)
- Recursos Humanos (HumanResource)
- Itens de Contrato (ContractItem)
- Boletins de Medição (MeasurementBulletin)

### 3. Relatórios e Monitoramento
**Descrição**: Sistema de relatórios e monitoramento diário.
**Componentes**:
- Ocorrências (OccurrenceRecord)
- Exportação de Relatórios (ReportingExport)

### 4. Gestão de Mapas e Arquivos Espaciais
**Descrição**: Gerenciamento de camadas de mapa e arquivos shape.
**Componentes**:
- Camadas de Mapa (TileLayer)
- Arquivos Shape (ShapeFile)
- Propriedades de Shape (ShapeFileProperty)
- Busca ECM/Engie

### 5. Dashboard e Análises
**Descrição**: Dashboard com métricas e análises.
**Endpoints**:
- História de Recursos (ResourceHistory)
- Status de Registros (RecordStatus)
- Custos de Ordens de Serviço (ServiceOrderCost)
- Performance de Unidades (FirmPerformance)
- Contagem de Ações (ActionCount)
- SLA de Relatórios (ReportingSLA)

### 6. Controle de Qualidade
**Descrição**: Sistema de controle de qualidade para construções.
**Componentes**:
- Projetos de Qualidade (QualityProject)
- Amostras (QualitySample)
- Ensaios (QualityAssay)
- Plantas de Construção (ConstructionPlant)

### 7. Sistema de Templates e Exportações
**Descrição**: Gerenciamento de templates e exportações.
**Componentes**:
- Templates
- Canvas Lists/Cards
- Importação Excel/CSV
- **Importação de PDF DIN ARTESP** - Sistema multi-formato com detecção automática ([ver documentação completa](pdf-import.md))
  - Suporte a formato 1 coluna e 2 colunas
  - Detecção automática de formato via FormatDetector
  - Extractors especializados (Factory + Strategy patterns)
  - Exceções customizadas para formatos não suportados ou mistos
- Exportação de Relatórios
- Sincronização Mobile

### 8. Gestão de Ocorrências
**Descrição**: Sistema de registro e acompanhamento de ocorrências.
**Características**:
- Registro de Ocorrências
- Tipos de Ocorrência
- Geração de PDF
- Histórico
- Georreferenciamento

## Funcionalidades Secundárias

### 1. Autenticação e Autorização
- Autenticação via Token
- Suporte a SAML2
- Reset de senha
- Verificação de GID
- Restrição de naturezas por perfil de permissão (`PermissionOccurrenceKindRestriction`)
  - Whitelist configurável via Django Admin
  - Filtragem aplicada em `OccurrenceTypeView`
  - Retrocompatível (sem configuração = acesso total)

### 2. Gerenciamento de Arquivos
- Upload para S3
- Controle de acesso público/privado
- Processamento de arquivos

### 3. Email e Notificações
- Sistema de fila de emails
- Blacklist de emails
- Tracking de eventos
- Notificações de usuário

### 4. Monitoramento e Logs
- Integração com Sentry
- AWS X-Ray tracing
- Action logs
- Performance tracking

## Funcionalidades em Desenvolvimento
- Consultar roadmap do projeto para funcionalidades planejadas

## Funcionalidades Deprecated
- Integração ARTESP
- Importação de arquivos Excel via frontend
- Módulos "Equipamento" e "WorkPlan"