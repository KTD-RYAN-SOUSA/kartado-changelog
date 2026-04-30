# Stack Tecnológica

## Linguagens e Runtime
- Python (verificar versão em pyproject.toml)
- Runtime: AWS Lambda

## Frameworks Principais
- Django - Framework web principal
- Django REST Framework - API REST
- Zappa - Deploy serverless para AWS Lambda

## Bibliotecas Chave
- python-decouple - Gerenciamento de configurações
- psycopg2 - Conexão com PostgreSQL
- sentry-sdk - Monitoramento de erros
- boto3 - Integração com AWS
- django-filter - Filtragem de querysets
- django-storages - Armazenamento em S3
- aws-xray-sdk - Tracing de requests

## Banco de Dados
- PostgreSQL/PostGIS (Espacial)
- Múltiplos bancos por cliente (CCR, Engie, etc)
- Migrations Django para versionamento

## Infraestrutura
- AWS Lambda (Serverless)
- AWS S3 (Armazenamento)
- AWS SES (Email)
- AWS SQS (Filas)
- AWS CloudWatch (Logs/Métricas)
- AWS X-Ray (Tracing)
- Sentry (Monitoramento de Erros)

## Ferramentas de Desenvolvimento
- Poetry - Gerenciamento de dependências
- Black - Formatação de código
- isort - Ordenação de imports
- pytest - Framework de testes
- Docker/docker-compose - Containers

## Arquitetura Geral
- Arquitetura baseada em apps Django
- API REST com Django REST Framework
- Multitenancy por banco de dados
- Autenticação via token e SAML2
- Uploads para S3 (público/privado)
- Background tasks via SQS

## Decisões Arquiteturais Importantes
- Serverless com Zappa para redução de custos e escalabilidade
- Múltiplos bancos para isolamento de clientes
- AWS S3 para armazenamento de arquivos estáticos e mídia
- Email via AWS SES com blacklist e tracking
- SAML2 para autenticação corporativa