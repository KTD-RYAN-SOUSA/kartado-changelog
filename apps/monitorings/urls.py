from django.urls import include, path
from rest_framework_nested import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("MonitoringPlan", views.MonitoringPlanView, basename="monitoring-plan")
router.register(
    "MonitoringPoint", views.MonitoringPointView, basename="monitoring-point"
)
router.register(
    "MonitoringPointGeo",
    views.MonitoringPointGeoView,
    basename="monitoring-point-geo",
)
router.register(
    "MonitoringCycle", views.MonitoringCycleView, basename="monitoring-cycle"
)
router.register(
    "MonitoringFrequency",
    views.MonitoringFrequencyView,
    basename="monitoring-frequency",
)
router.register(
    "MonitoringCampaign",
    views.MonitoringCampaignView,
    basename="monitoring-campaign",
)
router.register(
    "MonitoringRecord",
    views.MonitoringRecordView,
    basename="monitoring-record",
)
router.register(
    "MonitoringCollect",
    views.MonitoringCollectView,
    basename="monitoring-collect",
)
router.register(
    "OperationalControl",
    views.OperationalControlView,
    basename="operational-control",
)
router.register(
    "OperationalCycle",
    views.OperationalCycleView,
    basename="operational-cycle",
)
router.register("MaterialItem", views.MaterialItemView, basename="material-item")
router.register("MaterialUsage", views.MaterialUsageView, basename="material-usage")


# View patterns
urlpatterns = [
    path("", include(router.urls)),
    path("MonitoringFullSchedule/", views.MonitoringFullScheduleView.as_view()),
]
