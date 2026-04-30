from django.urls import include, path
from rest_framework import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("Service", views.ServiceView, basename="service-view")
router.register("ServiceSpecs", views.ServiceSpecsView, basename="servicespecs-view")
router.register("Measurement", views.MeasurementView, basename="measurement-view")
router.register("ServiceUsage", views.ServiceUsageView, basename="serviceusage-view")
router.register("Goal", views.GoalView, basename="goal-view")
router.register(
    "GoalAggregate", views.GoalAggregateView, basename="goal-aggregate-view"
)
router.register(
    "MeasurementService",
    views.MeasurementServiceView,
    basename="measurementservice-view",
)

# View patterns
urlpatterns = [path("", include(router.urls))]
