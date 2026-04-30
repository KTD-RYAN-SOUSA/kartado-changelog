from django.urls import include, path
from rest_framework_nested import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("PushNotification", views.PushNotificationView, basename="queued-push")

# View patterns
urlpatterns = [
    path("", include(router.urls)),
    path(
        "sqs-monitoring/",
        views.SQSMonitoringView.as_view(),
        name="sqs-monitoring",
    ),
    path(
        "sqs-test/",
        views.SQSTestView.as_view(),
        name="sqs-test",
    ),
]
