from helpers.permissions import BaseModelAccessPermissions


class SqlChatMessagePermissions(BaseModelAccessPermissions):
    model_name = "SqlChatMessage"
