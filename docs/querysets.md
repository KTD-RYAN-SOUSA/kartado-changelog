# Querysets do Kartado Backend

## Visão Geral

Os querysets são mecanismos de controle de acesso que determinam quais registros (apontamentos, jobs, arquivos, etc.) um usuário pode visualizar e manipular no sistema. Eles são aplicados através do sistema de permissões e fazem parte da arquitetura de segurança multi-tenant do Kartado.

## Como Funcionam

Os querysets são definidos nas permissões de usuário (UserPermission) e aplicados dinamicamente nas views através da classe `PermissionManager` (localizada em `helpers/permissions.py`). Cada queryset implementa uma lógica específica de filtragem de dados.

## Querysets Disponíveis

### 1. `none`

**O que faz:**
- Não permite acessar nenhum objeto
- Retorna um queryset vazio

**Quando usar:**
- Para perfis que não devem ter acesso a determinado tipo de recurso
- Como configuração padrão quando nenhuma permissão é concedida

**Exemplo real:**
```python
# Em apps/reportings/views.py
if "none" in allowed_queryset:
    queryset = join_queryset(queryset, Reporting.objects.none())
```

**Caso de uso:**
- Usuário com perfil "Inativo" não deve visualizar nenhum apontamento

---

### 2. `self`

**O que faz:**
- Permite acessar apontamentos criados pelo próprio usuário
- Permite acessar apontamentos associados a jobs onde o usuário:
  - É trabalhador (worker)
  - É criador (created_by)
  - É observador (watcher_users)
  - Pertence a uma firma associada ao job (firm, watcher_firms)
  - Pertence a uma subempresa observadora do job (watcher_subcompanies)

**Quando usar:**
- Para usuários que devem ver apenas seus próprios registros
- Perfis de campo/operacionais com acesso limitado

**Exemplo real:**
```python
# Em apps/reportings/views.py (linhas 478-484)
if "self" in allowed_queryset:
    queryset = join_queryset(
        queryset,
        Reporting.objects.filter(
            Q(created_by=request.user) | Q(job__in=jobs)
        ),
    )
```

**Caso de uso:**
- Inspetor de campo visualiza apenas os apontamentos que ele criou
- Técnico vê apenas jobs onde está designado como trabalhador

---

### 3. `firm`

**O que faz:**
- Permite acessar apontamentos criados por **qualquer usuário das firmas** (equipes) do usuário atual
- Inclui apontamentos acessíveis pelo queryset `self`
- Filtra registros relacionados às firmas específicas onde o usuário está vinculado

**Regra importante:**
- Se o usuário está em **múltiplas firmas**, ele vê dados de **cada firma separadamente**
- Não vê dados de firmas onde não está vinculado

**Exemplo real:**
```python
# Em apps/reportings/views.py (linhas 494-529)
if "firm" in allowed_queryset:
    # Obtém usuários relacionados às firmas do usuário atual
    related_users = User.objects.filter(user_firms__in=user_firms).distinct()

    queryset = join_queryset(
        queryset,
        Reporting.objects.filter(
            Q(company_id=user_company) & (
                Q(firm__in=user_firms) |
                Q(created_by__in=related_users) |
                Q(job__in=jobs)
            )
        )
    )
```

**Caso de uso:**
- Coordenador de uma equipe vê todos os apontamentos da sua equipe
- Gerente vinculado a 3 equipes vê dados das 3 equipes (mas não de outras)

---

### 4. `self_and_created_by_firm`

**O que faz:**
- Estende o queryset `firm` incluindo **firmas criadas** por usuários relacionados
- Permite acessar apontamentos de usuários que:
  - Pertencem às mesmas firmas do usuário atual
  - Pertencem a firmas **criadas** por usuários das firmas do usuário atual

**Diferença do `firm`:**
- `firm`: Vê apenas usuários das firmas onde está vinculado
- `self_and_created_by_firm`: Vê também usuários de firmas criadas por colegas de equipe

**Exemplo real:**
```python
# Em apps/reportings/views.py (linhas 531-557)
if "self_and_created_by_firm" in allowed_queryset:
    # Expande para incluir firmas criadas por usuários relacionados
    related_firms = Firm.objects.filter(created_by__in=related_users).distinct()
    user_firms.extend(related_firms)

    # Obtém usuários das novas firmas relacionadas
    related_firm_users = User.objects.filter(user_firms__in=related_firms).distinct()
    related_users = (related_users | related_firm_users).distinct()
```

**Caso de uso:**
- Gerente cria uma nova equipe para um projeto específico
- Coordenador da equipe original consegue ver apontamentos da nova equipe criada pelo gerente

---

### 5. `artesp`

**O que faz:**
- Permite acessar apontamentos que possuem um **código ARTESP** associado
- Filtra apenas registros com `form_data.artesp_code` preenchido

**Quando usar:**
- Para usuários que precisam ver apenas apontamentos reportados à agência ARTESP
- Perfis de fiscalização e auditoria

**Exemplo real:**
```python
# Em apps/reportings/views.py (linhas 558-565)
if "artesp" in allowed_queryset:
    queryset = join_queryset(
        queryset,
        Reporting.objects.filter(
            company_id=user_company,
            form_data__artesp_code__isnull=False,
        ).exclude(form_data__artesp_code__exact=""),
    )
```

**Caso de uso:**
- Usuário da sala técnica ARTESP visualiza apenas apontamentos com código ARTESP
- Relatórios de exportação para a agência reguladora

---

### 6. `artesp_entrevias`

**O que faz:**
- Queryset especializado para a empresa **Entrevias**
- Exclui tipos específicos de ocorrências e firmas históricas
- Configurações definidas nos metadados da empresa (`company.metadata`)

**Regras:**
- Exclui ocorrências com `occurrence_kind` especificado em metadados
- Exclui firmas históricas definidas em `metadata.artesp_exclude.historical_firm`
- Aplica-se apenas a apontamentos após 01/01/2020

**Exemplo real:**
```python
# Em apps/reportings/views.py (linhas 566-605)
if "artesp_entrevias" in allowed_queryset:
    kinds = get_obj_from_path(company.metadata, "artesp_exclude__occurrence_kind")
    firms = get_obj_from_path(company.metadata, "artesp_exclude__historical_firm")

    queryset = join_queryset(
        queryset,
        queryset_company.filter(found_at__gte="2020-01-01").exclude(
            (Q(occurrence_type__occurrence_kind__in=kinds) |
             Q(historicalreporting__in=histories)) &
            (Q(form_data__artesp_code__isnull=True) |
             Q(form_data__artesp_code__exact=""))
        ),
    )
```

**Caso de uso:**
- Usuários da Entrevias com regras específicas de visualização
- Exclusão de tipos de ocorrência e firmas antigas de relatórios ARTESP

---

### 7. `antt_supervisor_agency`

**O que faz:**
- Permite acessar apontamentos **compartilhados com a agência ANTT**
- Filtra apenas registros com `shared_with_agency=True`

**Quando usar:**
- Para usuários da agência reguladora ANTT
- Visualização de dados compartilhados pela concessionária

**Exemplo real:**
```python
# Em apps/reportings/views.py (linhas 607-611)
if "antt_supervisor_agency" in allowed_queryset:
    queryset = join_queryset(
        queryset,
        Reporting.objects.filter(
            company=user_company,
            shared_with_agency=True
        ),
    )
```

**Caso de uso:**
- Fiscais da ANTT visualizam apenas apontamentos compartilhados
- Relatórios específicos para a agência reguladora

---

### 8. `supervisor_agency`

**O que faz:**
- Permite acessar apontamentos relacionados a:
  - Construções de origem `AGENCY` (obras da agência)
  - Apontamentos com código ARTESP

**Quando usar:**
- Para usuários de agências reguladoras genéricas (ARTESP, ANTT, etc.)
- Visualização de construções cadastradas pela agência

**Exemplo real:**
```python
# Em apps/reportings/views.py (linhas 612-627)
if "supervisor_agency" in allowed_queryset:
    queryset = join_queryset(
        queryset,
        Reporting.objects.filter(
            Q(company_id=user_company) & (
                Q(reporting_construction_progresses__construction__origin="AGENCY") |
                (Q(form_data__artesp_code__isnull=False) &
                 ~Q(form_data__artesp_code__exact=""))
            )
        ),
    )
```

**Caso de uso:**
- Usuário da ARTESP vê construções cadastradas pela agência
- Fiscalização de obras com código ARTESP

---

### 9. `all`

**O que faz:**
- Permite acessar **todos os apontamentos da empresa** do usuário
- Sem restrições de firma, criador ou jobs

**Quando usar:**
- Para administradores e gerentes com visão completa
- Perfis de alto nível hierárquico

**Exemplo real:**
```python
# Em apps/reportings/views.py (linhas 628-631)
if "all" in allowed_queryset:
    queryset = join_queryset(
        queryset,
        Reporting.objects.filter(company_id=user_company)
    )
```

**Caso de uso:**
- Diretor da concessionária vê todos os apontamentos
- Administrador do sistema com acesso total

---

## Onde os Querysets São Aplicados

Os querysets são aplicados principalmente em:

1. **Reportings (Apontamentos)**: `apps/reportings/views.py`
2. **Jobs (Apontamentos de Plano)**: `apps/work_plans/views.py`
3. **Resources (Recursos)**: `apps/resources/views.py`
4. **Constructions (Construções)**: `apps/constructions/views.py`
5. **Files (Arquivos)**: `apps/files/views.py`

## Implementação Técnica

### Arquivo Principal
- `helpers/permissions.py`: Classe `PermissionManager` gerencia os querysets
- Método `get_allowed_queryset()`: Retorna lista de querysets permitidos para o usuário

### Fluxo de Aplicação
1. View recebe requisição do usuário
2. `PermissionManager` é instanciado com company_id e user
3. Sistema busca permissões do usuário em `UserInCompany`
4. `get_allowed_queryset()` retorna lista de querysets permitidos
5. View aplica filtros correspondentes ao(s) queryset(s)
6. Queryset final é retornado ao usuário

### Exemplo de Código
```python
# Em uma view
def get_queryset(self):
    permissions = PermissionManager(
        user=request.user,
        company_ids=user_company,
        model="Reporting"
    )

    allowed_queryset = permissions.get_allowed_queryset()

    if "self" in allowed_queryset:
        queryset = Reporting.objects.filter(created_by=request.user)

    if "firm" in allowed_queryset:
        queryset = queryset | Reporting.objects.filter(
            firm__in=user_firms
        )

    return queryset.distinct()
```

## Perfis e Querysets Comuns

| Perfil | Querysets Comuns | Descrição |
|--------|------------------|-----------|
| **Inativo** | `none` | Sem acesso a dados |
| **Inspetor** | `self` | Apenas seus registros |
| **Coordenador** | `firm` | Dados da(s) equipe(s) |
| **Gerente** | `firm`, `self_and_created_by_firm` | Dados das equipes e equipes criadas |
| **Engenheiro** | `all` | Todos os dados da empresa |
| **ARTESP** | `artesp`, `supervisor_agency` | Dados reportados à agência |
| **ANTT** | `antt_supervisor_agency` | Dados compartilhados com ANTT |
| **Terceiro** | `self` | Apenas seus próprios registros |

## Segurança

⚠️ **Importante:**
- Querysets são a **primeira linha de defesa** no controle de acesso
- Sempre são aplicados **antes** de retornar dados ao usuário
- Não podem ser contornados pelo frontend
- São validados a cada requisição
- Multi-tenant: sempre filtram por `company_id`

## Performance

💡 **Otimizações:**
- Queryset `all` **não** aplica `distinct()` quando não há filtros adicionais
- Uso de `select_related()` e `prefetch_related()` para reduzir queries
- Índices de banco de dados em campos de filtro comuns

## Referências

- Implementação principal: `apps/reportings/views.py` (função `get_reporting_queryset()`)
- Gerenciador de permissões: `helpers/permissions.py` (classe `PermissionManager`)
- Testes: `apps/reportings/tests/test_reporting_permissions.py`
- Fixtures de exemplo: `fixtures/mock_concessionaria/permissions/`

---

**Última atualização:** 2026-03-01
**Versão:** 1.0
