from unittest.mock import MagicMock, patch

from apps.notifications.strategies.firebase import (
    FirebaseNotificationService,
    fix_base64_padding,
)


class TestFirebaseNotificationService:
    @patch("apps.notifications.strategies.firebase._get_access_token")
    @patch("tempfile.NamedTemporaryFile")
    @patch("base64.b64decode")
    def test_initialize(self, mock_b64decode, mock_tempfile, mock_get_access_token):
        # Definir o token fake esperado
        fake_firebase_token = "fake_token_123"

        # Simular a decodificação da credencial Base64
        mock_b64decode.return_value = b'{"type": "service_account"}'

        # Criar um mock para o arquivo temporário
        mock_temp_file = MagicMock()
        mock_tempfile.return_value.__enter__.return_value = mock_temp_file

        # Simular que o arquivo temporário possui um caminho
        mock_temp_file.name = "/tmp/fake_credentials.json"

        # Simular o retorno do Firebase Token
        mock_get_access_token.return_value = fake_firebase_token

        # Chamar o método que estamos testando
        token = FirebaseNotificationService.initialize("fake_base64_string")

        # Verificar se a decodificação foi chamada corretamente
        mock_b64decode.assert_called_once_with(fix_base64_padding("fake_base64_string"))

        # Verificar se o método _get_access_token foi chamado com o caminho correto do arquivo
        mock_get_access_token.assert_called_once()

        # Verificar se o token retornado é o esperado
        assert token == fake_firebase_token
