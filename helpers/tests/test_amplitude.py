"""
Tests for helpers/amplitude.py
"""

import sys
from unittest.mock import MagicMock, patch


class _FakeBaseEvent:
    """Fake BaseEvent para testes - armazena kwargs como atributos."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# Mock do módulo amplitude (pode não estar instalado no ambiente de teste)
_mock_amplitude_module = MagicMock()
_mock_amplitude_module.BaseEvent = _FakeBaseEvent
sys.modules.setdefault("amplitude", _mock_amplitude_module)


class TestTrackEvent:
    """Testes para a função track_event do helper Amplitude."""

    def setup_method(self):
        """Reset singleton e mocks antes de cada teste."""
        import helpers.amplitude as amp_module

        amp_module._client = None
        _mock_amplitude_module.Amplitude.reset_mock()

    @patch("helpers.amplitude.credentials")
    def test_track_event_success(self, mock_credentials):
        """Verifica que track() e flush() são chamados corretamente."""
        mock_credentials.AMPLITUDE_API_KEY = "fake-api-key"
        mock_client = MagicMock()
        _mock_amplitude_module.Amplitude.return_value = mock_client

        from helpers.amplitude import track_event

        track_event(
            user_id="user-123",
            event_type="programação automática",
            event_properties={"unidade": "Company A"},
        )

        _mock_amplitude_module.Amplitude.assert_called_once_with("fake-api-key")
        mock_client.track.assert_called_once()
        mock_client.flush.assert_called_once()

        event = mock_client.track.call_args[0][0]
        assert event.event_type == "programação automática"
        assert event.user_id == "user-123"
        assert event.event_properties == {"unidade": "Company A"}

    @patch("helpers.amplitude.credentials")
    def test_track_event_no_api_key(self, mock_credentials):
        """Verifica que retorna silenciosamente quando API key está vazia."""
        mock_credentials.AMPLITUDE_API_KEY = ""

        from helpers.amplitude import track_event

        # Não deve levantar exceção
        track_event(
            user_id="user-123",
            event_type="test event",
        )

    @patch("helpers.amplitude.credentials")
    def test_track_event_exception_is_caught(self, mock_credentials):
        """Verifica que exceções são capturadas sem propagar."""
        mock_credentials.AMPLITUDE_API_KEY = "fake-api-key"
        mock_client = MagicMock()
        mock_client.track.side_effect = Exception("Connection error")
        _mock_amplitude_module.Amplitude.return_value = mock_client

        from helpers.amplitude import track_event

        # Não deve levantar exceção
        track_event(
            user_id="user-123",
            event_type="test event",
        )

    @patch("helpers.amplitude.credentials")
    def test_track_event_default_properties(self, mock_credentials):
        """Verifica que propriedades padrão são dict vazio quando não fornecidas."""
        mock_credentials.AMPLITUDE_API_KEY = "fake-api-key"
        mock_client = MagicMock()
        _mock_amplitude_module.Amplitude.return_value = mock_client

        from helpers.amplitude import track_event

        track_event(user_id="user-123", event_type="test event")

        event = mock_client.track.call_args[0][0]
        assert event.event_properties == {}
        assert event.user_properties == {}

    @patch("helpers.amplitude.credentials")
    def test_client_singleton(self, mock_credentials):
        """Verifica que o client é reutilizado (singleton)."""
        mock_credentials.AMPLITUDE_API_KEY = "fake-api-key"
        mock_client = MagicMock()
        _mock_amplitude_module.Amplitude.return_value = mock_client

        from helpers.amplitude import track_event

        track_event(user_id="user-1", event_type="event 1")
        track_event(user_id="user-2", event_type="event 2")

        # Amplitude() deve ser chamado apenas uma vez (singleton)
        _mock_amplitude_module.Amplitude.assert_called_once()
        # Mas track deve ser chamado duas vezes
        assert mock_client.track.call_count == 2
