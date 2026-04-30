from helpers.permissions import BaseModelAccessPermissions


class QueuedJudiciaryEmailPermissions(BaseModelAccessPermissions):
    model_name = "QueuedEmail"
