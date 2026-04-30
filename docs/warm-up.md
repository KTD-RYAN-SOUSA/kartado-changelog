# Guia de Warm-up para Documentação

Este guia fornece um roteiro estruturado para que IAs possam rapidamente compreender o projeto e manter/expandir a documentação de forma eficiente.

## 1. Estrutura do Projeto e Nomenclatura

### Mapeamento de Termos
Termos técnicos devem seguir este mapeamento em toda documentação:
- `Job` → "Programação" (plural: "Programações")
- `Company` → "Unidade"
- `Firm` → "Equipe"
- `OccurrenceType` → "Classe"
- `number` (campo) → "Serial"
- `Reporting` → "Apontamento"

### Apps Principais (apps/)
1. `reportings/`: Módulo central de Apontamentos
   - Models: `Reporting`, `ReportingFile`, `ReportingMessage`
   - Fluxos: aprovação, anexos, geoespacial
   - Endpoints: `/api/Reporting/`, `/api/Reporting/Spreadsheet/`, etc.

2. `work_plans/`: Módulo de Programações
   - Models: `Job`, `JobAsyncBatch`
   - Relacionamento M2M com Apontamentos
   - Processamento assíncrono via batches

3. `companies/`: Gestão de Unidades
   - Multi-tenancy por Unidade (bancos isolados)
   - Metadados críticos em `company.metadata`

### Helpers (helpers/)
- `helpers/apps/job.py`: Funções core para Programações
- `helpers/apps/reportings.py`: Helpers de Apontamentos
- `helpers/apps/auto_scheduling.py`: Lógica de auto-scheduling (alocação automática de Apontamentos em Programações)
- `helpers/fields.py`: Fields customizados (ex: FeatureCollectionField)
- `helpers/km_converter.py`: Cálculos geoespaciais

## 2. Ordem de Leitura Recomendada

Para entender o projeto, siga esta ordem de leitura:

1. Documentação de Features (`docs/features.md`)
   - Foco inicial: seções de Apontamentos e Programações
   - Observe regras de negócio e fluxos principais

2. Documentação de APIs (`docs/apis.md`)
   - Endpoints especiais e payloads
   - Observe formatos de resposta e validações

3. Regras de Negócio (`docs/business-rules.md`)
   - Metadados obrigatórios por Unidade
   - Validações e constraints

4. Código Fonte (ordem sugerida)
   - Models: entender estrutura de dados
   - Serializers: regras de validação
   - Views: endpoints e ações
   - Helpers: lógica de negócio core

## 3. Pontos Críticos para Documentação

### Apontamentos (Reporting)
1. Formulários Dinâmicos
   - `form_data`: dados do usuário
   - `form_metadata`: comportamento/validações
   - Campos com lógica (json-logic)

2. Fluxo de Aprovação
   - ApprovalFlow → ApprovalStep → ApprovalTransition
   - Estados e transições permitidas

3. Geoespacial
   - Cálculo de `end_km`
   - GeometryCollection e FeatureCollectionField

### Programações (Job)
1. Regras de Status
   - Status ordem < 2 muda para ordem 2 ao entrar em Job
   - Restauração ao remover (se não mudou durante vínculo)
   - `executed_status_order` obrigatório/único por Unidade

2. Menu Obrigatório
   - ForeignKey para RecordMenu
   - Obrigatório para inventory/recuperation

3. Sync Mobile
   - `can_be_synced` baseado em `processing_async_creation` e limites
   - `max_reportings_by_job` no metadata da Unidade

4. Processamento Batch
   - `JobAsyncBatch` para grandes volumes
   - Tipos: FILTERED e MANUAL
   - Desconexão de signals durante processamento

5. Auto-Scheduling
   - Configuração via `company.metadata["auto_scheduling_jobs"]`
   - Campos no Job: `is_automatic`, `has_auto_allocated_reportings`
   - Regras de match: `occurrence_type`, `occurrence_kind`, `form_field`
   - Disparado via signal `post_save` de Reporting e importação Excel
   - Filtro de API: `auto_scheduling=True/False` no endpoint `/api/Job/`
   - Implementação core: `helpers/apps/auto_scheduling.py`
   - Testes: `helpers/tests/test_auto_scheduling.py`

## 4. Padrões de Documentação

### Formatação
- Use backticks para nomes de campos/classes: \`Job\`, \`company\`
- Use links relativos para referenciar outros docs
- Mantenha hierarquia clara com headers (##, ###)

### Exemplos
- Inclua exemplos de payload quando relevante
- Demonstre fluxos comuns com passos numerados
- Documente casos de erro/edge cases

### Seções Obrigatórias
1. Descrição geral do módulo/feature
2. Campos e relacionamentos importantes
3. Regras de negócio e validações
4. Endpoints e ações disponíveis
5. Referências para implementação

## 5. Checklist de Validação

Antes de commitar mudanças na documentação:

- [ ] Nomenclatura consistente (conforme mapeamento)
- [ ] Links funcionando (entre arquivos .md)
- [ ] Exemplos de código atualizados
- [ ] Regras de negócio verificadas com código
- [ ] Formatação mantida (Markdown)

## 6. Dicas para Manutenção

1. Mantenha documentação próxima ao código
   - Atualize docs ao mudar regras de negócio
   - Verifique impacto em outros arquivos

2. Pergunte ao time sobre:
   - Exceções às regras por Unidade
   - SLAs e limites específicos
   - Comportamentos mobile/sync
   - Novas features planejadas

3. Sempre verifique:
   - Código em `models.py`
   - Validações em serializers
   - Helpers relacionados
   - Testes unitários (para regras)

## 7. Arquivos de Referência

```
docs/
├── features.md     # Features e funcionalidades
├── apis.md         # Endpoints e payloads
├── business-rules.md # Regras de negócio
├── patterns.md     # Padrões de código
├── services.md     # Serviços e integrações
└── warm-up.md      # Este guia
```

## 8. Contribuindo

Ao adicionar nova documentação:

1. Verifique nomenclatura atual
2. Mantenha estilo consistente
3. Inclua exemplos práticos
4. Referencie código fonte
5. Valide com time técnico

## 9. Troubleshooting

Problemas comuns e soluções:

1. Conflito de termos
   - Sempre use mapeamento oficial
   - Atualize todos os arquivos impactados

2. Regras complexas
   - Quebre em partes menores
   - Use exemplos concretos
   - Referencie código fonte

3. Mobile/Sync
   - Verifique limites por Unidade
   - Documente estados possíveis
   - Inclua mensagens de erro

4. Processamento batch
   - Explique triggers/condições
   - Documente tempo esperado
   - Liste pontos de falha