from abc import ABC, abstractmethod


class NotificationService(ABC):
    """Interface para serviços de envio de notificações"""

    @abstractmethod
    def send(self, title: str, token: str, extra_payload: str):
        pass
