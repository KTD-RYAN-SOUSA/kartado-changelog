from django.apps import AppConfig


class RoadsConfig(AppConfig):
    name = "apps.roads"

    def ready(self):
        import apps.roads.signals  # noqa
