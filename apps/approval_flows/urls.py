from django.urls import include, path
from rest_framework_nested import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("ApprovalFlow", views.ApprovalFlowView, basename="approval-flow")
router.register("ApprovalStep", views.ApprovalStepView, basename="approval-step")
router.register(
    "ApprovalTransition",
    views.ApprovalTransitionView,
    basename="approval-transition",
)


# View patterns
urlpatterns = [
    path("", include(router.urls)),
    path("ApprovalFlowNotifications/", views.ApprovalFlowNotifications.as_view()),
    path(
        "CheckNotificationAvailability/",
        views.CheckNotificationAvailability.as_view(),
    ),
]
