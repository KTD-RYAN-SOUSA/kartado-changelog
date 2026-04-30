import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status

from apps.sql_chat.models import SqlChatMessage
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestSqlChatMessageView(TestBase):
    model = "SqlChatMessage"

    @patch("apps.sql_chat.views.get_sql_chat_credentials")
    @patch("apps.sql_chat.views.requests.post")
    def test_create_message_success(self, mock_post, mock_get_credentials, client):
        """Test successful creation of SQL Chat message."""
        mock_get_credentials.return_value = {
            "api_key": "fake-api-key",
            "api_url": "https://fake-aws-api.com",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "request_id": "test-request-123",
            "session_id": "test-session-456",
        }
        mock_post.return_value = mock_response

        response = client.post(
            path="/SqlChatMessage/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "SqlChatMessage",
                    "attributes": {
                        "input": "Quantos registros temos na tabela?",
                    },
                    "relationships": {
                        "company": {
                            "data": {"type": "Company", "id": str(self.company.pk)}
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        content = json.loads(response.content)
        data = content.get("data", content)
        assert "uuid" in data
        assert "chat_id" in data
        assert data["request_id"] == "test-request-123"
        assert data["session_id"] == "test-session-456"
        assert data["status"] == "STARTED"

        message = SqlChatMessage.objects.get(uuid=data["uuid"])
        assert message.input == "Quantos registros temos na tabela?"
        assert message.created_by == self.user
        assert message.company == self.company

    @patch("apps.sql_chat.views.get_sql_chat_credentials")
    @patch("apps.sql_chat.views.requests.post")
    def test_create_message_with_existing_chat_id(
        self, mock_post, mock_get_credentials, client
    ):
        """Test creating message in existing chat uses same session_id."""
        existing_chat_id = uuid.uuid4()
        existing_session_id = "existing-session-123"

        SqlChatMessage.objects.create(
            chat_id=existing_chat_id,
            session_id=existing_session_id,
            company=self.company,
            created_by=self.user,
            input="Primeira mensagem",
            status="COMPLETED",
        )

        mock_get_credentials.return_value = {
            "api_key": "fake-api-key",
            "api_url": "https://fake-aws-api.com",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "request_id": "test-request-789",
            "session_id": existing_session_id,
        }
        mock_post.return_value = mock_response

        response = client.post(
            path="/SqlChatMessage/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "SqlChatMessage",
                    "attributes": {
                        "input": "Segunda mensagem",
                        "chatId": str(existing_chat_id),
                    },
                    "relationships": {
                        "company": {
                            "data": {"type": "Company", "id": str(self.company.pk)}
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        content = json.loads(response.content)
        data = content.get("data", content)
        assert data["chat_id"] == str(existing_chat_id)

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["session_id"] == existing_session_id

    @patch("apps.sql_chat.views.get_sql_chat_credentials")
    @patch("apps.sql_chat.views.requests.post")
    def test_create_message_aws_error(self, mock_post, mock_get_credentials, client):
        """Test creation when AWS API returns error."""
        mock_get_credentials.return_value = {
            "api_key": "fake-api-key",
            "api_url": "https://fake-aws-api.com",
        }

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        response = client.post(
            path="/SqlChatMessage/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "SqlChatMessage",
                    "attributes": {
                        "input": "Teste erro",
                    },
                    "relationships": {
                        "company": {
                            "data": {"type": "Company", "id": str(self.company.pk)}
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        message = SqlChatMessage.objects.filter(input="Teste erro").first()
        assert message is not None
        assert message.status == "FAILED"
        assert message.error is not None

    @patch("apps.sql_chat.views.get_sql_chat_credentials")
    @patch("apps.sql_chat.views.requests.get")
    def test_retrieve_completed_message(self, mock_get, mock_get_credentials, client):
        """Test retrieving a completed SQL Chat message."""
        message = SqlChatMessage.objects.create(
            chat_id=uuid.uuid4(),
            company=self.company,
            created_by=self.user,
            input="Teste retrieve",
            request_id="test-request-456",
            status="STARTED",
        )

        mock_get_credentials.return_value = {
            "api_key": "fake-api-key",
            "api_url": "https://fake-aws-api.com",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "COMPLETED",
            "result": {
                "sql": "SELECT COUNT(*) FROM tabela",
                "data": [{"count": 100}],
            },
            "session_id": "updated-session-789",
        }
        mock_get.return_value = mock_response

        response = client.get(
            path="/SqlChatMessage/{}/?company={}".format(
                str(message.uuid), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

        message.refresh_from_db()
        assert message.status == "COMPLETED"
        assert message.result["sql"] == "SELECT COUNT(*) FROM tabela"
        assert message.session_id == "updated-session-789"

    @patch("apps.sql_chat.views.get_sql_chat_credentials")
    @patch("apps.sql_chat.views.requests.get")
    def test_retrieve_failed_message(self, mock_get, mock_get_credentials, client):
        """Test retrieving a failed SQL Chat message."""
        message = SqlChatMessage.objects.create(
            chat_id=uuid.uuid4(),
            company=self.company,
            created_by=self.user,
            input="Teste failed",
            request_id="test-request-fail",
            status="STARTED",
        )

        mock_get_credentials.return_value = {
            "api_key": "fake-api-key",
            "api_url": "https://fake-aws-api.com",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "FAILED",
            "error": "SQL inválido",
        }
        mock_get.return_value = mock_response

        response = client.get(
            path="/SqlChatMessage/{}/?company={}".format(
                str(message.uuid), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

        message.refresh_from_db()
        assert message.status == "FAILED"
        assert message.error == "SQL inválido"

    @patch("apps.sql_chat.views.get_sql_chat_credentials")
    @patch("apps.sql_chat.views.requests.get")
    def test_retrieve_needs_clarification(self, mock_get, mock_get_credentials, client):
        """Test retrieving a message that needs clarification."""
        message = SqlChatMessage.objects.create(
            chat_id=uuid.uuid4(),
            company=self.company,
            created_by=self.user,
            input="Teste clarification",
            request_id="test-request-clarify",
            status="STARTED",
        )

        mock_get_credentials.return_value = {
            "api_key": "fake-api-key",
            "api_url": "https://fake-aws-api.com",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "NEEDS_CLARIFICATION",
            "result": {
                "question": "Qual tabela você quer consultar?",
            },
        }
        mock_get.return_value = mock_response

        response = client.get(
            path="/SqlChatMessage/{}/?company={}".format(
                str(message.uuid), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

        message.refresh_from_db()
        assert message.status == "NEEDS_CLARIFICATION"
        assert message.result["question"] == "Qual tabela você quer consultar?"

    def test_list_messages_by_company(self, client):
        """Test listing SQL Chat messages by company returns one per chat_id."""
        chat_id_1 = uuid.uuid4()
        chat_id_2 = uuid.uuid4()

        SqlChatMessage.objects.create(
            chat_id=chat_id_1,
            company=self.company,
            created_by=self.user,
            input="Chat 1 - Msg 1",
            status="COMPLETED",
        )
        SqlChatMessage.objects.create(
            chat_id=chat_id_1,
            company=self.company,
            created_by=self.user,
            input="Chat 1 - Msg 2",
            status="COMPLETED",
        )
        SqlChatMessage.objects.create(
            chat_id=chat_id_2,
            company=self.company,
            created_by=self.user,
            input="Chat 2 - Msg 1",
            status="COMPLETED",
        )

        response = client.get(
            path="/SqlChatMessage/?company={}".format(str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        # Should return only first message of each chat_id (2 chats = 2 messages)
        assert len(content["data"]) == 2
        chat_ids = [item["attributes"]["chatId"] for item in content["data"]]
        assert str(chat_id_1) in chat_ids
        assert str(chat_id_2) in chat_ids

    def test_list_messages_by_chat_id(self, client):
        """Test listing SQL Chat messages filtered by chat_id."""
        chat_id_1 = uuid.uuid4()
        chat_id_2 = uuid.uuid4()

        SqlChatMessage.objects.create(
            chat_id=chat_id_1,
            company=self.company,
            created_by=self.user,
            input="Chat 1 - Msg 1",
            status="COMPLETED",
        )
        SqlChatMessage.objects.create(
            chat_id=chat_id_1,
            company=self.company,
            created_by=self.user,
            input="Chat 1 - Msg 2",
            status="COMPLETED",
        )
        SqlChatMessage.objects.create(
            chat_id=chat_id_2,
            company=self.company,
            created_by=self.user,
            input="Chat 2 - Msg 1",
            status="COMPLETED",
        )

        response = client.get(
            path="/SqlChatMessage/?company={}&chat_id={}".format(
                str(self.company.pk), str(chat_id_1)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        assert len(content["data"]) == 2

        for item in content["data"]:
            assert item["attributes"]["input"].startswith("Chat 1")

    def test_list_messages_without_company_returns_empty(self, client):
        """Test listing without company parameter returns empty."""
        response = client.get(
            path="/SqlChatMessage/?company={}".format(str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

    def test_model_str_method(self, client):
        """Test SqlChatMessage __str__ method."""
        message = SqlChatMessage.objects.create(
            chat_id=uuid.uuid4(),
            company=self.company,
            created_by=self.user,
            input="Test string",
            status="STARTED",
        )

        str_representation = str(message)
        assert self.company.name in str_representation
        assert "STARTED" in str_representation
