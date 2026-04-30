from django.urls import include, path
from rest_framework_nested import routers

from .views import ConstructionProgressViewSet, ConstructionViewSet

# Create router
router = routers.SimpleRouter()

# Define route
router.register("Construction", ConstructionViewSet, basename="construction_view")
router.register(
    "ConstructionProgress",
    ConstructionProgressViewSet,
    basename="construction_progress_view",
)

# View patterns
urlpatterns = [path("", include(router.urls))]
