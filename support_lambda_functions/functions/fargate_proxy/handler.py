"""
Fargate Proxy Lambda
--------------------
Recebe um request HTTP, dispara a si mesma de forma assíncrona (InvocationType='Event')
e retorna 200 imediatamente ao chamador.

A invocação assíncrona executa o fluxo completo sem estar sujeita ao timeout de 30s
do API Gateway: inicia a task ECS Fargate, aguarda RUNNING, repassa o request e
retorna a resposta.

Variáveis de ambiente necessárias:
    ECS_CLUSTER_NAME       — nome do cluster ECS
    ECS_TASK_FAMILY        — família da task definition (ex: kartado-backend)
    ECS_SUBNETS            — subnets separadas por vírgula
    ECS_SECURITY_GROUPS    — security groups separados por vírgula
    AWS_DEFAULT_REGION_ECS — região AWS do ECS
    FARGATE_TASK_PORT      — porta do container (default: 8000)
    FARGATE_WAIT_TIMEOUT   — segundos para aguardar RUNNING (default: 60)
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request

import boto3

ECS_CLUSTER = os.environ.get("ECS_CLUSTER_NAME", "")
ECS_TASK_FAMILY = os.environ.get("ECS_TASK_FAMILY", "")
ECS_SUBNETS = [
    s.strip() for s in os.environ.get("ECS_SUBNETS", "").split(",") if s.strip()
]
ECS_SECURITY_GROUPS = [
    s.strip() for s in os.environ.get("ECS_SECURITY_GROUPS", "").split(",") if s.strip()
]
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION_ECS", "us-east-1")
TASK_PORT = int(os.environ.get("FARGATE_TASK_PORT", "8000"))
WAIT_TIMEOUT = int(os.environ.get("FARGATE_WAIT_TIMEOUT", "240"))


def _start_task():
    ecs = boto3.client("ecs", region_name=AWS_REGION)
    response = ecs.run_task(
        cluster=ECS_CLUSTER,
        taskDefinition=ECS_TASK_FAMILY,
        launchType="FARGATE",
        platformVersion="LATEST",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": ECS_SUBNETS,
                "securityGroups": ECS_SECURITY_GROUPS,
                "assignPublicIp": "ENABLED",
            }
        },
        enableExecuteCommand=True,
    )
    failures = response.get("failures", [])
    tasks = response.get("tasks", [])
    if not tasks:
        raise RuntimeError(f"Falha ao iniciar task ECS: {failures}")
    task_arn = tasks[0]["taskArn"]
    print(f"[FargateProxy] Task iniciada: {task_arn}")
    return task_arn


def _wait_for_running(task_arn):
    ecs = boto3.client("ecs", region_name=AWS_REGION)
    deadline = time.time() + WAIT_TIMEOUT
    while time.time() < deadline:
        resp = ecs.describe_tasks(cluster=ECS_CLUSTER, tasks=[task_arn])
        tasks = resp.get("tasks", [])
        if not tasks:
            raise RuntimeError("Task não encontrada ao aguardar RUNNING")
        task = tasks[0]
        status = task["lastStatus"]
        if status == "RUNNING":
            print(f"[FargateProxy] Task RUNNING: {task_arn}")
            return task
        if status == "STOPPED":
            raise RuntimeError(
                f"Task parou antes de iniciar: {task.get('stoppedReason', 'motivo desconhecido')}"
            )
        time.sleep(3)
    raise TimeoutError(f"Task não entrou em RUNNING dentro de {WAIT_TIMEOUT}s")


def _get_task_ip(task):
    ec2 = boto3.client("ec2", region_name=AWS_REGION)
    for attachment in task.get("attachments", []):
        if attachment["type"] == "ElasticNetworkInterface":
            for detail in attachment["details"]:
                if detail["name"] == "networkInterfaceId":
                    eni_id = detail["value"]
                    resp = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
                    interfaces = resp.get("NetworkInterfaces", [])
                    if interfaces:
                        return interfaces[0].get("Association", {}).get("PublicIp")
    return None


def _process(event):
    task_arn = _start_task()
    task = _wait_for_running(task_arn)
    ip = _get_task_ip(task)
    if not ip:
        raise RuntimeError("Não foi possível obter o IP público da task ECS")
    print("[FargateProxy] Aguardando 60s para inicialização do servidor...")
    time.sleep(120)
    return _forward_request(ip, event)


def _forward_request(ip, event):
    path = event.get("path", "/")
    method = event.get("httpMethod", "POST").upper()
    headers = event.get("headers") or {}
    body = event.get("body") or ""

    if isinstance(body, str):
        body = body.encode("utf-8")

    url = f"http://{ip}:{TASK_PORT}{path}"

    forward_headers = {
        k: v
        for k, v in headers.items()
        if k.lower() not in ("host", "content-length", "transfer-encoding")
    }
    forward_headers["X-Forwarded-From"] = "fargate-proxy"

    req = urllib.request.Request(
        url, data=body or None, headers=forward_headers, method=method
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            resp_body = response.read().decode("utf-8")
            return {
                "statusCode": response.status,
                "headers": dict(response.headers),
                "body": resp_body,
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        logging.error(
            f"[FargateProxy] HTTPError: status={e.code} body={err_body[:500]}"
        )
        return {
            "statusCode": e.code,
            "headers": dict(e.headers),
            "body": err_body,
        }
    except OSError:
        # Timeout ou outro erro — o request foi enviado e o export está sendo processado.
        print(
            "[FargateProxy] Sem resposta em 60s — export em processamento, encerrando Lambda"
        )
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"status": "processing"}),
        }


ALLOWED_ORIGINS = {
    "https://app.kartado.com.br",
    "https://engie.kartado.com.br",
    "https://ccr.kartado.com.br",
    "https://app.staging.kartado.com.br",
    "https://homolog-ccr.kartado.com.br",
    "https://pre.engie.kartado.com.br",
    "https://homolog.kartado.com.br",
    "http://localhost:3000",  # desenvolvimento local
}


def _cors_headers(event):
    origin = (event.get("headers") or {}).get("Origin") or (
        event.get("headers") or {}
    ).get("origin", "")
    allowed_origin = (
        origin if origin in ALLOWED_ORIGINS else next(iter(ALLOWED_ORIGINS))
    )
    return {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Headers": "Content-Type,Authorization,Accept",
        "Access-Control-Allow-Methods": "POST,OPTIONS",
        "Content-Type": "application/json",
    }


def lambda_handler(event, context):
    """
    Entry point da Lambda.

    - Invocação direta (API Gateway): invoca a si mesma async via header X-Fargate-Async
      e retorna 200 imediatamente.
    - Invocação assíncrona (header X-Fargate-Async: 1): tratada pelo wsgi.py que chama
      _process() diretamente, sem passar por lambda_handler.
    """
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": _cors_headers(event),
            "body": "",
        }

    try:
        lambda_client = boto3.client("lambda", region_name=AWS_REGION)
        async_event = {
            **event,
            "headers": {**(event.get("headers") or {}), "X-Fargate-Async": "1"},
        }
        response = lambda_client.invoke(
            FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"],
            InvocationType="Event",
            Payload=json.dumps(async_event),
        )
        print(
            f"[FargateProxy] Invocação async status: {response.get('StatusCode')} | RequestId: {response.get('ResponseMetadata', {}).get('RequestId')}"
        )
    except Exception as e:
        logging.error(f"[FargateProxy] Erro ao invocar async: {e}")
        return {
            "statusCode": 500,
            "headers": _cors_headers(event),
            "body": json.dumps({"error": str(e)}),
        }

    return {
        "statusCode": 200,
        "headers": _cors_headers(event),
        "body": json.dumps({"status": "processing"}),
    }
