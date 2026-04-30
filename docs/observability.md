# Observabilidade

## Visão Geral

O Kartado Backend utiliza três pilares de observabilidade:

| Pilar | Ferramenta | Propósito |
|---|---|---|
| **Rastreamento de Erros** | Sentry | Exceções, contexto de usuário, alertas |
| **Tracing de Requisições** | AWS X-Ray | Latência, rastreamento de queries, gargalos |
| **Métricas** | AWS CloudWatch | Filas de email, push notifications, SQS |

---

## Sentry

### Configuração por Ambiente

O Sentry é inicializado em cada settings de ambiente com o campo `environment` diferenciado. Os parâmetros base estão em `RoadLabsAPI/settings/base.py`:

```python
SENTRY_SAMPLE_RATE = 1.0         # 100% dos erros são capturados
SENTRY_TRACES_SAMPLE_RATE = 0.005  # 0,5% das transações são amostradas (performance)
```

| Ambiente | `environment` no Sentry | Settings |
|---|---|---|
| Production General | `production` | `settings/production.py` |
| Staging General | `staging` | `settings/staging.py` |
| Homolog | `homolog` | `settings/homolog.py` |
| Production CCR | `production-ccr` | `settings/ccr/production.py` |
| Production ENGIE | `production-engie` | `settings/engie/production.py` |

Exemplo de inicialização (padrão em todos os ambientes):

```python
# RoadLabsAPI/settings/production.py:122
sentry_sdk.init(
    dsn=credentials.SENTRY_DATA_SOURCE_NAME,
    environment="production",
    integrations=[DjangoIntegration()],
    sample_rate=SENTRY_SAMPLE_RATE,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    send_default_pii=True,  # inclui dados do usuário no contexto
)
ignore_logger("cssutils")
```

> **Nota:** O Sentry **não é inicializado** nos ambientes `development` e `testing`. Erros em desenvolvimento aparecem apenas no terminal.

### Como Usar no Código

O padrão do projeto é combinar `logging.error()` com `sentry_sdk.capture_exception()` em blocos `except`:

```python
import logging
import sentry_sdk

try:
    resultado = operacao_critica()
except Exception as e:
    logging.error(f"Mensagem descritiva: {str(e)}")
    sentry_sdk.capture_exception(e)
```

Esse padrão está presente em:
- `apps/notifications/services.py` — falhas no SQS e inicialização do Firebase
- `apps/work_plans/asynchronous.py` — erros em batches de Job
- `apps/files/signals.py` — erros no processamento de arquivos
- `apps/service_orders/helpers/email_judiciary/send_emails.py` — erros no envio de emails
- `helpers/import_pdf/read_pdf.py` — erros na importação de PDF

#### Rate Limit com Sentry

Quando o rate limit é excedido (429), a exceção é capturada automaticamente (`helpers/middlewares.py`):

```python
def ratelimit_exceeded_view(request, exception):
    if isinstance(exception, Ratelimited):
        sentry_sdk.capture_exception(exception)
        return JsonResponse({"detail": "Too many requests"}, status=429)
```

### Navegando no Sentry

Acesse o projeto com o nome `backend` no Sentry. Use o filtro de `environment` no topo da página para isolar por cliente/ambiente:

- `production` → instância geral de produção (https://app.kartado.com.br/)
- `staging` → instância geral de homologação
- `production-engie` → produção ENGIE (https://engie.kartado.com.br/)
- `staging-engie` → homologação ENGIE

Cada issue exibe: stack trace completo, dados do usuário autenticado (via `send_default_pii=True`), cabeçalhos da requisição e contexto de ambiente.

---

## AWS X-Ray

### Configuração

O X-Ray é ativado via `INSTALLED_APPS` e `MIDDLEWARE` em `RoadLabsAPI/settings/base.py`:

```python
INSTALLED_APPS = [
    ...
    "aws_xray_sdk.ext.django",
]

MIDDLEWARE = [
    "helpers.middlewares.RawRequestBodyMiddleware",
    "helpers.middlewares.ActionLogMiddleware",
    "aws_xray_sdk.ext.django.middleware.XRayMiddleware",  # registra cada request
    ...
]
```

Em produção (`settings/production.py:58`):

```python
AWS_XRAY_TRACING_NAME = "HidrOS-Production"
XRAY_RECORDER = {
    "AUTO_INSTRUMENT": True,  # instrumenta queries DB e templates automaticamente
    "AWS_XRAY_CONTEXT_MISSING": "LOG_ERROR",
    "SAMPLING": True,
    "AWS_XRAY_TRACING_NAME": "HidrOS-Production",
}
```

| Ambiente | Nome do trace |
|---|---|
| Production | `HidrOS-Production` |
| Staging | `HidrOS-Staging` |

> **Nota:** O X-Ray é **desativado automaticamente** em desenvolvimento (`settings/development.py:56`). Não é necessário configurar nada localmente.

### O que o X-Ray Registra

Com `AUTO_INSTRUMENT: True`, o X-Ray captura automaticamente:
- Duração de cada requisição HTTP
- Queries ao banco de dados (SQL e tempo de execução)
- Rendering de templates Django
- Chamadas a serviços AWS (S3, SQS, SES via boto3)

Use o console do AWS X-Ray para:
- Identificar endpoints lentos
- Inspecionar queries N+1
- Analisar tempo gasto em operações S3/SQS
- Rastrear uma requisição do início ao fim (trace completo)

---

## CloudWatch — Métricas Customizadas

### Função `send_aws_metrics`

A função `send_aws_metrics()` em `helpers/aws.py` é chamada a cada **5 minutos** via SQS e publica métricas no CloudWatch:

#### Namespace: `Email Metrics`

| Métrica | Descrição |
|---|---|
| `Unsent Emails` | Emails na fila aguardando envio |
| `Error Emails` | Emails com falha de envio |
| `In Progress Emails` | Emails sendo processados no momento |

#### Namespace: `Push Notification Metrics`

| Métrica | Descrição |
|---|---|
| `Unsent Pushs` | Notificações push aguardando envio |
| `In Progress Pushs` | Notificações em processamento |
| `SQS Messages In Queue` | Mensagens na fila SQS |
| `SQS Messages In Flight` | Mensagens sendo processadas pelo SQS |
| `SQS Messages Delayed` | Mensagens com entrega atrasada |

Use essas métricas para criar alarmes no CloudWatch quando filas acumulam (ex: `Unsent Emails > 100`) ou quando o processamento trava (`In Progress Emails` alto por muito tempo).

---

## Endpoint de Health Check

O endpoint `/api/SQSMonitoring/` (requer autenticação) retorna o status operacional do SQS e métricas de banco em tempo real (`apps/notifications/views.py`):

```json
{
  "sqs_status": {
    "enabled": true,
    "client_initialized": true,
    "queue_url": "https://sqs.sa-east-1.amazonaws.com/..."
  },
  "queue_metrics": {
    "messages_in_queue": 0,
    "messages_in_flight": 0,
    "messages_delayed": 0
  },
  "database_metrics": {
    "unsent_notifications": 5,
    "in_progress_notifications": 0,
    "total_notifications_today": 142
  },
  "timestamp": "2026-03-02T10:30:00Z"
}
```

---

## Logging

### Configuração Base

Os loggers de bibliotecas AWS são suprimidos para reduzir ruído (`RoadLabsAPI/settings/base.py:282`):

```python
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("s3transfer").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
```

### Padrão de Uso no Código

O projeto usa o módulo `logging` padrão do Python. Use `logging.error()` para falhas e `logging.info()` para eventos relevantes:

```python
import logging

# Operação bem-sucedida
logging.info("PDF parsing done!")

# Falha esperada com contexto
logging.error(f"Failed to publish notification {notification_id} to SQS: {str(e)}")

# Falha crítica (combine com Sentry)
logging.error("Error while building job querysets")
sentry_sdk.capture_exception(e)
```

### Onde Ver os Logs

| Ambiente | Destino |
|---|---|
| Local (Docker) | `docker compose logs -f app` |
| Staging / Production | AWS CloudWatch Logs (grupos criados pelo Zappa) |

---

## Silêncio de Observabilidade

Ambientes onde as ferramentas **não estão ativas**:

| Ambiente | Sentry | X-Ray |
|---|---|---|
| `development` | ❌ | ❌ |
| `testing` | ❌ | ❌ |
| `staging` | ✅ | ✅ |
| `production*` | ✅ | ✅ |

---

## Checklist ao Investigar um Bug em Produção

1. **Sentry** → Filtre pelo ambiente correto, veja o stack trace e dados do usuário
2. **AWS X-Ray** → Localize o trace pelo timestamp/request ID para ver queries e latência
3. **CloudWatch Logs** → Busque por `logging.error` próximo ao timestamp
4. **CloudWatch Metrics** → Verifique se filas de email/push estavam acumuladas no momento
5. **Health Check** → Acesse `/api/SQSMonitoring/` para validar estado atual das filas

---

## Dependências

```toml
# pyproject.toml
sentry-sdk = "2.19.*"
aws-xray-sdk = "2.10.*"
```

## Referências

- [Sentry Django Integration](https://docs.sentry.io/platforms/python/integrations/django/)
- [AWS X-Ray SDK para Python](https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-python.html)
- [CloudWatch Metrics com boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cloudwatch.html)
- Implementação: `helpers/aws.py`, `RoadLabsAPI/settings/production.py`, `apps/notifications/views.py`
