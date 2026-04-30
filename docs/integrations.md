# Integrações

## Repositórios e Serviços Relacionados

### Serviço de Processamento de Imagens
**Tipo**: Microserviço
**Propósito**: Processamento batch de imagens de apontamentos
**Protocolo**: HTTP/S3
**Dados Trocados**:
- Lista de imagens para download
- Arquivo ZIP consolidado
- Notificações por email
**Dependência**: Média
**Tratamento de Falhas**:
- Retry automático
- Notificação de falhas
- Logs de processamento

### Zip Kartado
**Tipo**: Serviço de Compactação
**Propósito**: Geração de arquivos ZIP sob demanda
**Protocolo**: HTTP API
**Dados Trocados**:
- Requisições HTTP para geração de ZIPs
- Arquivos ZIP gerados
- Status de processamento
**Dependência**: Média
**Configuração**: URL parametrizada como ZIP_DOWNLOAD_URL nas credenciais
**Tratamento de Falhas**:
- Retry automático
- Timeout handling
- Logs de requisição

### Sistema de Criação de Formulários (N8N)
**Tipo**: IA Integration
**Propósito**: Criação automática de OccurrenceTypes
**Protocolo**: HTTP API
**Dados Trocados**:
- Texto de entrada
- Definição de formulário
- Metadados do tipo
**Dependência**: Baixa
**Tratamento de Falhas**:
- Validação de entrada
- Fallback manual
- Logs de geração

### Conversor Excel para PDF
**Tipo**: Serviço de Conversão
**Propósito**: Conversão de relatórios
**Protocolo**: HTTP API
**Dados Trocados**:
- Arquivos Excel
- PDFs gerados
- Status de conversão
**Dependência**: Média
**Tratamento de Falhas**:
- Queue de processamento
- Timeout handling
- Retry policy

### AWS Lambda (Zappa)
**Tipo**: Serverless Computing
**Propósito**: Deploy e execução da aplicação
**Protocolo**: AWS API Gateway
**Dados Trocados**: 
- Requisições HTTP
- Arquivos estáticos
- Logs
**Dependência**: Crítica
**Tratamento de Falhas**: 
- Retries automáticos
- Dead Letter Queues
- CloudWatch Alarms

### AWS S3
**Tipo**: Storage
**Propósito**: Armazenamento de arquivos
**Protocolo**: S3 API
**Dados Trocados**:
- Arquivos estáticos
- Uploads de usuários
- Backups
**Dependência**: Crítica
**Tratamento de Falhas**:
- Retries com backoff
- Validação de uploads
- Multipart para arquivos grandes

### AWS SES
**Tipo**: Email Service
**Propósito**: Envio de emails
**Protocolo**: SMTP/API
**Dados Trocados**:
- Emails transacionais
- Notificações
- Templates
**Dependência**: Alta
**Tratamento de Falhas**:
- Fila de retry
- Bounce handling
- Blacklist automática

### AWS SQS
**Tipo**: Message Queue
**Propósito**: Processamento assíncrono
**Protocolo**: SQS API
**Dados Trocados**:
- Jobs de email
- Processamento de arquivos
- Notificações
**Dependência**: Alta
**Tratamento de Falhas**:
- Dead Letter Queues
- Retry policies
- Visibilidade timeout

### Sentry
**Tipo**: Error Tracking
**Propósito**: Monitoramento de erros
**Protocolo**: HTTP API
**Dados Trocados**:
- Stack traces
- Contexto de erros
- Performance data
**Dependência**: Média
**Tratamento de Falhas**:
- Buffer local
- Amostragem
- Rate limiting

### AWS X-Ray
**Tipo**: Tracing
**Propósito**: Análise de performance
**Protocolo**: X-Ray API
**Dados Trocados**:
- Traces de requests
- Segmentos de execução
- Metadados
**Dependência**: Baixa
**Tratamento de Falhas**:
- Sampling
- Buffering
- Daemon local

## Dependências Externas

### PostgreSQL/PostGIS
- Banco de dados principal
- Extensões espaciais
- Conexão via psycopg2
- Pooling de conexões

### PyMuPDF (fitz)
- Manipulação de arquivos PDF
- Extração de imagens de PDFs
- Análise de layout e estrutura
- Usado no sistema de importação DIN ARTESP ([ver documentação](pdf-import.md))

### pdfminer.six
- Extração de texto de PDFs
- Análise de estrutura de documento
- Detecção de formato de PDF
- Usado no sistema de importação DIN ARTESP ([ver documentação](pdf-import.md))

### Frontend Applications
- Comunicação via API REST
- CORS configurado
- Autenticação via token
- SSO via SAML2

### Cliente Mobile
- Sincronização offline
- Upload de arquivos
- Push notifications
- Versionamento de API

## Eventos

### Eventos Publicados
- user.created
- user.login
- email.sent
- email.bounced
- report.created
- file.uploaded

### Eventos Consumidos
- sqs.email_queue
- sqs.file_processing
- sns.notifications
- cloudwatch.alarms

## Contratos de Integração

### API REST
- Formato JSON:API
- Headers padrão
- Status codes HTTP
- Paginação via offset

### Formatos de Arquivo
- GeoJSON para mapas
- Excel para importação
- PDF para relatórios
- CSV para exportação

### Protocolos de Auth
- JWT tokens
- SAML2 assertions
- API keys
- Basic auth

## Resiliência

### Circuit Breakers
- Timeouts configuráveis
- Retry com backoff
- Fallback handlers
- Estado de health

### Caching
- Redis quando disponível
- Cache-Control headers
- ETags para recursos
- Invalidação seletiva

### Monitoring
- Métricas CloudWatch
- Traces X-Ray
- Logs estruturados
- Alertas Sentry

### Backup
- Snapshots de banco
- Replicação S3
- Exports periódicos
- Retenção configurável