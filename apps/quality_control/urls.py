from django.urls import include, path
from rest_framework_nested import routers

from .views import (
    ConstructionPlantViewSet,
    QualityAssayViewSet,
    QualityControlExportViewSet,
    QualityProjectViewSet,
    QualitySampleViewSet,
)

# Create router
router = routers.SimpleRouter()

# Define routes
router.register("QualitySample", QualitySampleViewSet, basename="quality_sample_view")
router.register("QualityAssay", QualityAssayViewSet, basename="quality_assay_view")
router.register(
    "QualityProject", QualityProjectViewSet, basename="quality_project_view"
)
router.register(
    "ConstructionPlant",
    ConstructionPlantViewSet,
    basename="construction_plant_view",
)
router.register(
    "QualityControlExport",
    QualityControlExportViewSet,
    basename="quality_control_export_view",
)

# View patterns
urlpatterns = [path("", include(router.urls))]
