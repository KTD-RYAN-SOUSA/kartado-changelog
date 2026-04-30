from django.apps import AppConfig


class ResourcesConfig(AppConfig):
    name = "apps.resources"

    def ready(self):
        import apps.resources.signals  # noqa
