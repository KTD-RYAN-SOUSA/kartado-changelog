# Microserviço Kartado Backend

## Domínio de Responsabilidade
O Kartado Backend é o serviço central de gestão de infraestrutura rodoviária, responsável por:
- Gestão de unidades e usuários
- Controle de recursos e contratos
- Monitoramento e relatórios
- Gestão de dados espaciais (GIS)
- Controle de qualidade
- Processamento de documentos

### Planos de Evolução
1. **Atualizações Planejadas**:
   - Atualização de bibliotecas críticas para versões mais recentes
   - Manutenção da stack tecnológica atual
   - Melhoria contínua do produto

2. **Futura Microsserviços**:
   - Planejamento de migração de algumas funcionalidades para microsserviços
   - Manutenção da arquitetura principal
   - Evolução gradual do sistema

3. **Novas Funcionalidades**:
   - Processo contínuo de adição de features
   - Melhorias baseadas em feedback
   - Evolução do produto

## Regras do Serviço

### Regras de Negócio Específicas
1. **Multi-tenancy**
   - Cada cliente tem seu próprio banco de dados
   - Configurações específicas por cliente
   - Isolamento total de dados

2. **Workflow de Documentos**
   - Upload e validação
   - Processamento assíncrono
   - Armazenamento seguro
   - Controle de versão

3. **Gestão de Recursos**
   - Alocação e tracking
   - Medições e relatórios
   - Controle financeiro
   - Performance metrics

4. **Auto-Scheduling de Programações**
   - Alocação automática de Apontamentos em Programações
   - Regras configuráveis por Unidade via `company.metadata["auto_scheduling_jobs"]`
   - Disparado via signal `post_save` de Reporting e importação Excel
   - Consistência garantida com `transaction.atomic()` e `select_for_update()`
   - Implementação: `helpers/apps/auto_scheduling.py`

### Invariantes do Domínio
- Usuários pertencem a Unidades
- Recursos vinculados a contratos
- Documentos têm criadores
- Dados geográficos validados
- Histórico de mudanças mantido

### Agregados e Entidades
1. **Unidade (Company) Aggregate**
   - Company (Unidade)
   - CompanyGroup (Grupo de unidades)
   - SubCompany (Empresa)
   - UserInCompany (Usuário na unidade)

2. **Resource Aggregate**
   - Resource (Recurso)
   - Contract (Contrato)
   - ServiceOrderResource (Utilização de recurso)

3. **Spatial Aggregate**
   - ShapeFile (Camadas de dados geográficos)
   - TileLayer (Camadas de mapa)

## Comunicação

### Endpoints Expostos
- REST API com JSON:API
- Webhooks para eventos
- File upload endpoints
- Export endpoints

## Persistência

### Bancos de Dados
- PostgreSQL por cliente
- PostGIS para dados espaciais
- Migrations controladas
- Backups automáticos

### Schemas
- Separação por módulo
- Índices otimizados
- Constraints explícitos
- Audit tables

### Caching
- Redis quando disponível
- Cache por cliente
- TTL configurável
- Invalidação seletiva

## Observabilidade

### Logs
- Structured logging
- Log levels apropriados
- Contexto de cliente
- Rotation configurada

### Métricas
- Requisições por endpoint
- Latência de operações
- Uso de recursos
- Erros por tipo

### Traces
- X-Ray habilitado
- Spans nomeados
- Annotations úteis
- Sampling configurado

### Health Checks
- Liveness probe
- Readiness probe
- Deep health check
- Status page

## Pipeline de Deploy (Github)

### Etapas de Deploy
1. **Quality Assurance**
   ```yaml
   - pip install poetry==1.3.1
   - poetry install --extras "ci-tools"
   - poetry run flake8 .
   - poetry run black --check .
   - poetry run isort . --check-only
   ```

2. **Testes**
   ```yaml
   - poetry install --extras "ci-tools"
   - poetry run pytest --ds=RoadLabsAPI.settings.testing
   ```

3. **SonarQube Analysis**
   ```yaml
   - pipe: sonarsource/sonarqube-scan:2.0.1
   ```

4. **Migrate e Deploy**
   ```yaml
   - poetry install --no-dev --only main
   - poetry run python manage.py migrate
   - poetry run zappa update $ZAPPA_ENVIRONMENT_NAME
   ```

5. **Build Docker**
   ```yaml
   - docker build -t kartado_backend/$ZAPPA_ENVIRONMENT_NAME .
   - docker push $AWS_ACCOUNT_ID.dkr.ecr...
   ```

### Ambientes
- Staging General
- Production General
- Production ENGIE
- Production CCR
- Homolog (General/ENGIE/CCR)
- Production ECO

## Resiliência e Escalabilidade

### Circuit Breakers
- Timeouts configurados
- Retry policies
- Fallback handlers
- Estado monitorado

### Auto-scaling
- Baseado em métricas
- Cool-down periods
- Limites configurados
- Alerts definidos

### Recuperação
- Backup restoration
- State recovery
- Event replay
- Data consistency

### Performance
- Query optimization
- Connection pooling
- Batch processing
- Caching strategy

## SLAs e SLOs

### Disponibilidade
- 99.9% uptime
- RPO de 1 hora
- RTO de 4 horas
- Monitoramento 24/7

### Performance
- Latência < 500ms
- Throughput > 100 rps
- CPU < 70%
- Memory < 80%

### Qualidade
- Error rate < 0.1%
- Success rate > 99%
- Coverage > 80%
- Documentation up-to-date