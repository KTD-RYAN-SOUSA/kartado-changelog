"""
Notificações para processamento de modelos BIM.

Este módulo cria PushNotifications para informar o usuário
sobre o status do processamento de modelos BIM.
"""

import logging

from django.conf import settings

from helpers.notifications import create_push_notifications

logger = logging.getLogger(__name__)


def notify_bim_done(bim_model):
    """
    Cria notificação no sino quando modelo BIM está pronto.

    Args:
        bim_model: Instância de BIMModel com status='done'
    """
    user = bim_model.created_by
    company = bim_model.company
    inventory = bim_model.inventory

    if not user:
        logger.warning(
            f"[BIM_NOTIFICATION] BIMModel {bim_model.uuid} sem usuário para notificar"
        )
        return

    if not inventory:
        logger.warning(
            f"[BIM_NOTIFICATION] BIMModel {bim_model.uuid} sem inventário associado"
        )
        return

    inventory_serial = inventory.number or str(inventory.uuid)[:8]

    url = "{}/#/Inventory/{}/show/bim".format(
        settings.FRONTEND_URL, str(inventory.uuid)
    )

    message = (
        f"O carregamento do modelo 3D do inventário {inventory_serial} foi processado"
    )

    create_push_notifications(
        users=[user],
        message=message,
        company=company,
        instance=bim_model,
        url=url,
    )

    logger.info(
        f"[BIM_NOTIFICATION] Notificação de sucesso criada para {user.email}: {bim_model.uuid}"
    )


def notify_bim_error(bim_model):
    """
    Cria notificação no sino quando há erro no processamento.

    Args:
        bim_model: Instância de BIMModel com status='error'
    """
    user = bim_model.created_by
    company = bim_model.company
    inventory = bim_model.inventory

    if not user:
        logger.warning(
            f"[BIM_NOTIFICATION] BIMModel {bim_model.uuid} sem usuário para notificar"
        )
        return

    if not inventory:
        logger.warning(
            f"[BIM_NOTIFICATION] BIMModel {bim_model.uuid} sem inventário associado"
        )
        return

    inventory_serial = inventory.number or str(inventory.uuid)[:8]

    url = "{}/#/Inventory/{}/show/bim".format(
        settings.FRONTEND_URL, str(inventory.uuid)
    )

    message = (
        f"Ocorreu um erro ao processar o modelo 3D do inventário {inventory_serial}"
    )

    create_push_notifications(
        users=[user],
        message=message,
        company=company,
        instance=bim_model,
        url=url,
    )

    logger.info(
        f"[BIM_NOTIFICATION] Notificação de erro criada para {user.email}: {bim_model.uuid}"
    )
