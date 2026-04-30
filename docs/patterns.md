# Padrões de Design

## Padrões Arquiteturais
- **MVT (Model-View-Template)** - Padrão Django tradicional
- **REST API** - Interface de comunicação principal
- **Multi-tenancy** - Separação de dados por cliente via bancos diferentes
- **Event-Driven** - Uso de filas SQS para processamento assíncrono
- **Service Layer** - Lógica de negócio em services.py
- **Factory Pattern** - Criação de extractors de PDF baseado em formato detectado
- **Strategy Pattern** - Diferentes estratégias de extração por formato de PDF
- **Template Method Pattern** - Classe base abstrata definindo fluxo comum de extração

## Padrões de Código

### Exemplo de ViewSet
```python
class ReportingView(viewsets.ModelViewSet):
    serializer_class = ReportingSerializer
    permission_classes = [IsAuthenticated, ReportingPermissions]
    filterset_class = ReportingFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        if "company" not in self.request.query_params:
            return Reporting.objects.none()

        user_company = UUID(self.request.query_params["company"])
        if not self.permissions:
            self.permissions = PermissionManager(
                user=self.request.user,
                company_ids=user_company,
                model="Reporting",
            )
        return get_reporting_queryset(
            user_company, self.request.user, self.permissions
        )
```

### Exemplo de Filter
```python
class ReportingFilter(filters.FilterSet):
    search = CharFilter(method="filter_search")
    company = KeyFilter()
    occurrence_type = UUIDListFilter(field_name="occurrence_type")
    created_at = DateFromToRangeCustomFilter()
    created_by = UUIDListFilter(field_name="created_by")
    
    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(number__icontains=value) |
            Q(description__icontains=value)
        )
```

### Exemplo de Permission
```python
class ReportingPermissions(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        company_param = request.query_params.get("company", None)
        if not company_param:
            return False

        company = UUID(company_param)
        if not user.companies.filter(uuid=company).exists():
            return False

        return True
```

### PermissionManager - Métodos Úteis
O `PermissionManager` (`helpers/permissions.py`) centraliza a lógica de permissões:

```python
# Obter naturezas permitidas para o usuário
allowed_kinds = self.permissions.get_allowed_occurrence_kinds()
if allowed_kinds:
    queryset = queryset.filter(occurrence_kind__in=allowed_kinds)
# Lista vazia = acesso total (retrocompatível)
```

Métodos disponíveis:
- `get_allowed_occurrence_kinds()`: Retorna lista de `occurrence_kind` permitidos (whitelist)
- `get_permissions_objs()`: Retorna objetos `UserPermission` do usuário
- `has_*_permission()`: Verifica permissões específicas por funcionalidade

### Exemplo de Signal
```python
@receiver(post_save, sender=Reporting)
def reporting_post_save(sender, instance, created, **kwargs):
    if created:
        notify_new_reporting.delay(instance.uuid)
```

## Comandos Comuns

### Desenvolvimento
```bash
# Shell Django com autoload de models
python manage.py shell_plus

# Jupyter Notebook com Django
export DJANGO_ALLOW_ASYNC_UNSAFE=1
python manage.py shell_plus --notebook

# Servidor de desenvolvimento
python manage.py runserver 0.0.0.0:8000

# Merge de migrações
python manage.py makemigrations --merge
black . --config pyproject.toml

# Visualizar configurações
python manage.py print_settings
python manage.py print_settings TIME*

# Gerar admin
python manage.py admin_generator <app_name>
```

### Docker
```bash
# Executar comandos no container
docker compose exec app poetry run <comando>
docker compose exec app poetry run ./manage.py <comando>
```

### Deploy
```bash
# QA
poetry run flake8 .
poetry run black .
poetry run isort .

# Testes
poetry run pytest

# Deploy
poetry run zappa update <environment>
```

## Organização de Código
```
apps/                     # Apps Django
    ├── companies/         # Gestão de Unidades
  ├── constructions/     # Obras e construções
  ├── daily_reports/     # Relatórios diários
  ├── files/            # Gestão de arquivos
  ├── monitorings/      # Monitoramento
  ├── notifications/    # Sistema de notificações
  ├── permissions/      # Controle de acesso
  ├── users/           # Gestão de usuários
  └── ...              # Outras apps

RoadLabsAPI/            # Core do projeto
  ├── settings/        # Configurações por ambiente
  ├── urls.py         # URLs principais
  └── wsgi.py         # Config WSGI

helpers/               # Código auxiliar comum
scripts/              # Scripts utilitários
tests/                # Testes
```

## Convenções de Nomenclatura
- Apps em plural e minúsculo
- Models em PascalCase singular
- ViewSets sufixo ViewSet
- Serializers sufixo Serializer
- Migrations numeradas e descritivas
- URLs em kebab-case

## Padrões de Teste
- pytest como framework principal de testes
- Fixtures em conftest.py para criar banco de dados fictício
- Testes unitários obrigatórios para código novo
- Testes de comportamento esperado
- Verificação de regressão em código existente
- Testes organizados por apps
- Mocks para serviços externos
- Coverage para análise de cobertura

### Processo de Teste
1. Criar fixtures necessárias em conftest.py
2. Implementar testes unitários para novo código
3. Verificar comportamentos esperados
4. Validar que alterações não afetam código existente
5. Manter cobertura de testes adequada

## Padrões de Tratamento de Erros
- Sentry para logging de erros
- X-Ray para tracing
- Custom exception handler
- Error responses em JSON API
- Validação em serializers
- Try/except em pontos críticos

## Boas Práticas Específicas
1. **Code Style**
   - Black para formatação
   - isort para imports
   - flake8 para linting
   - Docstrings em inglês

2. **Database**
   - Atomic transactions
   - Select_related/Prefetch para N+1
   - Índices para campos de busca
   - Migrations atômicas

3. **Security**
   - SAML2 auth
   - Token authentication
   - Permission classes
   - SSL everywhere
   - Input validation

4. **Performance**
   - Query optimization
   - Caching quando possível
   - Paginação por default
   - Background tasks para processos pesados