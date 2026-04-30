import base64
import tempfile

import google.auth.transport.requests
import requests
from google.oauth2 import service_account

from .base import NotificationService

PROJECT_ID = "hidros-223919"
BASE_URL = "https://fcm.googleapis.com"
FCM_ENDPOINT = "v1/projects/" + PROJECT_ID + "/messages:send"
FCM_URL = BASE_URL + "/" + FCM_ENDPOINT
SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]


def _get_access_token(temp_file_path: str):
    """Retrieve a valid access token that can be used to authorize requests.
    :return: Access token.
    """
    credentials = service_account.Credentials.from_service_account_file(
        temp_file_path, scopes=SCOPES
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)

    return credentials.token


def send_fcm_notification(firebase_token, token, title, body, data):
    headers = {
        "Authorization": "Bearer " + firebase_token,
        "Content-Type": "application/json",
    }

    payload = {
        "message": {
            "token": token,
            "notification": {"body": body, "title": title},
            "data": data,
        }
    }

    response = requests.post(FCM_URL, json=payload, headers=headers)

    return response.json()


def fix_base64_padding(b64_string: str) -> str:
    return b64_string + "=" * (-len(b64_string) % 4)


class FirebaseNotificationService(NotificationService):
    @staticmethod
    def initialize(firebase_credentials_base64: str = None):
        """Initialize to get the token of firebase services to requests"""
        if not firebase_credentials_base64:
            raise ValueError(
                "A variável de ambiente FIREBASE_CREDENTIALS_BASE64 não foi definida!"
            )

        firebase_credentials_base64 = fix_base64_padding(firebase_credentials_base64)

        # Decodificar e criar um arquivo temporário
        json_data = base64.b64decode(firebase_credentials_base64).decode("utf-8")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_file:
            temp_file.write(json_data.encode("utf-8"))
            temp_file_path = temp_file.name

        _firebase_token = _get_access_token(temp_file_path)

        return _firebase_token

    @staticmethod
    def send(
        title: str,
        token: str,
        extra_payload: str,
        body: str = None,
        firebase_token: str = None,
    ):
        if firebase_token is None:
            raise Exception(
                "Firebase is not initialized. Call FirebaseNotificationService.initialize() first to get a valid token."
            )

        response = send_fcm_notification(
            firebase_token=firebase_token,
            token=token,
            title=title,
            body=body,
            data=extra_payload,
        )

        return response
