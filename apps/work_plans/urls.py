from django.urls import include, path
from rest_framework import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("Job", views.JobViewSet, basename="job")
router.register(
    "NoticeViewManager",
    views.NoticeViewManagerViewSet,
    basename="notice-view-manager",
)
router.register(
    "UserNoticeView", views.UserNoticeViewViewSet, basename="user-notice-view"
)

# View patterns
urlpatterns = [path("", include(router.urls))]
