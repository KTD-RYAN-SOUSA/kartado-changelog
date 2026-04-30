from unittest.mock import Mock, patch

import jwt
import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import exceptions

from helpers.auth import (
    CustomTokenAuthentication,
    custom_encode_handler,
    custom_jwt_get_secret_key,
    jwt_get_secret_key,
    payload_handler,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


class TestJwtGetSecretKey(TestCase):
    """Tests for jwt_get_secret_key function"""

    def test_jwt_get_secret_key(self):
        """Test that jwt_get_secret_key returns user's jwt_secret"""
        user = Mock()
        user.jwt_secret = "user-specific-secret-123"

        result = jwt_get_secret_key(user)

        assert result == "user-specific-secret-123"


class TestPayloadHandler(TestCase):
    """Tests for payload_handler function"""

    @patch("helpers.auth.jwt_create_payload")
    def test_payload_handler_default_type_access(self, mock_create_payload):
        """Test payload_handler with default type_access='all'"""
        user = Mock()
        mock_create_payload.return_value = {"user_id": 123, "username": "testuser"}

        result = payload_handler(user)

        assert result["type_access"] == "all"
        assert "user_id" in result
        mock_create_payload.assert_called_once_with(user)

    @patch("helpers.auth.jwt_create_payload")
    def test_payload_handler_custom_type_access(self, mock_create_payload):
        """Test payload_handler with custom type_access"""
        user = Mock()
        mock_create_payload.return_value = {"user_id": 456}

        result = payload_handler(user, type_access="mobile")

        assert result["type_access"] == "mobile"
        assert result["user_id"] == 456

    @patch("helpers.auth.jwt_create_payload")
    def test_payload_handler_readonly_type_access(self, mock_create_payload):
        """Test payload_handler with readonly type_access"""
        user = Mock()
        mock_create_payload.return_value = {"user_id": 789}

        result = payload_handler(user, type_access="readonly")

        assert result["type_access"] == "readonly"


class TestCustomJwtGetSecretKey(TestCase):
    """Tests for custom_jwt_get_secret_key function"""

    @patch("helpers.auth.api_settings")
    def test_custom_jwt_get_secret_key_without_user_secret(self, mock_settings):
        """Test when JWT_GET_USER_SECRET_KEY is not configured"""
        mock_settings.JWT_GET_USER_SECRET_KEY = None
        mock_settings.JWT_SECRET_KEY = "default-secret-key"

        result = custom_jwt_get_secret_key({"user_id": 1})

        assert result == "default-secret-key"

    @patch("helpers.auth.get_user_model")
    @patch("helpers.auth.api_settings")
    def test_custom_jwt_get_secret_key_with_user_secret(
        self, mock_settings, mock_get_user_model
    ):
        """Test when JWT_GET_USER_SECRET_KEY is configured"""
        # Setup user
        mock_user_class = Mock()
        mock_user = Mock()
        mock_user.pk = 123
        mock_user_class.objects.using.return_value.get.return_value = mock_user
        mock_get_user_model.return_value = mock_user_class

        # Setup secret key function
        def get_user_secret(user):
            return f"user-{user.pk}-secret"

        mock_settings.JWT_GET_USER_SECRET_KEY = get_user_secret

        result = custom_jwt_get_secret_key({"user_id": 123}, db_alias="default")

        assert result == "user-123-secret"
        mock_user_class.objects.using.assert_called_once_with("default")

    @patch("helpers.auth.get_user_model")
    @patch("helpers.auth.api_settings")
    def test_custom_jwt_get_secret_key_custom_db_alias(
        self, mock_settings, mock_get_user_model
    ):
        """Test with custom database alias"""
        mock_user_class = Mock()
        mock_user = Mock()
        mock_user_class.objects.using.return_value.get.return_value = mock_user
        mock_get_user_model.return_value = mock_user_class

        mock_settings.JWT_GET_USER_SECRET_KEY = lambda user: "secret"

        custom_jwt_get_secret_key({"user_id": 1}, db_alias="replica")

        mock_user_class.objects.using.assert_called_once_with("replica")


class TestCustomEncodeHandler(TestCase):
    """Tests for custom_encode_handler function"""

    @patch("helpers.auth.custom_jwt_get_secret_key")
    @patch("helpers.auth.api_settings")
    @patch("helpers.auth.jwt")
    def test_custom_encode_handler_hs_algorithm(
        self, mock_jwt_module, mock_settings, mock_get_key
    ):
        """Test encoding with HS256 algorithm"""
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_get_key.return_value = "secret-key"
        mock_jwt_module.encode.return_value = "encoded.jwt.token"

        payload = {"user_id": 123}
        custom_encode_handler(payload, "default")

        mock_get_key.assert_called_once_with(payload, "default")
        mock_jwt_module.encode.assert_called_once()

    @patch("helpers.auth.api_settings")
    @patch("helpers.auth.jwt")
    def test_custom_encode_handler_rs_algorithm(self, mock_jwt_module, mock_settings):
        """Test encoding with RS256 algorithm"""
        mock_settings.JWT_ALGORITHM = "RS256"
        mock_settings.JWT_PRIVATE_KEY = "private-key-content"
        mock_jwt_module.encode.return_value = "encoded.jwt.token"

        payload = {"user_id": 456}
        custom_encode_handler(payload, "default")

        mock_jwt_module.encode.assert_called_once()

    @patch("helpers.auth.custom_jwt_get_secret_key")
    @patch("helpers.auth.api_settings")
    @patch("helpers.auth.jwt")
    def test_custom_encode_handler_with_dict_key(
        self, mock_jwt_module, mock_settings, mock_get_key
    ):
        """Test encoding when key is a dictionary (kid scenario)"""
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_get_key.return_value = {"kid1": "key-value"}
        mock_jwt_module.encode.return_value = "encoded.jwt.token"

        payload = {"user_id": 789}
        custom_encode_handler(payload, "default")

        # Should extract first key-value pair and set kid header
        mock_jwt_module.encode.assert_called_once()
        call_args = mock_jwt_module.encode.call_args
        assert call_args[1]["headers"] == {"kid": "kid1"}

    @patch("helpers.auth.custom_jwt_get_secret_key")
    @patch("helpers.auth.api_settings")
    @patch("helpers.auth.jwt")
    def test_custom_encode_handler_with_list_key(
        self, mock_jwt_module, mock_settings, mock_get_key
    ):
        """Test encoding when key is a list"""
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_get_key.return_value = ["first-key", "second-key"]
        mock_jwt_module.encode.return_value = "encoded.jwt.token"

        payload = {"user_id": 321}
        custom_encode_handler(payload, "default")

        # Should use first key in list
        mock_jwt_module.encode.assert_called_once()


class TestCustomTokenAuthentication(TestCase):
    """Tests for CustomTokenAuthentication class"""

    def setUp(self):
        """Set up test authentication instance"""
        self.auth = CustomTokenAuthentication()

    @patch.object(CustomTokenAuthentication, "get_token_from_request")
    def test_authenticate_no_token(self, mock_get_token):
        """Test authentication when no token is provided"""
        mock_get_token.return_value = None
        request = Mock()

        result = self.auth.authenticate(request)

        assert result is None

    @patch.object(CustomTokenAuthentication, "jwt_decode_token")
    @patch.object(CustomTokenAuthentication, "get_token_from_request")
    def test_authenticate_expired_token(self, mock_get_token, mock_decode):
        """Test authentication with expired token"""
        from rest_framework_jwt.compat import ExpiredSignature

        mock_get_token.return_value = "expired.token"
        mock_decode.side_effect = ExpiredSignature()

        request = Mock()

        with pytest.raises(exceptions.AuthenticationFailed, match="Token has expired"):
            self.auth.authenticate(request)

    @patch.object(CustomTokenAuthentication, "jwt_decode_token")
    @patch.object(CustomTokenAuthentication, "get_token_from_request")
    def test_authenticate_invalid_token(self, mock_get_token, mock_decode):
        """Test authentication with invalid token"""
        mock_get_token.return_value = "invalid.token"
        mock_decode.side_effect = jwt.DecodeError()

        request = Mock()

        with pytest.raises(
            exceptions.AuthenticationFailed, match="Error decoding token"
        ):
            self.auth.authenticate(request)
