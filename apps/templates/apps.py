from django.apps import AppConfig


class TemplatesConfig(AppConfig):
    name = "apps.templates"

    def ready(self):
        import apps.templates.notifications  # noqa
        import apps.templates.signals  # noqa
