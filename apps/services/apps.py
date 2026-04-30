from django.apps import AppConfig


class ServicesConfig(AppConfig):
    name = "apps.services"

    def ready(self):
        import apps.services.signals  # noqa
