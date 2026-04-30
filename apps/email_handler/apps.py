from django.apps import AppConfig


class EmailHandlerConfig(AppConfig):
    name = "apps.email_handler"

    def ready(self):
        import apps.email_handler.signals  # noqa
