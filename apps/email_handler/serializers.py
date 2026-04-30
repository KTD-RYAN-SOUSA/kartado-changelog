from django.conf import settings
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import ResourceRelatedField

from apps.email_handler.models import QueuedEmail
from helpers.mixins import EagerLoadingMixin


class QueuedJudiciaryEmailSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "company",
        "issuer",
        "file_download",
        "send_to_users",
    ]

    uuid = serializers.UUIDField(required=False)
    send_to_users = ResourceRelatedField(many=True, read_only=True)
    zip_file_url = serializers.SerializerMethodField(read_only=True)
    status = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = QueuedEmail
        fields = [
            "uuid",
            "sent_at",
            "issuer",
            "send_to_users",
            "zip_file_url",
            "opened_at",
            "status",
            "created_at",
        ]

    def get_zip_file_url(self, obj: QueuedEmail) -> str:
        # NOTE: Should not include the `qe=<uuid>` argument to avoid being marked as opened
        if obj.file_download:
            fd_pk = obj.file_download.pk
            at = self.context["request"].user.pk
            return f"{settings.BACKEND_URL}/FileDownload/{fd_pk}?access_token={at}"

        return None

    def get_status(self, obj: QueuedEmail) -> str:
        return obj.status
