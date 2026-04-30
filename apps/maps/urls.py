from django.urls import include, path
from rest_framework import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("TileLayer", views.TileLayerViewSet, basename="tilelayer-view")
router.register("ShapeFile", views.ShapeFileViewSet, basename="shapefile-view")
router.register(
    "ShapeFileProperty",
    views.ShapeFilePropertyViewSet,
    basename="shapefileproperty-view",
)

# View patterns
urlpatterns = [
    path("", include(router.urls)),
    path("EcmSearch/", views.EcmSearchView.as_view()),
    path("EcmDownload/", views.EcmDownloadView.as_view()),
    path("EcmCheckPermission/", views.EcmCheckPermissionView.as_view()),
    path("EngieSearch/", views.EngieSearchView.as_view()),
]
