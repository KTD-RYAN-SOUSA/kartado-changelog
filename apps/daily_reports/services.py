import json

import requests
import sentry_sdk

from helpers.strings import get_obj_from_path


def _get_webhook_url(company_metadata, path_key: str):
    """
    Busca a URL do webhook no metadata da company.
    """
    return get_obj_from_path(company_metadata, path_key)


def send_daily_report_to_n8n(raw_body: bytes, legacy_number: str, company):
    webhook_url = _get_webhook_url(
        getattr(company, "metadata", {}), "n8n_daily_report_webhook_url"
    )
    if not webhook_url:
        sentry_sdk.capture_message("N8N_DAILY_REPORT_WEBHOOK_URL not setup", "Warning")
        return

    headers = {"Content-Type": "application/json"}

    try:
        payload_dict = json.loads(raw_body)
        payload_dict["data"]["attributes"]["legacyNumber"] = legacy_number

        response = requests.post(
            webhook_url, json=payload_dict, headers=headers, timeout=30
        )
        response.raise_for_status()
    except (requests.RequestException, json.JSONDecodeError) as e:
        sentry_sdk.capture_exception(e)


def send_edited_daily_report_to_n8n(raw_body: bytes, daily_report_uuid: str, company):
    """
    Envia os dados de uma requisição de edição de RDO para um webhook do n8n.
    """
    webhook_url = _get_webhook_url(
        getattr(company, "metadata", {}), "n8n_edited_daily_report_webhook_url"
    )
    if not webhook_url:
        sentry_sdk.capture_message(
            "N8N_EDITED_DAILY_REPORT_WEBHOOK_URL not setup",
            "warning",
        )
        return

    headers = {"Content-Type": "application/json"}

    try:
        payload_dict = json.loads(raw_body)

        response = requests.post(
            webhook_url, json=payload_dict, headers=headers, timeout=30
        )
        response.raise_for_status()
    except (requests.RequestException, json.JSONDecodeError) as e:
        sentry_sdk.capture_exception(e)


def send_daily_report_file_to_webhook(instance, raw_body: bytes, company):
    from apps.daily_reports.serializers import MultipleDailyReportFileSerializer

    webhook_url = _get_webhook_url(
        getattr(company, "metadata", {}), "n8n_daily_report_file_webhook_url"
    )
    if not webhook_url:
        sentry_sdk.capture_message(
            "N8N_DAILY_REPORT_FILE_WEBHOOK_URL não configurada",
            "warning",
        )
        return

    headers = {"Content-Type": "application/json"}

    try:
        raw_body_dict = json.loads(raw_body)
        serializer = MultipleDailyReportFileSerializer(instance)

        raw_body_dict["data"]["attributes"]["uploadGetUrl"] = serializer.data["upload"]
        raw_body_dict["data"]["attributes"]["companyId"] = str(
            instance.multiple_daily_report.company.uuid
        )
        raw_body_dict["data"]["attributes"]["uuid"] = str(instance.uuid)

        response = requests.post(
            webhook_url, json=raw_body_dict, headers=headers, timeout=30
        )
        response.raise_for_status()
    except (requests.RequestException, Exception) as e:
        sentry_sdk.capture_exception(e)


def send_daily_report_same_db_to_n8n(
    raw_body: bytes,
    legacy_number: str,
    company,
    source_uuid: str = None,
    source_firm=None,
):
    """
    Envia RDO para webhook N8N same-database.
    Operação dentro do mesmo banco de dados.

    Pré-condições (validadas aqui no backend):
    - n8n_target_company_id: UUID da company destino que receberá os dados.
      Também valida se a company destino existe no banco.
    - n8n_same_db_source_firm_uuids: (opcional) lista de UUIDs de firms de origem
      autorizadas. Se vazio, todas as firms da company são elegíveis.

    Resolução de Firm/SubCompany é responsabilidade do N8N.
    """
    from apps.companies.models import Company

    metadata = getattr(company, "metadata", {})

    # Verificar n8n_target_company_id (chave de ativação same-db)
    target_company_id = get_obj_from_path(metadata, "n8n_target_company_id")
    if not target_company_id:
        return

    # Validar se a company destino existe
    if not Company.objects.filter(uuid=target_company_id).exists():
        sentry_sdk.capture_message(
            f"Same-DB: company destino {target_company_id} não encontrada",
            "warning",
        )
        return

    # Filtrar por firms de origem autorizadas
    source_firm_uuids = (
        get_obj_from_path(metadata, "n8n_same_db_source_firm_uuids") or []
    )
    if source_firm_uuids and source_firm:
        if str(source_firm.uuid) not in source_firm_uuids:
            return

    webhook_url = _get_webhook_url(
        metadata, "n8n_same_db_daily_report_create_webhook_url"
    )
    if not webhook_url:
        sentry_sdk.capture_message(
            "N8N_SAME_DB_DAILY_REPORT_CREATE_WEBHOOK_URL not setup",
            "warning",
        )
        return

    headers = {"Content-Type": "application/json"}

    try:
        payload_dict = json.loads(raw_body)
        payload_dict["data"]["attributes"]["legacyNumber"] = legacy_number
        payload_dict["data"]["attributes"]["targetCompanyId"] = target_company_id
        if source_uuid:
            payload_dict["data"]["attributes"]["sourceUuid"] = source_uuid

        response = requests.post(
            webhook_url, json=payload_dict, headers=headers, timeout=30
        )
        response.raise_for_status()
    except (requests.RequestException, json.JSONDecodeError) as e:
        sentry_sdk.capture_exception(e)


def send_daily_report_same_db_edit_to_n8n(instance):
    """
    Envia edição de RDO para webhook N8N same-database.
    Operação PATCH para sincronizar mudanças no mesmo banco de dados.

    Fluxo:
    - RDO Original (sem legacy_number) é editado
    - Backend dispara webhook com número do RDO original
    - N8N encontra a cópia pela legacyNumber = number do original
    - N8N aplica 4 regras de sincronização

    Pré-condições (validadas aqui no backend):
    - n8n_same_db_daily_report_edit_webhook_url deve estar configurada na company
    - RDO deve ser ORIGINAL (sem legacy_number)
    - Company deve ter integração same-db ativa (target_company_id)

    Args:
        instance: MultipleDailyReport instance sendo editado
    """
    import logging

    from helpers.serializers import get_obj_serialized

    logger = logging.getLogger(__name__)

    logger.info(
        f"[EDIT_WEBHOOK] ▶ send_daily_report_same_db_edit_to_n8n() chamado para RDO {instance.uuid}"
    )

    company = instance.company
    metadata = getattr(company, "metadata", {})

    # Obter webhook URL
    webhook_url = _get_webhook_url(
        metadata, "n8n_same_db_daily_report_edit_webhook_url"
    )
    target_company_id = get_obj_from_path(metadata, "n8n_target_company_id")

    if not webhook_url:
        logger.debug(
            f"[EDIT_WEBHOOK] Webhook não configurada para company {company.uuid}. "
            f"Chave: n8n_same_db_daily_report_edit_webhook_url (ignorando)"
        )
        return

    logger.info(f"[EDIT_WEBHOOK] ✓ Webhook URL encontrada: {webhook_url[:50]}...")

    # Validar se RDO é original (não é cópia)
    # RDOs cópias têm legacy_number, originais não têm
    if instance.legacy_number:
        logger.debug(
            f"[EDIT_WEBHOOK] RDO {instance.uuid} é cópia (legacy_number={instance.legacy_number}), ignorando"
        )
        return

    logger.info(f"[EDIT_WEBHOOK] ✓ RDO {instance.uuid} é ORIGINAL (sem legacy_number)")

    # Serializar dados
    try:
        serialized_data = get_obj_serialized(
            instance,
            exclude_fields=[
                "uuid",
                "id",
                "number",
                "createdBy",
                "createdAt",
                "updatedBy",
                "updatedAt",
            ],
        )
    except Exception as e:
        logger.error(f"[EDIT_WEBHOOK] Erro ao serializar RDO {instance.uuid}: {e}")
        serialized_data = {}

    # Construir payload
    # legacyNumber = number do RDO original (será usado para encontrar cópia)
    payload = {
        "data": {
            "id": str(instance.uuid),
            "attributes": {
                "uuid": str(instance.uuid),
                "legacyNumber": instance.number,  # ← Número do original
                "target_company_id": target_company_id,
                **serialized_data,
            },
            "relationships": {
                "company": {"data": {"type": "Company", "id": str(company.uuid)}}
            },
        }
    }

    logger.info(
        f"[EDIT_WEBHOOK] Payload: legacyNumber={instance.number}, uuid={instance.uuid}"
    )

    headers = {"Content-Type": "application/json"}

    # Aguardar para garantir que workers, equipments e vehicles
    # já foram commitados no banco antes do n8n consultar a API
    import time

    time.sleep(10)

    logger.info(f"[EDIT_WEBHOOK] Disparando PATCH para {webhook_url}")

    try:
        response = requests.patch(
            webhook_url, json=payload, headers=headers, timeout=60
        )
        response.raise_for_status()
        logger.info(
            f"[EDIT_WEBHOOK] ✓ Webhook PATCH disparado com sucesso! "
            f"RDO={instance.uuid}, Status={response.status_code}"
        )
    except (requests.RequestException, Exception) as e:
        logger.error(
            f"[EDIT_WEBHOOK] ✗ Falha ao disparar webhook PATCH para RDO {instance.uuid}: {e}"
        )
        sentry_sdk.capture_exception(e)
