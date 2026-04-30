import uuid

from helpers.permissions import BaseModelAccessPermissions

from .models import ApprovalFlow, ApprovalStep


class ApprovalFlowPermissions(BaseModelAccessPermissions):
    model_name = "ApprovalFlow"


class ApprovalStepPermissions(BaseModelAccessPermissions):
    model_name = "ApprovalStep"

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
                approval_flow = ApprovalFlow.objects.get(
                    pk=uuid.UUID(request.data["approval_flow"]["id"])
                )
                return approval_flow.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.approval_flow.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False


class ApprovalTransitionPermissions(BaseModelAccessPermissions):
    model_name = "ApprovalTransition"

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
                approval_step = ApprovalStep.objects.get(
                    pk=uuid.UUID(request.data["origin"]["id"])
                )
                return approval_step.approval_flow.company_id
            except Exception as e:
                print(e)
                return False

        elif action in ["update", "partial_update", "destroy"]:
            try:
                return obj.origin.approval_flow.company_id
            except Exception as e:
                print(e)
                return False

        else:
            return False
