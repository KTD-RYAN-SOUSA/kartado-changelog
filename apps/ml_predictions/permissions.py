from helpers.permissions import BaseModelAccessPermissions


class MLPredictionPermissions(BaseModelAccessPermissions):
    model_name = "MLPrediction"

    def has_permission(self, request, view):
        if view.action in ["create"]:
            return False
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if view.action in ["destroy"]:
            return False
        return super().has_object_permission(request, view, obj)
