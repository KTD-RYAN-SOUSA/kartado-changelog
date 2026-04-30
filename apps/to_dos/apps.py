from django.apps import AppConfig


class ToDosConfig(AppConfig):
    name = "apps.to_dos"

    def ready(self):
        import apps.to_dos.signals  # noqa
