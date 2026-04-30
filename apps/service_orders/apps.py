from django.apps import AppConfig


class ServiceOrdersConfig(AppConfig):
    name = "apps.service_orders"

    def ready(self):
        import apps.service_orders.notifications  # noqa
        import apps.service_orders.signals  # noqa
