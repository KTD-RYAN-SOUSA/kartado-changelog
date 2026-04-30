# Kartado Backend API

Esse projeto é uma API escrita usando [**Django**](https://docs.djangoproject.com/en/2.2/) e a [Django Rest Framework](https://www.django-rest-framework.org/). Ela é publicada na AWS utilizando o [Zappa](https://github.com/zappa/Zappa) e roda de forma "serverless".

Abaixo estão as informações necessárias para que você consiga instalar e rodar a API localmente.

## Instalando o projeto

### Instale o Docker

Você precisará instalar o Docker na sua máquina para rodar nosso container. As instruções de instalação estão disponívels [aqui](https://docs.docker.com/engine/install/) e variam de acordo com qual sistema operacional você está usando.

Selecione o seu sistema operacional e siga as instruções da documentação.

Observação: Você também precisará do docker compose. Segundo a documentação do docker, novas instalações já devem vir acompanhadas do compose. Sem necessidade de instalações adicionais.

Você pode encontrar as diferenças entre a versão 1 e versão 2 do docker compose [aqui](https://docs.docker.com/compose/migrate/). Nas instruções vamos assumir que você possui a versão 2 instalada; onde o comando é `docker compose` em vez de `docker-compose`. Caso você ainda use a versão 1, substituir os comandos por `docker-compose` deve funcionar.

### Construa a imagem

Agora que temos o Docker instalado, precisamos baixar e construir as dependências.

Em um terminal, navegue até a pasta onde você baixou o repositório e rode o seguinte comando:

```bash
docker compose build
```

Após construir a imagem, podemos rodar o projeto com:

```bash
docker compose up -d
```

A flag `-d` significa "detach" e faz com que o projeto rode sem usar a linha de comando atual como saída dos logs. Se você quer ver esses logs no terminal atual, omita a flag.

Parar de rodar um container que está executando em modo "detach" é possível com o comando:

```bash
docker compose stop
```

## Preparando o banco de dados

### Aplicando um .dump para popular o banco

Você provavelmente receberá um arquivo de dump do banco de dados para popular sua instância local. Caso você não tenha recebido entre em contato com o seu tech lead ou leia a sessão abaixo com as informações para criar um banco de dados atualizado. As instruções a seguir assumem que o container está rodando e que você possui um arquivo de dump.

Antes de tudo precisamos saber o nome do container rodando o postgres. Você pode descobrir isso rodando o seguinte:

```bash
docker ps
```

Na lista você verá a instância do postgres com seu nome do container e ID.

Copie o seu arquivo dump para dentro do container com o comando:

```bash
docker cp </path/to/dump/file.dump> <container_name>:.
```

Onde `</path/to/dump/file.dump>` é o caminho até onde você salvou o arquivo dump e `<container_name>` o nome do container que obtemos com o `docker ps`.

Agora que copiamos o arquivo, podemos aplicar comando para popular o seu banco com os dados:

```bash
docker exec <container_name> pg_restore -U postgres -d hidros-local <file.dump>
```

Onde `<file.dump>` é o caminho para o arquivo que copiamos para o container. Como ele está na raiz podemos só utilizar seu nome.

Essa operação pode levar um tempo para terminar.

### Aplicando as migrações que faltaram

A depender da idade do seu dump, novas migrações podem ter acontecido desde que ele foi criado. O dump já contará com algumas migrações mas precisamos aplicar as novas.

Garanta que você está na branch `master` do repositório e rode o seguinte comando para aplicar as migrações:

```bash
docker compose exec app poetry run ./manage.py migrate contenttypes
```
```bash
docker compose exec app poetry run ./manage.py migrate
```

Essa operação também pode levar um tempinho para terminar.

## Criando um banco de dados local

Para criar um `dump` é necessário entrar no container do `postgres` no terminal:

```bash
docker compose exec postgis bash
```

Você pode gerar um arquivo `dump` completo, com todas as tabelas do ambiente de homologação. Abaixo, a referência de banco de dados é para o ambiente de homologação de energia, se você quiser fazer um banco de dados para diferentes ambientes verifique as alterações necessárias no arquivo `credentials.py`.

O comando `pg_dump` é para realizar o backup do banco de dados PostgreSQL.

O comando `-h` especifica o endereço do host onde está localizado o banco de dados PostgreSQL que você deseja fazer o backup, é necessário adicionar o endereço do host onde o banco de dados está hospedado

O comando `-U postgres` define o nome do usuário que está fazendo o backup.

O comando `-d` especifica o nome do banco de dados que você deseja fazer o backup.

O comando `-W` solicita senha do usuário. Você pode conferir a senha no arquivo `credentials.py`, vai estar na chave `ENGIE_STAGING_DATABASE_URL`, entre as palavras postgres: e o @.

O comando `-Fc` define o formato do arquivo de backup. Neste caso, está definido como "Custom", que é um formato binário específico do PostgreSQL. Isso é útil para backups maiores, pois permite opções de compressão e restauração seletiva.

O comando `-f` especifica o nome do arquivo de saída para o backup. Neste caso, o arquivo de backup será chamado de "novo-dump.dump". Caso queira, você pode mudar para o nome que você deseja dar ao arquivo de backup.

```bash
pg_dump \
    -h engie-production.cnsey7np045b.sa-east-1.rds.amazonaws.com \
    -U postgres \
    -d engie-homolog \
    -W \
    -Fc \
    -f novo-dump.dump
```

Caso você queira remover algumas tabelas que são mais pesadas e gerar um banco de forma mais rápida, você pode fazer:

```bash
pg_dump  \
    -h engie-production.cnsey7np045b.sa-east-1.rds.amazonaws.com \
    -U postgres \
    -d engie-homolog \
    -W \
    -Fc \
    -f novo-dump.dump \
    --exclude-table-data=maps_historicalshapefile \
    --exclude-table-data=email_handler_historicalqueuedemail \
    --exclude-table-data=email_handler_queuedemail \
    --exclude-table-data=email_handler_historicalqueuedpush \
    --exclude-table-data=email_handler_queuedpush \
    --exclude-table-data=users_historicaluser \
    --exclude-table-data=users_historicalusernotification \
    --exclude-table-data=silk_sqlquery \
    --exclude-table-data=silk_response \
    --exclude-table-data=silk_request \
    --exclude-table-data=integrations_integrationrun \
    --exclude-table-data=templates_historicalexportrequest \
    --exclude-table-data=templates_exportrequest \
    --exclude-table-data=templates_actionlog \
    --exclude-table-data=templates_log \
    --exclude-table-data=templates_historicallog \
    --exclude-table-data=occurrence_records_historicaloccurrencerecord
```

Depois de gerar o novo banco de dados, é necessário apagar o banco local e carregar o `novo dump` de dentro do container do `postgres`:

```bash
psql -U postgres
    > DROP DATABASE "hidros-local";
    > CREATE DATABASE "hidros-local";
    > exit;

pg_restore -U postgres -d hidros-local novo-dump.dump
```

Fora do container, se precisar atualizar os pacotes ao trocar de `branch` (por exemplo indo para a env-homolog-engie) pode ser necessário rodar o comando:

```bash
docker compose exec app poetry
```

## Rodando comandos dentro do container

Talvez você precise rodar um comando dentro do container do app Django. Isso é possível rodando:

```bash
docker compose exec app poetry run <comando que você deseja rodar>
```

Um exemplo é o que fizemos para aplicar as migrações na seção anterior:

```bash
docker compose exec app poetry run ./manage.py migrate
```

## Debug dentro do container

Procure o ID do container `hidros-backend_app` utilizando o seguinte comando:

```bash
docker ps
```

E rode o seguinte comando para "linkar" a linha linha de comando com a saída do container:

```bash
docker attach <container_id>
```

Agora, por exemplo, se seu código chega em um breakpoint, você terá acesso ao shell rodando dentro do container para enviar comandos.

## Rodando os testes

Utilizamos o [pytest](https://docs.pytest.org/en/8.0.x/) em testes automatizados e você pode rodar um ou mais testes utilizando o seguinte comando:

```bash
docker compose exec app poetry run pytest <path>
```

Onde `<path>` é o caminho dos testes que você deseja rodar. Por exemplo, se você deseja rodas todos os testes do sistema, você pode mandar só um `.` (assumindo que você está na pasta do repositório). Você poderá também rodar os testes de um app específico, de um arquivo específico, de uma classe específica, etc.

**Dica:** Se os testes estão muitos verbosos e retornando muito texto, você pode cortar boa parte dessa verbosidade utilizando a flag `-c pytest-clean.ini`.

Exemplo:

```bash
docker compose exec app poetry run pytest -c pytest-clean.ini <path>
```

## Qualidade de código

Nós utilizamos algumas ferramentas de qualidade de código que podem ajudar no seu dia a dia já que o pipeline verifica e só aceita código que atende esses requisitos de qualidade.

Você pode encontrar mais informações sobre como utilizar essas ferramentas [aqui](https://doc.kartado.com.br/docs/praticas-de-qualidade-de-codigo).

Lembre-se que para rodar esses comandos dentro do container você precisará do comando completo mencionado acima em "Rodando comandos dentro do container".

Mas, em geral para rodar os comandos que formatam o código:

```bash
docker compose exec app poetry run black caminho-relativo-do-arquivo-que-precisa-formatar
```

```bash
docker compose exec app poetry run isort caminho-relativo-do-arquivo-que-precisa-formatar
```

```bash
docker compose exec app poetry run flake8 caminho-relativo-do-arquivo-que-precisa-formatar
```

Para saber o `caminho-relativo-do-arquivo-que-precisa-formatar` dentro do editor de texto que você utiliza (por exemplo VS Code), você clica com o botão direito do mouse em cima do arquivo desejado e vai aparecer `Copy Relative Path`.

## Análise de queries

Utilizamos uma ferramenta chamada [Silk](https://github.com/jazzband/django-silk) para analisar as queries e performance de chamadas ao banco de dados.

Você pode acessar as informações no endereço `localhost:8000/silk/` (considerando que o container esteja rodando).

OBS: O Silk não está disponível em ambientes publicados como staging.

<br><br>

# Como instalar

Para começar é necessário ter instalado os pacotes abaixo:

-   **Python(== 3.7.\*)**
-   **git**
-   **pip**
-   **virtualenv**

Se você ainda não tiver os pacotes listados acima, faça os passoa abaixo:

```shell
sudo apt-get update
```

Para instalar **git**:

```shell
sudo apt-get install git
```

Para instalar **pip** para Python 3:

```shell
sudo apt-get install python3-pip
```

Para instalar **virtualenv**:

```shell
pip3 install virtualenv
```

Após essas instalações, você poderá clonar o repositório:

```shell
git clone https://gitlab.com/Road-Labs/hidros-backend.git
cd hidros-backend
virtualenv -p /usr/bin/python3.6 venv
source venv/bin/activate
```

Agora, instale essas dependências:

```shell
sudo apt-get install libxmlsec1-dev pkg-config
sudo apt-get install postgis
```

Agora, use **pip** para instalar as bibliotecas usadas no desenvolvimento:

```shell
pip3 install -r requirements-dev.txt
```

Além disso, instale essas bibliotecas:

```shell
sudo add-apt-repository -y ppa:ubuntugis/ppa
sudo apt-get install postgresql postgresql-contrib gdal-bin python-gdal python3-gdal libgdal20
```

Agora é necessário alterar uma linha na configuração do Postgres. Primeiro, vá para `cd /etc/postgresql/` e use `ls` para encontrar a versão que você está usando. Depois disso, use:

```shell
sudo nano /etc/postgresql/{your-version}/main/pg_hba.conf
```

Encontre a seguinte linha:

```shell
local   all             postgres                                peer
```

E mude para:

```shell
local   all             postgres                                md5
```

Use `CTRL-O`, `Enter`, `CTRL-X` para sair.

Agora, vamos tentar executar o servidor:

```shell
git checkout dev

python ./manage.py makemigrations
```

Caso tenha algum problema com a senha:

```shell
sudo su postgres
psql
ALTER USER postgres with password 'postgres';
CREATE DATABASE "hidros-local";
```

Use `CTRL-D` para sair.

Reinicie o Postgres:

```shell
sudo service postgresql restart
```

Agora, tente executar o `makemigrations` novamente, se o erro persistir, altere o arquivo Postgres para `peer` novamente.

Após `makemigrations`, execute:

```shell
python ./manage.py migrate
```

Após o `migrate`, execute isto para preencher o banco de dados se você tiver o arquivo `dump`:

```shell
sudo su postgres
pg_restore -d hidros-local {your-file}.dump
```

Use `CTRL-D` para sair.

Reinicie o Postgres:

```shell
sudo service postgresql restart
```

Se você não possui o arquivo `dump`, use isto:

```shell
python ./manage.py loaddata fixtures/*.json
```

Para finalizar, basta executar o aplicativo e ele estará pronto para uso:

```shell
python ./manage.py runserver
```

# Ferramentas de desenvolvimento

## Postman

Para instalar **Postman**, use a [documentation](https://learning.getpostman.com/docs/).

> Postman é uma ferramenta que envia solicitações (requests) para uma API e mostra a resposta..

## Locust

Crie um ambiente virtual:

```shell
python3 -m venv venv_locust
source venv_locust/bin/activate
```

Instale as bibliotecas:

```shell
pip3 install -r locust/requirements.txt
```

Iniciar Locust

```shell
locust -f locust/wmdb.py
```

# Documenação

## Swagger

A documentação da API está disponível no Swagger. Uma ferramenta de código aberto para gerar automaticamente documentação de endpoints.

Você pode acessar este recurso executando o projeto e navegando até http://localhost:8000/docs/.

Lá você encontrará uma lista de endpoints e verbos HTTP. Mas como a maioria deles requer permissões, clique em “Login do Django” e insira suas credenciais. Caso contrário, terá avisos que certas visualizações não são compatíveis com a geração de esquema.

# Debugging

Nesta seção, são apresentadas algumas ferramentas de depuração que auxiliam na depuração.

## Pdb

Use a [documentation](https://docs.python.org/3/library/pdb.html):

> O módulo pdb define um depurador de código-fonte interativo para programas Python. Ele suporta a configuração de pontos de interrupção (condicionais) e etapas únicas no nível da linha de origem, inspeção de quadros de pilha, listagem de código-fonte e avaliação de código Python arbitrário no contexto de qualquer quadro de pilha. Ele também suporta depuração post-mortem e pode ser chamado sob controle do programa.

Para usar, adicione esta linha de código:

```python
import pdb; pdb.set_trace()
```

Onde você deseja criar um ponto de interrupção. Assim, ao executar o aplicativo, ao chegar ao ponto de interrupção, você pode usar o terminal para depurar. Os comandos mais comuns usados são: `s`(step), `n`(next), `c`(continue) e `q`(quit).

## Django Shell

Django Shell é o console interativo do Django. É como o prompt do Python, mas você também pode usar todos os módulos do Django.

Para usar, execute:

```shell
python ./manage.py shell
```

Agora, você pode criar e manipular objetos, verificar e filtrar conjuntos de consultas, testar funções, etc. Além disso, usando `helpers/testing/queries_helpers.py` você pode verificar o tempo e o número de consultas usadas no acesso ao seu banco de dados.

## Sentry

Sentry é um aplicativo de rastreamento de erros e pode ser muito útil para investigar bugs de teste e produção.

No site do Sentry, você encontrará este projeto com o nome `backend`.

Os ambientes relevantes (no topo da página) são:

-   `staging`: Problemas (issue) relacionados com [general staging instance](https://hidros.staging.roadlabs.com.br/)
-   `production`: Problemas (issue) relacionados com [general production instance](https://app.kartado.com.br/)
-   `staging-pre-shared`: Problemas (issue) relacionados com [pre production instance](https://pre.app.kartado.com.br/)
-   `production-engie`: Problemas (issue) relacionados com [Engie's production instance](https://engie.kartado.com.br/)
-   `staging-engie`: Problemas (issue) relacionados com [Engie's staging instance](https://pre.engie.kartado.com.br/)

Ao clicar em uma issue, você terá informações úteis para depuração (debugging), como rastreamento de pilha, informações do cliente, descrição do erro, cabeçalhos de solicitação e outras informações relevantes.

# Releases e changelog automaticos

Este repositorio usa Conventional Commits + release-please para gerar changelog e release de forma automatica.

## Formato de commit

Os commits devem seguir o padrao:

```text
tipo(escopo-opcional): descricao
```

Exemplos:

- `feat(api): adiciona endpoint de exportacao`
- `fix(auth): corrige renovacao de token`
- `chore(ci): atualiza cache do workflow`

Tipos aceitos: `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`, `test`.

## Como funciona no GitHub Actions

- O workflow `Commitlint` valida os commits dos PRs e bloqueia merge fora do padrao.
- O workflow `Release Please` roda em pushes para `main`.
- Quando houver commits relevantes desde a ultima versao, o release-please abre/atualiza automaticamente um PR de release.
- Ao mergear esse PR, ele cria a tag e a release no GitHub, alem de atualizar o `CHANGELOG.md`.

## Categorias tecnicas no changelog

Commits `chore` entram na secao **Tarefas tecnicas** do changelog/release notes, para dar visibilidade de melhorias internas (infra, CI, manutencao, etc.).
