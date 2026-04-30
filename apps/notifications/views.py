from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.filters import PushNotificationFilter
from apps.notifications.models import PushNotification
from apps.notifications.serializers import PushNotificationSerializer
from apps.notifications.services import sqs_notification_service


class PushNotificationView(viewsets.ModelViewSet):
    serializer_class = PushNotificationSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = PushNotificationFilter
    permissions = None

    ordering_fields = ["id", "created_at", "updated_at", "sent", "read"]
    ordering = "id"

    def get_queryset(self):
        queryset = PushNotification.objects.filter(
            users=self.request.user, cleared=True
        ).distinct()

        return self.get_serializer_class().setup_eager_loading(queryset)


class SQSMonitoringView(APIView):
    """
    View for monitoring SQS queue metrics and health.
    Useful for debugging and operational monitoring.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Get queue metrics
            queue_metrics = sqs_notification_service.get_queue_metrics()

            # Get database metrics
            db_metrics = {
                "unsent_notifications": PushNotification.objects.filter(
                    sent=False, cleared=True
                ).count(),
                "in_progress_notifications": PushNotification.objects.filter(
                    sent=False, in_progress=True
                ).count(),
                "total_notifications_today": PushNotification.objects.filter(
                    created_at__date=timezone.now().date()
                ).count(),
            }

            # SQS service status
            sqs_status = {
                "enabled": sqs_notification_service.enabled,
                "client_initialized": sqs_notification_service.sqs_client is not None,
                "queue_url": sqs_notification_service.queue_url,
            }

            return Response(
                {
                    "sqs_status": sqs_status,
                    "queue_metrics": queue_metrics,
                    "database_metrics": db_metrics,
                    "timestamp": timezone.now().isoformat(),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SQSTestView(APIView):
    """
    View for testing SQS publishing functionality.
    Only available for testing/debugging purposes.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            notification_id = request.data.get("notification_id")
            if not notification_id:
                return Response(
                    {"error": "notification_id is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if notification exists
            try:
                notification = PushNotification.objects.get(id=notification_id)
            except PushNotification.DoesNotExist:
                return Response(
                    {"error": f"PushNotification {notification_id} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Publish to SQS
            company_id = notification.company.id if notification.company else None
            success = sqs_notification_service.publish_notification(
                notification_id=notification_id, company_id=company_id
            )

            return Response(
                {
                    "success": success,
                    "notification_id": notification_id,
                    "message": "Test publish completed",
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
