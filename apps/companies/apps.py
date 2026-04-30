from django.apps import AppConfig


class CompaniesConfig(AppConfig):
    name = "apps.companies"

    def ready(self):
        import apps.companies.notifications  # noqa
        import apps.companies.signals  # noqa
