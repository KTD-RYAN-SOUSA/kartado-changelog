import uuid

from apps.constructions.models import Construction
from helpers.permissions import BaseModelAccessPermissions


class ConstructionPermissions(BaseModelAccessPermissions):
    model_name = "Construction"


class ConstructionProgressPermissions(BaseModelAccessPermissions):
    model_name = "ConstructionProgress"

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
                construction_id = uuid.UUID(request.data["construction"]["id"])
                construction = Construction.objects.get(pk=construction_id)
                return construction.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.construction.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False
