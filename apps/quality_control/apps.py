from django.apps import AppConfig


class QualityControlConfig(AppConfig):
    name = "apps.quality_control"

    def ready(self):
        import apps.quality_control.signals  # noqa
