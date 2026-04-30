import json
import logging
import time

import requests
import sentry_sdk

from helpers.aws import get_databricks_credentials
from RoadLabsAPI.settings import credentials

logger = logging.getLogger(__name__)


class DatabricksClient:
    def __init__(self):
        stage = credentials.stage.upper()
        creds = get_databricks_credentials(stage)
        self.host = creds["host"]
        self.token = creds["token"]
        self.warehouse_id = creds["warehouse_id"]

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _execute_query(self, statement, parameters=None):
        url = f"{self.host}/api/2.0/sql/statements"
        payload = {
            "statement": statement,
            "warehouse_id": self.warehouse_id,
            "wait_timeout": "50s",
            "on_wait_timeout": "CONTINUE",
        }
        if parameters:
            payload["parameters"] = parameters

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                data=json.dumps(payload),
                timeout=55,
            )
            if not response.ok:
                logger.error(
                    "Databricks request failed: %s %s",
                    response.status_code,
                    response.text,
                )
                return None

            result = response.json()
            return self._wait_for_result(result)

        except requests.exceptions.RequestException as e:
            logger.error("Databricks request failed: %s", e)
            sentry_sdk.capture_exception(e)
            return None

    def _wait_for_result(self, result, max_attempts=30, interval=5):
        state = result.get("status", {}).get("state")
        if state == "SUCCEEDED":
            return result

        statement_id = result.get("statement_id")
        if not statement_id:
            logger.error("Databricks: sem statement_id para polling")
            return None

        url = f"{self.host}/api/2.0/sql/statements/{statement_id}"

        for _ in range(max_attempts):
            if state in ("FAILED", "CANCELED", "CLOSED"):
                logger.error("Databricks query %s: %s", state, result.get("status", {}))
                return None

            time.sleep(interval)

            try:
                response = requests.get(url, headers=self._get_headers(), timeout=30)
                if not response.ok:
                    logger.error("Databricks polling failed: %s", response.text)
                    return None
                result = response.json()
                state = result.get("status", {}).get("state")
                if state == "SUCCEEDED":
                    return result
            except requests.exceptions.RequestException as e:
                logger.error("Databricks polling error: %s", e)
                sentry_sdk.capture_exception(e)
                return None

        logger.error("Databricks query timeout após %s tentativas", max_attempts)
        return None

    def _parse_response(self, raw_response):
        columns = [col["name"] for col in raw_response["manifest"]["schema"]["columns"]]
        result = raw_response.get("result", {})
        data_array = result.get("data_array") or result.get("dataArray") or []

        if not data_array:
            return None

        predictions = []
        for row in data_array:
            prediction = {}
            for col_name, value in zip(columns, row):
                if col_name == "regras" and isinstance(value, str):
                    prediction[col_name] = json.loads(value)
                elif col_name == "classe":
                    prediction[col_name] = int(value)
                else:
                    prediction[col_name] = value
            predictions.append(prediction)

        return predictions

    def predict_by_company(self, company_id):
        raw_response = self._execute_query(
            statement=(
                "SELECT * FROM development.gold.predict_rdo "
                "WHERE company_id = :company_id"
            ),
            parameters=[{"name": "company_id", "value": company_id}],
        )
        if raw_response is None:
            return None
        return self._parse_response(raw_response)
