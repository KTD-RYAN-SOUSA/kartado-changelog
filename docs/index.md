# Documentação do Kartado Backend

## Visão Geral
O Kartado Backend é a aplicação principal que contém todo o código backend utilizado na plataforma Kartado, uma solução para gestão de infraestrutura rodoviária. O sistema suporta múltiplos clientes (CCR, Engie, etc.) com configurações e bases de dados totalmente separadas, cada um em seu próprio ambiente AWS com instâncias RDS dedicadas. O sistema integra-se com serviços externos através de APIs HTTP e chaves de acesso.

## Documentação Disponível

### Arquitetura e Stack
- [Stack Tecnológica](stack.md) - Tecnologias, frameworks e ferramentas utilizadas
- [Padrões de Design](patterns.md) - Padrões arquiteturais e de código

### Funcionalidades e Regras
- [Funcionalidades](features.md) - Descrição das funcionalidades principais
- [Regras de Negócio](business-rules.md) - Regras de negócio implementadas

### Sistema filtragem de dados
- [Querysets](querysets.md) - Sistema de controle de acesso e filtragem de dados

### Integrações
- [Integrações](integrations.md) - Comunicação com outros serviços e repositórios

### APIs e Serviços
- [Especificação de APIs](apis.md) - Endpoints, contratos e exemplos
- [Microserviços](services.md) - Regras e responsabilidades do serviço
- [Observabilidade](observability.md) - Sentry, X-Ray, CloudWatch e logging

## Links Rápidos
- Ambiente de Desenvolvimento: Utiliza Docker e Poetry para gerenciamento de dependências
- Deploy: AWS Lambda via Zappa
- Staging: https://api.hidros.staging.roadlabs.com.br
- Produção: https://api.hidros.roadlabs.com.br