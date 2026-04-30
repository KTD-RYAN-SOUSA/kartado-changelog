import logging
import uuid

import requests
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from helpers.aws import get_sql_chat_credentials
from helpers.permissions import PermissionManager, join_queryset
from RoadLabsAPI.settings import credentials

from .models import SqlChatMessage
from .permissions import SqlChatMessagePermissions
from .serializers import (
    SqlChatMessageListSerializer,
    SqlChatMessageReadSerializer,
    SqlChatMessageWriteSerializer,
)

logger = logging.getLogger(__name__)


class SqlChatMessageView(viewsets.ModelViewSet):
    """
    ViewSet for SQL Chat messages
    """

    permission_classes = [IsAuthenticated, SqlChatMessagePermissions]
    permissions = None
    ordering = "created_at"

    def get_queryset(self):
        queryset = None

        if self.action == "list":
            if "company" not in self.request.query_params:
                return SqlChatMessage.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="SqlChatMessage",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, SqlChatMessage.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    SqlChatMessage.objects.filter(
                        company_id=user_company, created_by=self.request.user
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, SqlChatMessage.objects.filter(company_id=user_company)
                )

            chat_id = self.request.query_params.get("chat_id")
            if chat_id and queryset is not None:
                queryset = queryset.filter(chat_id=chat_id)
            elif queryset is not None:
                first_msg_ids = (
                    queryset.order_by("chat_id", "created_at")
                    .distinct("chat_id")
                    .values_list("uuid", flat=True)
                )
                queryset = queryset.filter(uuid__in=list(first_msg_ids))

        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = SqlChatMessage.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(
            queryset.distinct().order_by("created_at")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return SqlChatMessageWriteSerializer
        if self.action == "list":
            if self.request.query_params.get("chat_id"):
                return SqlChatMessageReadSerializer
            return SqlChatMessageListSerializer
        return SqlChatMessageReadSerializer

    def retrieve(self, request, *args, **kwargs):
        """Return message. If processing, poll AWS for status."""
        instance = self.get_object()

        if instance.status in ["STARTED", "PROCESSING"] and instance.request_id:
            self._poll_aws(instance)

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def _poll_aws(self, message):
        """Poll AWS for status and update message."""
        stage = credentials.stage.upper()
        api_credentials = get_sql_chat_credentials(stage)

        try:
            response = requests.get(
                f"{api_credentials['api_url']}?id={message.request_id}",
                headers={"x-api-key": api_credentials["api_key"]},
                timeout=30,
            )

            if response.status_code != 200:
                raise Exception(
                    f"AWS API error: {response.status_code} - {response.text}"
                )

            aws_data = response.json()
            message.status = aws_data.get("status", message.status)

            status_handlers = {
                "COMPLETED": lambda: setattr(
                    message, "result", aws_data.get("result", {})
                ),
                "NEEDS_CLARIFICATION": lambda: setattr(
                    message, "result", aws_data.get("result", {})
                ),
                "FAILED": lambda: setattr(
                    message, "error", aws_data.get("error", "Erro desconhecido")
                ),
            }

            handler = status_handlers.get(message.status)
            if handler:
                handler()

            if aws_data.get("session_id"):
                message.session_id = aws_data["session_id"]

            message.save()

        except Exception as e:
            logger.error(f"Erro polling AWS: {e}")

    def create(self, request, *args, **kwargs):
        """Create message and send to AWS."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        input_text = serializer.validated_data["input"]
        company = serializer.validated_data["company"]
        chat_id = serializer.validated_data.get("chat_id") or uuid.uuid4()

        last_message = (
            SqlChatMessage.objects.filter(chat_id=chat_id, session_id__isnull=False)
            .order_by("-created_at")
            .first()
        )
        session_id = last_message.session_id if last_message else None

        message = SqlChatMessage.objects.create(
            chat_id=chat_id,
            session_id=session_id,
            company=company,
            created_by=request.user,
            input=input_text,
            status="STARTED",
        )

        try:
            stage = credentials.stage.upper()
            api_credentials = get_sql_chat_credentials(stage)

            payload = {
                "input": input_text,
                "company_id": str(company.uuid),
            }
            if session_id:
                payload["session_id"] = session_id

            response = requests.post(
                api_credentials["api_url"],
                json=payload,
                headers={"x-api-key": api_credentials["api_key"]},
                timeout=30,
            )

            if response.status_code != 200:
                raise Exception(
                    f"AWS API error: {response.status_code} - {response.text}"
                )

            aws_data = response.json()

            message.request_id = aws_data.get("request_id")
            message.session_id = aws_data.get("session_id")
            message.save()

        except Exception as e:
            logger.error(f"Erro ao enviar para AWS: {e}")
            message.status = "FAILED"
            message.error = str(e)
            message.save()
            return Response(
                {"error": "Falha ao iniciar processamento"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "uuid": str(message.uuid),
                "request_id": message.request_id,
                "session_id": message.session_id,
                "chat_id": str(message.chat_id),
                "status": message.status,
            },
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, pk=None):
        """Delete all messages from a chat."""

        obj = self.get_object()
        chat_id = obj.chat_id

        SqlChatMessage.objects.filter(chat_id=chat_id).delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
