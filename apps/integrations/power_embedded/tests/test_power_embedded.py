import json
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status

from apps.integrations.power_embedded.client import (
    PowerEmbeddedClient,
    PowerEmbeddedError,
)
from apps.integrations.power_embedded.helpers import (
    build_group_name,
    ensure_user_in_pe,
    normalize_name,
)
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db

PE_CLIENT_PATH = "apps.integrations.power_embedded.client.requests.request"
VIEWS_GET_GROUP = "apps.integrations.power_embedded.views.get_group_for_company"
VIEWS_ENSURE_USER = "apps.integrations.power_embedded.views.ensure_user_in_pe"
VIEWS_CLIENT = "apps.integrations.power_embedded.views.PowerEmbeddedClient"


class TestNormalizeName:
    def test_removes_accents(self):
        assert normalize_name("Concessionária") == "concessionaria"

    def test_removes_special_characters(self):
        assert normalize_name("ANTT (SIGACO)") == "antt_sigaco"

    def test_replaces_spaces_with_underscore(self):
        assert normalize_name("Demo Concessionária") == "demo_concessionaria"

    def test_removes_hyphens(self):
        assert normalize_name("CCR - AutoBAn") == "ccr_autoban"

    def test_collapses_multiple_spaces(self):
        assert normalize_name("ENGIE  Energia") == "engie_energia"

    def test_preserves_numbers(self):
        assert normalize_name("Teste 123") == "teste_123"

    def test_full_example(self):
        assert normalize_name("Modelo ANTT (SIGACO)") == "modelo_antt_sigaco"


class TestBuildGroupName(TestBase):
    model = "power_bi"

    def test_builds_group_name(self):
        expected_permission = normalize_name(
            self.user.companies_membership.filter(company=self.company, is_active=True)
            .first()
            .permissions.name
        )
        expected_company = normalize_name(self.company.name)
        expected = f"{expected_permission}_{expected_company}"

        result = build_group_name(self.user, self.company)
        assert result == expected

    def test_returns_none_without_membership(self):
        self.user.companies_membership.filter(company=self.company).delete()
        result = build_group_name(self.user, self.company)
        assert result is None

    def test_returns_none_without_permissions_fk(self):
        membership = self.user.companies_membership.filter(company=self.company).first()
        membership.permissions = None
        membership.save()
        result = build_group_name(self.user, self.company)
        assert result is None


class TestPowerEmbeddedClient:
    @patch(PE_CLIENT_PATH)
    def test_get_user_by_email_found(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = (
            b'{"data": [{"email": "test@kartado.com.br", "id": "123"}]}'
        )
        mock_response.json.return_value = {
            "data": [{"email": "test@kartado.com.br", "id": "123"}]
        }
        mock_request.return_value = mock_response

        client = PowerEmbeddedClient()
        result = client.get_user_by_email("test@kartado.com.br")

        assert result is not None
        assert result["email"] == "test@kartado.com.br"
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args
        assert call_kwargs[1]["params"] == {"email": "test@kartado.com.br"}

    @patch(PE_CLIENT_PATH)
    def test_get_user_by_email_not_found(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data": []}'
        mock_response.json.return_value = {"data": []}
        mock_request.return_value = mock_response

        client = PowerEmbeddedClient()
        result = client.get_user_by_email("notfound@kartado.com.br")

        assert result is None

    @patch(PE_CLIENT_PATH)
    def test_create_user_payload(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"id": "123"}'
        mock_response.json.return_value = {"id": "123"}
        mock_request.return_value = mock_response

        client = PowerEmbeddedClient()
        client.create_user(email="test@kartado.com.br", name="Test User")

        call_kwargs = mock_request.call_args
        payload = call_kwargs[1]["json"]
        assert payload["email"] == "test@kartado.com.br"
        assert payload["name"] == "Test User"
        assert payload["role"] == 3
        assert payload["sendWelcomeEmail"] is False

    @patch(PE_CLIENT_PATH)
    def test_get_group_by_name_found(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = (
            b'{"data": [{"id": "g1", "name": "suporte_demo", "reports": ["r1"]}]}'
        )
        mock_response.json.return_value = {
            "data": [{"id": "g1", "name": "suporte_demo", "reports": ["r1"]}]
        }
        mock_request.return_value = mock_response

        client = PowerEmbeddedClient()
        result = client.get_group_by_name("suporte_demo")

        assert result is not None
        assert result["id"] == "g1"
        call_kwargs = mock_request.call_args
        assert call_kwargs[1]["params"] == {"name": "suporte_demo"}

    @patch(PE_CLIENT_PATH)
    def test_request_raises_on_error(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_request.return_value = mock_response

        client = PowerEmbeddedClient()
        with pytest.raises(PowerEmbeddedError):
            client.list_reports()

    @patch(PE_CLIENT_PATH)
    def test_generate_embed_url_payload(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = (
            b'{"embedUrl": "https://test.com", "expiresAt": "2026-01-01"}'
        )
        mock_response.json.return_value = {
            "embedUrl": "https://test.com",
            "expiresAt": "2026-01-01",
        }
        mock_request.return_value = mock_response

        client = PowerEmbeddedClient()
        result = client.generate_embed_url(
            user_email="test@kartado.com.br",
            report_id="r1",
            company_id="c1",
        )

        assert result["embedUrl"] == "https://test.com"
        call_kwargs = mock_request.call_args
        payload = call_kwargs[1]["json"]
        assert payload["embed"] is True
        assert payload["customFilters"] == [{"key": "company_id", "value": "c1"}]


class TestEnsureUserInPe:
    def test_creates_new_user(self):
        mock_client = MagicMock()
        mock_client.get_user_by_email.return_value = None
        mock_user = MagicMock()
        mock_user.email = "new@kartado.com.br"
        mock_user.get_full_name.return_value = "New User"

        result = ensure_user_in_pe(mock_client, mock_user, "group-1")

        assert result == "created"
        mock_client.create_user.assert_called_once_with(
            email="new@kartado.com.br", name="New User"
        )
        mock_client.link_user_to_groups.assert_called_once_with(
            email="new@kartado.com.br", group_ids=["group-1"]
        )

    def test_links_existing_user_to_group(self):
        mock_client = MagicMock()
        mock_client.get_user_by_email.return_value = {
            "email": "existing@kartado.com.br",
            "groups": ["other-group"],
        }
        mock_user = MagicMock()
        mock_user.email = "existing@kartado.com.br"

        result = ensure_user_in_pe(mock_client, mock_user, "group-1")

        assert result == "linked"
        mock_client.create_user.assert_not_called()
        mock_client.link_user_to_groups.assert_called_once()

    def test_already_linked(self):
        mock_client = MagicMock()
        mock_client.get_user_by_email.return_value = {
            "email": "existing@kartado.com.br",
            "groups": ["group-1"],
        }
        mock_user = MagicMock()
        mock_user.email = "existing@kartado.com.br"

        result = ensure_user_in_pe(mock_client, mock_user, "group-1")

        assert result == "already_linked"
        mock_client.create_user.assert_not_called()
        mock_client.link_user_to_groups.assert_not_called()


class TestReportListView(TestBase):
    model = "power_bi"

    @patch(VIEWS_CLIENT)
    @patch(VIEWS_ENSURE_USER)
    @patch(VIEWS_GET_GROUP)
    def test_list_reports(self, mock_get_group, mock_ensure, mock_client_cls, client):
        mock_get_group.return_value = {
            "id": "g1",
            "reports": ["r1", "r2"],
        }
        mock_client_instance = MagicMock()
        mock_client_instance.list_reports.return_value = {
            "data": [
                {"id": "r1", "name": "Report 1", "workspaceName": "WS"},
                {"id": "r2", "name": "Report 2", "workspaceName": "WS"},
                {"id": "r3", "name": "Report 3", "workspaceName": "WS"},
            ]
        }
        mock_client_cls.return_value = mock_client_instance

        response = client.get(
            path="/PowerEmbedded/Reports/?company={}".format(self.company.pk),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        data = content.get("data", content)
        reports = data if isinstance(data, list) else data.get("data", data)
        assert len(reports) == 2

    @patch(VIEWS_CLIENT)
    @patch(VIEWS_GET_GROUP)
    def test_empty_when_no_group(self, mock_get_group, mock_client_cls, client):
        mock_get_group.return_value = None
        mock_client_cls.return_value = MagicMock()

        response = client.get(
            path="/PowerEmbedded/Reports/?company={}".format(self.company.pk),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

    def test_forbidden_without_permission(self, client):
        false_permission(self.user, self.company, self.model, allowed="all")

        response = client.get(
            path="/PowerEmbedded/Reports/?company={}".format(self.company.pk),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestEmbedUrlView(TestBase):
    model = "power_bi"

    @patch(VIEWS_CLIENT)
    def test_generate_embed_url(self, mock_client_cls, client):
        mock_client_instance = MagicMock()
        mock_client_instance.generate_embed_url.return_value = {
            "embedUrl": "https://embed.test.com/token=abc",
            "expiresAt": "2026-01-01T00:00:00Z",
        }
        mock_client_cls.return_value = mock_client_instance

        response = client.get(
            path="/PowerEmbedded/Reports/004a41c6-5657-4ef9-85a7-3ec502ca1853/EmbedUrl/?company={}".format(
                self.company.pk
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        data = content.get("data", content)
        attrs = data.get("attributes", data)
        assert "embed_url" in attrs
        assert "expires_at" in attrs

    @patch(VIEWS_CLIENT)
    def test_502_when_embed_url_null(self, mock_client_cls, client):
        mock_client_instance = MagicMock()
        mock_client_instance.generate_embed_url.return_value = {
            "embedUrl": None,
            "expiresAt": None,
        }
        mock_client_cls.return_value = mock_client_instance

        response = client.get(
            path="/PowerEmbedded/Reports/004a41c6-5657-4ef9-85a7-3ec502ca1853/EmbedUrl/?company={}".format(
                self.company.pk
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY


class TestEnsureUserView(TestBase):
    model = "power_bi"

    @patch(VIEWS_CLIENT)
    @patch(VIEWS_ENSURE_USER)
    @patch(VIEWS_GET_GROUP)
    def test_ensure_user_created(
        self, mock_get_group, mock_ensure, mock_client_cls, client
    ):
        mock_get_group.return_value = {"id": "g1"}
        mock_ensure.return_value = "created"
        mock_client_cls.return_value = MagicMock()

        response = client.post(
            path="/PowerEmbedded/Users/Ensure/?company={}".format(self.company.pk),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        data = content.get("data", content)
        attrs = data.get("attributes", data)
        assert attrs["status"] == "created"

    @patch(VIEWS_CLIENT)
    @patch(VIEWS_GET_GROUP)
    def test_404_when_no_group(self, mock_get_group, mock_client_cls, client):
        mock_get_group.return_value = None
        mock_client_cls.return_value = MagicMock()

        response = client.post(
            path="/PowerEmbedded/Users/Ensure/?company={}".format(self.company.pk),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
