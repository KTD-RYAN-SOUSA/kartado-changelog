import uuid

from helpers.permissions import BaseModelAccessPermissions

from .models import IntegrationConfig


class IntegrationConfigPermissions(BaseModelAccessPermissions):
    model_name = "IntegrationConfig"


class IntegrationRunPermissions(BaseModelAccessPermissions):
    model_name = "IntegrationRun"

    def get_company_id(self, action, request, obj=None):
        if action in ["list", "retrieve"]:
            if self.company_filter_key not in request.query_params:
                return False

            try:
                return uuid.UUID(request.query_params[self.company_filter_key])
            except Exception as e:
                print(e)
                return False

        elif action == "create":
            try:
                integration_config_id = uuid.UUID(
                    request.data["integration_config"]["id"]
                )
                integration_config = IntegrationConfig.objects.get(
                    pk=integration_config_id
                )
                return integration_config.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.integration_config.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False
