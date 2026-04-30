import logging
import os
import threading
import time
from typing import Callable, Optional

import boto3
from botocore.exceptions import ClientError
from django.conf import settings


def publish_fargate_metrics(
    metric_name: str,
    duration_seconds: float,
    success: bool,
    item_count: Optional[int] = None,
    image_count: Optional[int] = None,
) -> None:
    """
    Publica métricas customizadas no CloudWatch no namespace "Kartado/Fargate".

    Métricas publicadas:
        - Duration        (Seconds) — tempo total de processamento
        - Success         (Count)   — 1 quando concluído sem erro
        - Errors          (Count)   — 1 quando concluído com erro
        - ItemsProcessed  (Count)   — opcional
        - ImagesProcessed (Count)   — opcional
    """
    try:
        region = getattr(settings, "AWS_DEFAULT_REGION_ECS", "")
        cloudwatch = boto3.client("cloudwatch", region_name=region)
        dimensions = [{"Name": "ProcessType", "Value": metric_name}]
        metric_data = [
            {
                "MetricName": "Duration",
                "Dimensions": dimensions,
                "Value": duration_seconds,
                "Unit": "Seconds",
            },
            {
                "MetricName": "Success" if success else "Errors",
                "Dimensions": dimensions,
                "Value": 1,
                "Unit": "Count",
            },
        ]
        if item_count is not None:
            metric_data.append(
                {
                    "MetricName": "ItemsProcessed",
                    "Dimensions": dimensions,
                    "Value": item_count,
                    "Unit": "Count",
                }
            )
        if image_count is not None:
            metric_data.append(
                {
                    "MetricName": "ImagesProcessed",
                    "Dimensions": dimensions,
                    "Value": image_count,
                    "Unit": "Count",
                }
            )
        cloudwatch.put_metric_data(Namespace="Kartado/Fargate", MetricData=metric_data)
    except Exception as e:
        from sentry_sdk import capture_exception

        logging.error(f"Error in put metric: {e}")
        capture_exception(e)


def stop_current_fargate_task(reason: str = "Task concluída") -> None:
    """
    Encerra a task ECS Fargate atual via API, obtendo o ARN e cluster
    a partir do endpoint de metadados injetado pelo ECS (ECS_CONTAINER_METADATA_URI_V4).

    Deve ser chamada apenas dentro de um container ECS Fargate.
    """

    import requests

    metadata_uri = os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
    if not metadata_uri:
        logging.error(
            "[ECSTaskService] ECS_CONTAINER_METADATA_URI_V4 não está definida"
        )
        return

    try:
        metadata = requests.get(f"{metadata_uri}/task", timeout=5).json()
        task_arn = metadata["TaskARN"]
        cluster = metadata["Cluster"]
    except Exception as e:
        from sentry_sdk import capture_exception

        logging.error(f"[ECSTaskService] Erro ao obter metadados da task: {e}")
        capture_exception(e)
        return

    try:
        region = getattr(settings, "AWS_DEFAULT_REGION_ECS", "us-east-1")
        ecs = boto3.client("ecs", region_name=region)
        ecs.stop_task(cluster=cluster, task=task_arn, reason=reason)
        logging.info(
            f"[ECSTaskService] StopTask enviado para {task_arn} — motivo: {reason}"
        )
    except Exception as e:
        from sentry_sdk import capture_exception

        logging.error(f"[ECSTaskService] Erro ao chamar StopTask: {e}")
        capture_exception(e)


def run_in_fargate(
    instance,
    process_fn: Callable[[], None],
    metric_name: str = "FargateProcessing",
    get_item_count: Optional[Callable[[], Optional[int]]] = None,
    get_image_count: Optional[Callable[[], Optional[int]]] = None,
) -> None:
    """
    Executa process_fn em uma thread daemon, publica métricas e encerra o container ao concluir.
    """

    def run():
        start_time = time.time()
        try:
            process_fn()
        finally:
            duration = time.time() - start_time
            try:
                instance.refresh_from_db()
                success = not instance.error
                item_count = get_item_count() if get_item_count else None
                image_count = get_image_count() if get_image_count else None
                publish_fargate_metrics(
                    metric_name, duration, success, item_count, image_count
                )
            except Exception as e:
                from sentry_sdk import capture_exception

                capture_exception(e)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()


class ECSTaskService:
    """Serviço para gerenciar tasks ECS Fargate sob demanda."""

    def __init__(self):
        self.cluster = getattr(settings, "ECS_CLUSTER_NAME", "")
        self.task_family = getattr(settings, "ECS_TASK_FAMILY", "kartado-backend")
        self.subnets = getattr(settings, "ECS_SUBNETS", [])
        self.security_groups = getattr(settings, "ECS_SECURITY_GROUPS", [])
        self.region = getattr(settings, "AWS_DEFAULT_REGION_ECS", "")
        # Usa o IAM role do ambiente automaticamente via credential chain do boto3:
        # - Lambda: usa as env vars injetadas pela AWS (execution role)
        # - Fargate: usa o ECS metadata endpoint (task role)
        self.ecs_client = boto3.client("ecs", region_name=self.region)
        self.ec2_client = boto3.client("ec2", region_name=self.region)

    def start_task(self) -> str:
        """Inicia uma nova task ECS Fargate e retorna o task ARN."""
        response = self.ecs_client.run_task(
            cluster=self.cluster,
            taskDefinition=self.task_family,
            launchType="FARGATE",
            platformVersion="LATEST",
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": self.subnets,
                    "securityGroups": self.security_groups,
                    "assignPublicIp": "ENABLED",
                }
            },
            enableExecuteCommand=True,
        )

        if not response.get("tasks"):
            raise RuntimeError("Nenhuma task ECS foi iniciada")

        return response["tasks"][0]["taskArn"]

    def wait_for_running(self, task_arn: str, timeout: int = 300) -> bool:
        """Aguarda a task estar no estado RUNNING. Retorna True se RUNNING, False caso contrário."""
        start_time = time.time()
        interval = 5

        while time.time() - start_time < timeout:
            try:
                response = self.ecs_client.describe_tasks(
                    cluster=self.cluster, tasks=[task_arn]
                )

                if not response.get("tasks"):
                    return False

                status = response["tasks"][0]["lastStatus"]

                if status == "RUNNING":
                    return True

                if status == "STOPPED":
                    return False

                time.sleep(interval)

            except ClientError:
                return False

        return False

    def get_task_ip(self, task_arn: str) -> Optional[str]:
        """Obtém o IP público da task via ENI."""
        try:
            response = self.ecs_client.describe_tasks(
                cluster=self.cluster, tasks=[task_arn]
            )

            if not response.get("tasks"):
                return None

            task = response["tasks"][0]
            attachments = task.get("attachments", [])

            eni_id = None
            for attachment in attachments:
                if attachment["type"] == "ElasticNetworkInterface":
                    for detail in attachment["details"]:
                        if detail["name"] == "networkInterfaceId":
                            eni_id = detail["value"]
                            break
                    break

            if not eni_id:
                return None

            eni_response = self.ec2_client.describe_network_interfaces(
                NetworkInterfaceIds=[eni_id]
            )

            if not eni_response.get("NetworkInterfaces"):
                return None

            return (
                eni_response["NetworkInterfaces"][0]
                .get("Association", {})
                .get("PublicIp")
            )

        except ClientError:
            return None
