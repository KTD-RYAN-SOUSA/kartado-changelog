import pytest

from apps.users.models import UserNotification
from helpers.testing.tests import BaseModelTests

pytestmark = pytest.mark.django_db


class TestUserNotification(BaseModelTests):
    def init_manual_fields(self):
        self.model_class = UserNotification
        self.model_attributes = {
            "notification": "registros.adicao_aos_notificados",
            "notificationType": "EMAIL",
            "time_interval": "IMMEDIATE",
        }
        self.update_attributes = {
            "notificationType": "PUSH",
        }
        self.model_relationships = {
            "companies": [self.company],
            "user": self.user,
        }
