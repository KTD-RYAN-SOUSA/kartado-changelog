from rest_framework_json_api import serializers

from apps.sql_chat.models import SqlChatMessage
from apps.users.models import User
from helpers.mixins import EagerLoadingMixin


class SqlChatUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["uuid", "first_name", "last_name", "email"]


class SqlChatMessageWriteSerializer(serializers.ModelSerializer):
    chat_id = serializers.UUIDField(required=False)

    class Meta:
        model = SqlChatMessage
        fields = ["input", "company", "chat_id"]


class SqlChatMessageListSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    created_by = SqlChatUserSerializer(read_only=True)

    _PREFETCH_RELATED_FIELDS = ["created_by"]

    class Meta:
        model = SqlChatMessage
        fields = [
            "chat_id",
            "input",
            "created_at",
            "created_by",
        ]


class SqlChatMessageReadSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    created_by = SqlChatUserSerializer(read_only=True)
    result = serializers.SerializerMethodField()

    _PREFETCH_RELATED_FIELDS = ["created_by"]

    class Meta:
        model = SqlChatMessage
        fields = [
            "uuid",
            "chat_id",
            "input",
            "status",
            "result",
            "error",
            "created_at",
            "created_by",
        ]

    def get_result(self, obj):
        if not obj.result:
            return {}
        result = obj.result.copy()
        result.pop("sql", None)
        result.pop("metadata", None)
        result.pop("explanation", None)
        return result
