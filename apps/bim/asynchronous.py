import logging

import sentry_sdk
from zappa.asynchronous import task

from apps.bim.notifications import notify_bim_done, notify_bim_error

logger = logging.getLogger(__name__)


@task
def process_bim_upload(bim_model_uuid: str):
    """
    Processa upload de arquivo BIM de forma assíncrona.

    Esta task é disparada após o upload inicial do arquivo e:
    1. Atualiza o status para "processing"
    2. Valida o arquivo (o upload para S3 já foi feito pelo FileField)
    3. Atualiza o status para "done" ou "error"

    Args:
        bim_model_uuid: UUID do BIMModel a ser processado
    """
    from .models import BIMModel

    logger.info(f"[BIM_UPLOAD] Iniciando processamento do BIMModel: {bim_model_uuid}")

    try:
        bim_model = BIMModel.objects.get(uuid=bim_model_uuid)
    except BIMModel.DoesNotExist as e:
        logger.error(f"[BIM_UPLOAD] BIMModel não encontrado: {bim_model_uuid}")
        sentry_sdk.capture_exception(e)
        return

    try:
        # Atualiza status para processing
        bim_model.status = BIMModel.STATUS_PROCESSING
        bim_model.save(update_fields=["status", "updated_at"])
        logger.info(f"[BIM_UPLOAD] Status atualizado para processing: {bim_model_uuid}")

        # O arquivo já foi salvo no S3 pelo FileField durante o upload
        # Aqui podemos fazer validações adicionais ou processamento futuro

        # Verificar se o arquivo existe
        if not bim_model.file:
            raise ValueError("Arquivo não foi salvo corretamente")

        # Futuro: Processamento IFC → Fragments pode ser adicionado aqui
        # from apps.bim.processing import convert_ifc_to_fragments
        # convert_ifc_to_fragments(bim_model)

        # Atualiza status para done
        bim_model.status = BIMModel.STATUS_DONE
        bim_model.save(update_fields=["status", "updated_at"])
        logger.info(
            f"[BIM_UPLOAD] Processamento concluído com sucesso: {bim_model_uuid}"
        )

        # Notifica o usuário sobre o sucesso
        notify_bim_done(bim_model)

    except Exception as e:
        logger.error(
            f"[BIM_UPLOAD] Erro ao processar BIMModel {bim_model_uuid}: {str(e)}",
            exc_info=True,
        )
        sentry_sdk.capture_exception(e)

        # Atualiza status para error
        bim_model.status = BIMModel.STATUS_ERROR
        bim_model.error_message = str(e)
        bim_model.save(update_fields=["status", "error_message", "updated_at"])

        # Notifica o usuário sobre o erro
        notify_bim_error(bim_model)
