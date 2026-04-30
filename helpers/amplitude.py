"""
Amplitude analytics helper.

Provides a lightweight wrapper around the Amplitude Python SDK
for server-side event tracking.
"""

import logging

from RoadLabsAPI.settings import credentials

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Retorna instância singleton do client Amplitude. None se API key não configurada."""
    from amplitude import Amplitude

    global _client
    if _client is None:
        api_key = credentials.AMPLITUDE_API_KEY
        if not api_key:
            return None
        _client = Amplitude(api_key)
    return _client


def track_event(user_id, event_type, event_properties=None, user_properties=None):
    """
    Envia evento para o Amplitude.

    Silencioso em caso de falha — nunca propaga exceções.
    Chama flush() após track para garantir envio em ambientes Lambda.

    Args:
        user_id: Identificador do usuário (UUID ou string).
        event_type: Nome do evento (ex: "programação automática").
        event_properties: Dicionário com propriedades do evento.
        user_properties: Dicionário com propriedades do usuário.
    """
    from amplitude import BaseEvent

    client = _get_client()
    if client is None:
        logger.debug("Amplitude não configurado (API key vazia), evento ignorado")
        return

    try:
        event = BaseEvent(
            event_type=event_type,
            user_id=str(user_id),
            event_properties=event_properties or {},
            user_properties=user_properties or {},
            platform="Web",
            os_name="Server",
            device_id="kartado-backend",
        )
        client.track(event)
        client.flush()
    except Exception:
        logger.exception(f"Erro ao enviar evento Amplitude: {event_type}")
