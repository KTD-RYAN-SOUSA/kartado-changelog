import logging

import requests
from rest_framework.exceptions import APIException

from .helpers import get_credentials

logger = logging.getLogger(__name__)


class PowerEmbeddedError(APIException):
    status_code = 502
    default_detail = "Power Embedded service unavailable"
    default_code = "power_embedded_error"


class PowerEmbeddedClient:
    VIEWER_ROLE = 3

    def __init__(self):
        creds = get_credentials()
        self.base_url = creds.get("base_url", "")
        self.api_key = creds.get("api_key", "")
        self.organization_id = creds.get("organization_id", "")

    def _headers(self):
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _request(self, method, path, params=None, **kwargs):
        url = f"{self.base_url}{path}"
        response = requests.request(
            method,
            url,
            headers=self._headers(),
            params=params,
            timeout=30,
            **kwargs,
        )
        if response.status_code >= 400:
            raise PowerEmbeddedError(
                detail=(f"PE API error: {response.status_code}" f" on {method} {path}"),
            )
        if not response.content:
            return None
        return response.json()

    def get_user_by_email(self, email):
        response = self._request("GET", "/api/user", params={"email": email})
        if not response or not response.get("data"):
            return None
        for user in response["data"]:
            if user.get("email", "").lower() == email.lower():
                return user
        return None

    def create_user(self, email, name):
        return self._request(
            "POST",
            "/api/user",
            json={
                "email": email,
                "name": name,
                "role": self.VIEWER_ROLE,
                "sendWelcomeEmail": False,
            },
        )

    def link_user_to_groups(self, email, group_ids):
        return self._request(
            "PUT",
            "/api/user/link-groups",
            json={"userEmail": email, "groups": group_ids},
        )

    def get_group_by_name(self, name):
        response = self._request("GET", "/api/groups", params={"name": name})
        if not response or not response.get("data"):
            return None
        for group in response["data"]:
            if group.get("name", "").lower() == name.lower():
                return group
        return None

    def list_reports(self):
        return self._request("GET", "/api/report")

    def generate_embed_url(self, user_email, report_id, company_id):
        return self._request(
            "POST",
            "/api/identity/url",
            json={
                "userEmail": user_email,
                "organizationId": self.organization_id,
                "reportId": report_id,
                "embed": True,
                "language": "pt-BR",
                "customFilters": [{"key": "company_id", "value": str(company_id)}],
            },
        )
