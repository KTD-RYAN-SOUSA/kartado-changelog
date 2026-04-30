from django.apps import AppConfig


class PermissionsConfig(AppConfig):
    name = "apps.permissions"

    def ready(self):
        import apps.permissions.signals  # noqa
