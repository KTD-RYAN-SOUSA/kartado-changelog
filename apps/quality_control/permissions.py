import uuid

from apps.companies.models import Firm
from apps.reportings.models import Reporting
from helpers.permissions import BaseModelAccessPermissions


class QualityProjectPermissions(BaseModelAccessPermissions):
    model_name = "QualityProject"

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
                firm_id = uuid.UUID(request.data["firm"]["id"])
                firm = Firm.objects.get(pk=firm_id)
                return firm.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.firm.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class ConstructionPlantPermissions(BaseModelAccessPermissions):
    model_name = "ConstructionPlant"


class QualitySamplePermissions(BaseModelAccessPermissions):
    model_name = "QualitySample"


class QualityAssayPermissions(BaseModelAccessPermissions):
    model_name = "QualityAssay"


class QualityControlExportPermissions(BaseModelAccessPermissions):
    model_name = "QualityControlExport"

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
                reporting_id = uuid.UUID(request.data["reporting"]["id"])
                reporting = Reporting.objects.get(pk=reporting_id)
                return reporting.firm.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.reporting.firm.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False
