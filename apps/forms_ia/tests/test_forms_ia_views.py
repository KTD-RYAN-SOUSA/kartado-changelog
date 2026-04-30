import json
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status

from apps.forms_ia.models import FormsIARequest
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestFormsIARequestView(TestBase):
    model = "FormsIARequest"

    @patch("apps.forms_ia.views.get_forms_ia_credentials")
    @patch("apps.forms_ia.views.requests.post")
    def test_create_forms_ia_request_success(
        self, mock_post, mock_get_credentials, client
    ):
        """Test successful creation of Forms IA request"""
        # Mock credentials
        mock_get_credentials.return_value = {
            "api_key": "fake-api-key",
            "api_url": "https://fake-bedrock-api.com",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"request_id": "test-request-123"}
        mock_post.return_value = mock_response

        response = client.post(
            path="/FormsIARequest/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "FormsIARequest",
                    "attributes": {
                        "occurrenceKind": "inspection",
                        "name": "Test Form IA",
                        "inputText": "Create a form for road inspection",
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
        request_obj = FormsIARequest.objects.get(uuid=content["data"]["id"])

        assert request_obj.name == "Test Form IA"
        assert request_obj.occurrence_kind == "inspection"
        assert request_obj.request_id == "test-request-123"
        assert request_obj.done is False
        assert request_obj.error is False
        assert request_obj.created_by == self.user

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["x-api-key"] == "fake-api-key"
        assert "Test Form IA" in call_kwargs["json"]["input"]

    @patch("apps.forms_ia.views.get_forms_ia_credentials")
    @patch("apps.forms_ia.views.requests.post")
    def test_create_forms_ia_request_bedrock_error(
        self, mock_post, mock_get_credentials, client
    ):
        """Test creation when Bedrock API returns error"""
        mock_get_credentials.return_value = {
            "api_key": "fake-api-key",
            "api_url": "https://fake-bedrock-api.com",
        }

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        response = client.post(
            path="/FormsIARequest/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "FormsIARequest",
                    "attributes": {
                        "occurrenceKind": "inspection",
                        "name": "Test Form Error",
                        "inputText": "Create a form",
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

        request_obj = FormsIARequest.objects.filter(name="Test Form Error").first()
        assert request_obj is not None
        assert request_obj.error is True
        assert request_obj.error_message == "Erro ao iniciar processamento"
        assert request_obj.created_by == self.user

    @patch("apps.forms_ia.views.get_forms_ia_credentials")
    @patch("apps.forms_ia.views.requests.post")
    def test_create_forms_ia_request_no_request_id(
        self, mock_post, mock_get_credentials, client
    ):
        """Test creation when Bedrock API returns response without request_id"""
        mock_get_credentials.return_value = {
            "api_key": "fake-api-key",
            "api_url": "https://fake-bedrock-api.com",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "pending"}
        mock_post.return_value = mock_response

        response = client.post(
            path="/FormsIARequest/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "FormsIARequest",
                    "attributes": {
                        "occurrenceKind": "inspection",
                        "name": "Test No Request ID",
                        "inputText": "Create a form",
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

        request_obj = FormsIARequest.objects.filter(name="Test No Request ID").first()
        assert request_obj is not None
        assert request_obj.error is True
        assert request_obj.error_message == "Resposta inválida do processamento"
        assert request_obj.created_by == self.user

    @patch("apps.forms_ia.views.get_forms_ia_credentials")
    @patch("apps.forms_ia.views.requests.get")
    def test_retrieve_completed_request(self, mock_get, mock_get_credentials, client):
        """Test retrieving a completed Forms IA request"""
        forms_ia_request = FormsIARequest.objects.create(
            company=self.company,
            occurrence_kind="inspection",
            name="Test Retrieve",
            input_text="Create a form",
            request_id="test-request-456",
            created_by=self.user,
        )

        mock_get_credentials.return_value = {
            "api_key": "fake-api-key",
            "api_url": "https://fake-bedrock-api.com",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "COMPLETED",
            "result": {
                "response": {
                    "displayName": "Test Form",
                    "fields": [{"id": 1, "apiName": "testField", "dataType": "string"}],
                    "groups": [],
                }
            },
        }
        mock_get.return_value = mock_response

        response = client.get(
            path="/FormsIARequest/{}/?company={}".format(
                str(forms_ia_request.uuid), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

        forms_ia_request.refresh_from_db()
        assert forms_ia_request.done is True
        assert forms_ia_request.output_json["data"]["displayName"] == "Test Form"

    @patch("apps.forms_ia.views.get_forms_ia_credentials")
    @patch("apps.forms_ia.views.requests.get")
    def test_retrieve_failed_request(self, mock_get, mock_get_credentials, client):
        """Test retrieving a failed Forms IA request"""
        forms_ia_request = FormsIARequest.objects.create(
            company=self.company,
            occurrence_kind="inspection",
            name="Test Failed",
            input_text="Create a form",
            request_id="test-request-789",
            created_by=self.user,
        )

        mock_get_credentials.return_value = {
            "api_key": "fake-api-key",
            "api_url": "https://fake-bedrock-api.com",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "FAILED",
            "error_message": "Processing error",
        }
        mock_get.return_value = mock_response

        response = client.get(
            path="/FormsIARequest/{}/?company={}".format(
                str(forms_ia_request.uuid), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

        forms_ia_request.refresh_from_db()
        assert forms_ia_request.error is True
        assert forms_ia_request.error_message == "Processing error"

    def test_list_forms_ia_requests(self, client):
        """Test listing Forms IA requests"""
        FormsIARequest.objects.create(
            company=self.company,
            occurrence_kind="inspection",
            name="Form 1",
            input_text="Input 1",
            created_by=self.user,
        )
        FormsIARequest.objects.create(
            company=self.company,
            occurrence_kind="maintenance",
            name="Form 2",
            input_text="Input 2",
            created_by=self.user,
        )

        response = client.get(
            path="/FormsIARequest/?company={}".format(str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        assert len(content["data"]) >= 2

    def test_model_str_method(self, client):
        """Test FormsIARequest __str__ method"""
        request_obj = FormsIARequest.objects.create(
            company=self.company,
            occurrence_kind="inspection",
            name="Test String",
            input_text="Test input",
            created_by=self.user,
        )

        str_representation = str(request_obj)
        assert self.company.name in str_representation
        assert "Test String" in str_representation
