from django.apps import AppConfig


class MonitoringsConfig(AppConfig):
    name = "apps.monitorings"

    def ready(self):
        import apps.monitorings.signals  # noqa
        import apps.occurrence_records.notifications  # noqa
