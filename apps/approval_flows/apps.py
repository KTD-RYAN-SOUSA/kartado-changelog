from django.apps import AppConfig


class ApprovalFlowsConfig(AppConfig):
    name = "apps.approval_flows"

    def ready(self):
        import apps.approval_flows.signals  # noqa
