from django.apps import AppConfig


class OccurrenceRecordsConfig(AppConfig):
    name = "apps.occurrence_records"

    def ready(self):
        import apps.occurrence_records.notifications  # noqa
        import apps.occurrence_records.signals  # noqa
