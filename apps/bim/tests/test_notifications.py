import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.bim.models import BIMModel
from apps.bim.notifications import notify_bim_done, notify_bim_error
from apps.companies.models import Company
from apps.notifications.models import PushNotification, UserPush
from apps.reportings.models import Reporting
from apps.users.models import User

pytestmark = pytest.mark.django_db


class TestBIMNotifications:
    """Testes para notificações de processamento BIM."""

    @pytest.fixture
    def company(self):
        """Cria uma company para os testes."""
        return Company.objects.create(
            name="Test Company",
            uuid=uuid.uuid4(),
        )

    @pytest.fixture
    def user(self, company):
        """Cria um usuário para os testes."""
        user = User.objects.create(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )
        return user

    @pytest.fixture
    def inventory(self, company):
        """Cria um inventory (Reporting) para os testes."""
        return Reporting.objects.create(
            uuid=uuid.uuid4(),
            company=company,
            number="INV-001",
            km=0.0,
            direction="Norte",
            lane="Faixa 1",
        )

    @pytest.fixture
    def bim_model(self, company, user, inventory):
        """Cria um BIMModel para os testes."""
        return BIMModel.objects.create(
            uuid=uuid.uuid4(),
            company=company,
            created_by=user,
            inventory=inventory,
            name="test_model.ifc",
            status=BIMModel.STATUS_DONE,
        )

    @patch("apps.bim.notifications.create_push_notifications")
    def test_notify_bim_done_creates_push_notification(
        self, mock_create_push, bim_model
    ):
        """Testa se notify_bim_done cria uma notificação de sucesso."""
        notify_bim_done(bim_model)

        mock_create_push.assert_called_once()
        call_kwargs = mock_create_push.call_args[1]

        assert call_kwargs["users"] == [bim_model.created_by]
        assert call_kwargs["company"] == bim_model.company
        assert "INV-001" in call_kwargs["message"]
        assert "foi processado" in call_kwargs["message"]
        assert f"/#/Inventory/{bim_model.inventory.uuid}/show/bim" in call_kwargs["url"]

    @patch("apps.bim.notifications.create_push_notifications")
    def test_notify_bim_error_creates_push_notification(
        self, mock_create_push, bim_model
    ):
        """Testa se notify_bim_error cria uma notificação de erro."""
        bim_model.status = BIMModel.STATUS_ERROR
        bim_model.error_message = "Test error"
        bim_model.save()

        notify_bim_error(bim_model)

        mock_create_push.assert_called_once()
        call_kwargs = mock_create_push.call_args[1]

        assert call_kwargs["users"] == [bim_model.created_by]
        assert call_kwargs["company"] == bim_model.company
        assert "INV-001" in call_kwargs["message"]
        assert "erro" in call_kwargs["message"].lower()
        assert f"/#/Inventory/{bim_model.inventory.uuid}/show/bim" in call_kwargs["url"]

    @patch("apps.bim.notifications.create_push_notifications")
    def test_notify_bim_done_without_user_does_not_create_notification(
        self, mock_create_push, bim_model
    ):
        """Testa que não cria notificação quando não há usuário."""
        bim_model.created_by = None
        bim_model.save()

        notify_bim_done(bim_model)

        mock_create_push.assert_not_called()

    @patch("apps.bim.notifications.create_push_notifications")
    def test_notify_bim_error_without_user_does_not_create_notification(
        self, mock_create_push, bim_model
    ):
        """Testa que não cria notificação de erro quando não há usuário."""
        bim_model.created_by = None
        bim_model.save()

        notify_bim_error(bim_model)

        mock_create_push.assert_not_called()

    @patch("apps.bim.notifications.create_push_notifications")
    def test_notify_bim_done_without_inventory_does_not_create_notification(
        self, mock_create_push, company, user
    ):
        """Testa que não cria notificação quando não há inventory."""
        # Cria BIMModel sem inventory (usando mock)
        bim_model = MagicMock()
        bim_model.uuid = uuid.uuid4()
        bim_model.created_by = user
        bim_model.company = company
        bim_model.inventory = None

        notify_bim_done(bim_model)

        mock_create_push.assert_not_called()

    @patch("apps.bim.notifications.create_push_notifications")
    def test_notify_bim_done_uses_uuid_when_no_inventory_number(
        self, mock_create_push, company, user
    ):
        """Testa que usa UUID quando inventory não tem número."""
        # Usa mock para inventory sem número (evita signal de auto_add_reporting_number)
        inventory_uuid = uuid.uuid4()
        mock_inventory = MagicMock()
        mock_inventory.uuid = inventory_uuid
        mock_inventory.number = ""

        mock_bim_model = MagicMock()
        mock_bim_model.uuid = uuid.uuid4()
        mock_bim_model.created_by = user
        mock_bim_model.company = company
        mock_bim_model.inventory = mock_inventory

        notify_bim_done(mock_bim_model)

        mock_create_push.assert_called_once()
        call_kwargs = mock_create_push.call_args[1]

        # Deve usar os primeiros 8 caracteres do UUID
        inventory_uuid_prefix = str(inventory_uuid)[:8]
        assert inventory_uuid_prefix in call_kwargs["message"]

    @patch("apps.bim.notifications.settings")
    @patch("apps.bim.notifications.create_push_notifications")
    def test_notify_bim_done_uses_frontend_url_from_settings(
        self, mock_create_push, mock_settings, bim_model
    ):
        """Testa que usa FRONTEND_URL das settings."""
        mock_settings.FRONTEND_URL = "https://app.kartado.com.br"

        notify_bim_done(bim_model)

        mock_create_push.assert_called_once()
        call_kwargs = mock_create_push.call_args[1]

        assert call_kwargs["url"].startswith("https://app.kartado.com.br/#/")


class TestBIMNotificationsIntegration:
    """Testes de integração para notificações BIM."""

    @pytest.fixture
    def company(self):
        """Cria uma company para os testes."""
        return Company.objects.create(
            name="Test Company",
            uuid=uuid.uuid4(),
        )

    @pytest.fixture
    def user(self, company):
        """Cria um usuário para os testes."""
        return User.objects.create(
            username="testuser_integration",
            email="test_integration@example.com",
            first_name="Test",
            last_name="User",
        )

    @pytest.fixture
    def inventory(self, company):
        """Cria um inventory (Reporting) para os testes."""
        return Reporting.objects.create(
            uuid=uuid.uuid4(),
            company=company,
            number="INV-INT-001",
            km=0.0,
            direction="Norte",
            lane="Faixa 1",
        )

    @pytest.fixture
    def bim_model(self, company, user, inventory):
        """Cria um BIMModel para os testes."""
        return BIMModel.objects.create(
            uuid=uuid.uuid4(),
            company=company,
            created_by=user,
            inventory=inventory,
            name="integration_test.ifc",
            status=BIMModel.STATUS_DONE,
        )

    def test_notify_bim_done_creates_push_notification_in_database(self, bim_model):
        """Testa se a notificação é realmente criada no banco."""
        initial_count = PushNotification.objects.count()
        initial_user_push_count = UserPush.objects.count()

        notify_bim_done(bim_model)

        assert PushNotification.objects.count() == initial_count + 1
        assert UserPush.objects.count() == initial_user_push_count + 1

        # Verifica a notificação criada
        push = PushNotification.objects.latest("created_at")
        assert "INV-INT-001" in push.message
        assert "foi processado" in push.message
        assert push.company == bim_model.company

        # Verifica o UserPush
        user_push = UserPush.objects.latest("push_message__created_at")
        assert user_push.user == bim_model.created_by
        assert user_push.push_message == push
        assert user_push.read is False

    def test_notify_bim_error_creates_push_notification_in_database(self, bim_model):
        """Testa se a notificação de erro é criada no banco."""
        bim_model.status = BIMModel.STATUS_ERROR
        bim_model.save()

        initial_count = PushNotification.objects.count()

        notify_bim_error(bim_model)

        assert PushNotification.objects.count() == initial_count + 1

        push = PushNotification.objects.latest("created_at")
        assert "INV-INT-001" in push.message
        assert "erro" in push.message.lower()
