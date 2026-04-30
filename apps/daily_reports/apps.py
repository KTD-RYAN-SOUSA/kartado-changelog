from django.apps import AppConfig


class DailyReportsConfig(AppConfig):
    name = "apps.daily_reports"

    def ready(self):
        import apps.daily_reports.signals  # noqa
