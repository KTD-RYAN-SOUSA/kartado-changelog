from django.urls import include, path
from rest_framework import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register(
    "OccurrenceRecordFile",
    views.OccurrenceRecordFileView,
    basename="occurrence-file",
)
router.register("File", views.FileView, basename="file-view")

# View patterns
urlpatterns = [
    path("", include(router.urls)),
    path(
        "FileDownload/<str:file_download_pk>",
        views.FileDownloadView.as_view(),
    ),
]
