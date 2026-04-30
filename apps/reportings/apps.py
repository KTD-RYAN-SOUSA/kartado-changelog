from django.apps import AppConfig


class ReportingsConfig(AppConfig):
    name = "apps.reportings"

    def ready(self):
        import apps.reportings.notifications  # noqa
        import apps.reportings.signals  # noqa
