from django.apps import AppConfig


class WorkPlansConfig(AppConfig):
    name = "apps.work_plans"

    def ready(self):
        import apps.work_plans.notifications  # noqa
        import apps.work_plans.signals  # noqa
