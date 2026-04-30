from django.apps import AppConfig


class FilesConfig(AppConfig):
    name = "apps.files"

    def ready(self):
        import apps.files.signals  # noqa
