from unittest.mock import MagicMock, patch

import pytest

from helpers.apps.databricks import DatabricksClient

pytestmark = pytest.mark.django_db

MOCK_CREDS = {
    "host": "https://fake-databricks.com",
    "token": "fake-token",
    "warehouse_id": "fake-warehouse",
}


class TestDatabricksClient:
    @patch("helpers.apps.databricks.get_databricks_credentials")
    def _create_client(self, mock_creds):
        mock_creds.return_value = MOCK_CREDS
        return DatabricksClient()

    def test_parse_response_success(self):
        client = self._create_client()
        raw_response = {
            "manifest": {
                "schema": {
                    "columns": [
                        {"name": "id_rdo"},
                        {"name": "classe"},
                        {"name": "desc_classe"},
                        {"name": "regras"},
                    ]
                }
            },
            "result": {
                "data_array": [
                    ["rdo-1", "1", "revisao", '["regra 1", "regra 2"]'],
                    ["rdo-2", "0", "aprovado", '["regra 3"]'],
                ]
            },
        }

        result = client._parse_response(raw_response)

        assert len(result) == 2
        assert result[0]["id_rdo"] == "rdo-1"
        assert result[0]["classe"] == 1
        assert result[0]["regras"] == ["regra 1", "regra 2"]
        assert result[1]["classe"] == 0

    def test_parse_response_empty_data(self):
        client = self._create_client()
        raw_response = {
            "manifest": {"schema": {"columns": [{"name": "id_rdo"}]}},
            "result": {"data_array": []},
        }

        result = client._parse_response(raw_response)

        assert result is None

    @patch("helpers.apps.databricks.get_databricks_credentials")
    @patch("helpers.apps.databricks.requests.post")
    def test_execute_query_success(self, mock_post, mock_creds):
        mock_creds.return_value = MOCK_CREDS

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "status": {"state": "SUCCEEDED"},
            "manifest": {"schema": {"columns": [{"name": "id_rdo"}]}},
            "result": {"data_array": [["rdo-1"]]},
        }
        mock_post.return_value = mock_response

        client = DatabricksClient()
        result = client._execute_query("SELECT * FROM test")

        assert result is not None
        assert result["status"]["state"] == "SUCCEEDED"

    @patch("helpers.apps.databricks.get_databricks_credentials")
    @patch("helpers.apps.databricks.requests.post")
    def test_execute_query_http_error(self, mock_post, mock_creds):
        mock_creds.return_value = MOCK_CREDS

        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        client = DatabricksClient()
        result = client._execute_query("SELECT * FROM test")

        assert result is None

    @patch("helpers.apps.databricks.get_databricks_credentials")
    @patch("helpers.apps.databricks.requests.post")
    @patch("helpers.apps.databricks.requests.get")
    def test_polling_on_pending(self, mock_get, mock_post, mock_creds):
        mock_creds.return_value = MOCK_CREDS

        mock_post_response = MagicMock()
        mock_post_response.ok = True
        mock_post_response.json.return_value = {
            "status": {"state": "PENDING"},
            "statement_id": "stmt-123",
        }
        mock_post.return_value = mock_post_response

        mock_get_response = MagicMock()
        mock_get_response.ok = True
        mock_get_response.json.return_value = {
            "status": {"state": "SUCCEEDED"},
            "manifest": {"schema": {"columns": [{"name": "id_rdo"}]}},
            "result": {"data_array": [["rdo-1"]]},
        }
        mock_get.return_value = mock_get_response

        client = DatabricksClient()
        result = client._execute_query("SELECT * FROM test")

        assert result is not None
        assert result["status"]["state"] == "SUCCEEDED"
        mock_get.assert_called_once()

    @patch("helpers.apps.databricks.get_databricks_credentials")
    @patch("helpers.apps.databricks.requests.post")
    def test_wait_for_result_failed(self, mock_post, mock_creds):
        mock_creds.return_value = MOCK_CREDS

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "status": {"state": "FAILED", "error": {"message": "Query failed"}},
            "statement_id": "stmt-123",
        }
        mock_post.return_value = mock_response

        client = DatabricksClient()
        result = client._execute_query("SELECT * FROM test")

        assert result is None
