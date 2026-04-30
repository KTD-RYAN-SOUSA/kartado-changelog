from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    name = "apps.integrations"

    def ready(self):
        import apps.integrations.signals  # noqa
