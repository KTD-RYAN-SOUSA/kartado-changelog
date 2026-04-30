# Regras de Negócio

## Regras Críticas

### 1. Separação Multi-tenant
**Descrição**: Sistema suporta múltiplos clientes (CCR, Engie, etc) com isolamento total de dados
**Implementação**: Bancos de dados separados por cliente
**Validações**: 
- Conexão dinâmica ao banco correto baseado no cliente
- Backend URLs específicas por cliente
**Exceções**: Nenhuma - isolamento total obrigatório

### 2. Controle de Acesso e Segmentação de Dados
**Descrição**: Sistema crítico de segmentação de dados baseado em permissões de usuário e unidade (Company)
**Implementação**:
- Sistema de permissões granular por Unidade
- Segmentação de dados por unidade (Company)
- Verificação em tempo real de permissões
- Whitelist de naturezas por perfil de permissão (`PermissionOccurrenceKindRestriction`)
**Validações**:
- Verificação de pertencimento à Unidade
- Checagem de permissões específicas por funcionalidade
- Validação de escopo de acesso por Unidade
- Filtros automáticos de dados baseados em permissão
- Filtragem de `OccurrenceType` por naturezas permitidas (quando configurado)
**Exceções**: Usuários admin podem ter acesso mais amplo, mas sempre limitado à sua unidade

### 2.1 Restrição de Naturezas por Permissão
**Descrição**: Whitelist de naturezas (`occurrence_kind`) configurável por perfil de permissão (`UserPermission`) e empresa (`Company`).
**Modelo**: `PermissionOccurrenceKindRestriction`
**Implementação**:
- Cada perfil pode ter uma lista de naturezas permitidas por empresa
- A restrição é aplicada na consulta de `OccurrenceType` via `PermissionManager.get_allowed_occurrence_kinds()`
- Usuários com múltiplos perfis recebem a união das naturezas permitidas
**Retrocompatibilidade**:
- Lista vazia ou sem registro = acesso total (comportamento padrão)
- Não impacta usuários/perfis existentes sem configuração
**Configuração**: Via Django Admin (inline em UserPermission)

### 3. Gestão de Arquivos
**Descrição**: Arquivos são armazenados com controle de acesso público/privado
**Implementação**: AWS S3 com buckets separados
**Validações**:
- Verificação de permissões de acesso
- Controle de tipos de arquivo permitidos
- Validação de tamanho máximo
**Exceções**: Arquivos estáticos são sempre públicos

### 4. Processamento de Emails
**Descrição**: Sistema de email com rastreamento e blacklist
**Implementação**: Fila de emails com SQS
**Validações**:
- Verificação de blacklist
- Validação de templates
- Tracking de status de envio
**Exceções**: Emails críticos do sistema sempre são enviados

### 5. Auto-Scheduling de Programações
**Descrição**: Alocação automática de Apontamentos em Programações baseada em regras configuradas por Unidade
**Implementação**: Signal `post_save` de Reporting + helper `process_auto_scheduling` em `helpers/apps/auto_scheduling.py`
**Validações**:
- Auto-scheduling deve estar habilitado no metadata da Unidade (`auto_scheduling_jobs.enabled = true`)
- O Apontamento não pode estar já vinculado a uma Programação (`job_id` deve ser `None`)
- O Apontamento deve ter sido criado após a `activation_date` configurada
- O Apontamento deve ter uma Equipe (`firm`) associada
- Pelo menos uma regra de match deve corresponder ao Apontamento
- Programações candidatas devem estar: não arquivadas, com `end_date` no futuro, dentro da janela de busca (`search_window_days`) e abaixo do limite de Apontamentos (`max_reportings_per_job`)
**Exceções**:
- Apontamentos importados via Excel também são processados pelo auto-scheduling (exceto edições)
- A função é idempotente: Apontamentos já vinculados a Programações são ignorados
- Se nenhuma Programação válida for encontrada, uma nova é criada automaticamente com `is_automatic=True`
- Toda a operação de vinculação ocorre dentro de `transaction.atomic()` com `select_for_update()` para garantir consistência em acessos concorrentes
### 6. Importação de PDF DIN ARTESP
**Descrição**: Sistema de importação multi-formato para PDFs de Não Conformidades
**Implementação**: Factory + Strategy patterns com detecção automática de formato
**Validações**:
- Formato deve ser DIN ARTESP (1 coluna ou 2 colunas)
- PDF não pode ter formatos mistos (1-col e 2-col no mesmo arquivo)
- Quantidade de fotos por NC: 2-4 para 1 coluna, **1 para 2 colunas** (nome sobrescreve)
- Headers têm ordem DIFERENTE entre formatos (mapeamento via PROPERTY_TO_HEADING_ONE_COLUMN)
**Exceções**:
- `UnsupportedPDFFormatException` - PDF não é formato DIN ARTESP
- `MixedPDFFormatException` - PDF contém formatos mistos
- `PageLimitExceededException` - PDF excedeu o limite de páginas definidos

**Observação**: No formato 2 colunas, o nome da imagem é sempre "{nc}.png", resultando em apenas 1 foto salva.

**Documentação completa**: [pdf-import.md](pdf-import.md)

## Validações e Restrições

### Unidades e Usuários
- Uma Unidade pode ter múltiplas subempresas
- Um usuário pode pertencer a múltiplas Unidades
- Unidades precisam ter pelo menos um admin
- Nomes de Unidade devem ser únicos
- Emails de usuário devem ser únicos

### Contratos e Recursos
- Contratos precisam ter Unidade associada
- Recursos devem ter tipo definido
- Valores de contrato não podem ser negativos
- Datas de início devem ser anteriores a datas de fim

### Relatórios e Medições
- Relatórios diários precisam ter data válida
- Medições precisam ter itens de contrato associados
- Valores devem respeitar limites contratuais
- Documentos obrigatórios por tipo de relatório

## Políticas e Workflows

### Aprovação de Acessos
1. Usuário solicita acesso
2. Admin da Unidade aprova/rejeita
3. Sistema cria/atualiza permissões
4. Notificação é enviada ao usuário

### Processamento de Relatórios
1. Usuário submete relatório
2. Sistema valida dados
3. Arquivos são processados e armazenados
4. Notificações são enviadas
5. Relatório fica disponível para consulta

### Gestão de Contratos
1. Contrato é criado com itens
2. Medições são registradas
3. Sistema valida valores e limites
4. Relatórios são gerados

## Cálculos e Algoritmos

### Exportação de Apontamentos
- **Processo**: Geração assíncrona via task
- **Colunas Básicas**:
  ```python
  basic_columns = {
      "number": "Serial",
      "parent_number": "Serial Inventário Vinculado",
      "road": "Rodovia",
      "km": "km inicial",
      "end_km": "km final",
      "lot": "Lote",
      "latitude": "Latitude",
      "longitude": "Longitude",
      "occurrence_kind": "Natureza",
      "occurrence_type": "Classe",
      ...
  }
  ```
- **Formatação**:
  - Estilos personalizados (borders, alignment)
  - Formatação de números e datas
  - Tratamento de imagens
- **Limites**:
  - MAX_REPORTING_FILES = 100000
  - THREADING_LIMIT = 30
- **Tratamento de Erros**:
  - ReportingFileCountExceededException
  - Capture de exceções no Sentry
  - Notificação de erros

### Cálculos Financeiros
- Valores de medição por item
- Totais de contrato
- Descontos e ajustes
- Performance de Unidades

### Cálculos Geográficos
- Processamento de arquivos shape
- Conversão de coordenadas
- Cálculos de área/distância
- Geração de mapas

## Compliance e Regulamentações

### LGPD/GDPR
- Consentimento de usuários
- Proteção de dados pessoais
- Direito de exclusão
- Logs de acesso

### Segurança
- Autenticação forte
- Encriptação de dados sensíveis
- Auditoria de ações
- Backup de dados

## Regras de Domínio

### Conceitos Principais
- Unidade > Equipe > Usuários
- Contratos > Itens > Medições
- Recursos > Alocações > Usos

### Relacionamentos
- Usuários pertencem a unidades
- Recursos pertencem a contratos
- Relatórios pertencem a unidades
- Arquivos pertencem a apontamentos

### Invariantes
- IDs são UUIDs
- Timestamps em UTC
- Soft delete quando possível
- Histórico de mudanças