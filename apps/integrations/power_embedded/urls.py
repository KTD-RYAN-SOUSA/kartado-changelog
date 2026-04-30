from django.urls import path

from .views import EmbedUrlView, EnsureUserView, ReportListView

urlpatterns = [
    path(
        "PowerEmbedded/Reports/",
        ReportListView.as_view(),
        name="power-embedded-reports",
    ),
    path(
        "PowerEmbedded/Reports/<uuid:report_id>/EmbedUrl/",
        EmbedUrlView.as_view(),
        name="power-embedded-embed-url",
    ),
    path(
        "PowerEmbedded/Users/Ensure/",
        EnsureUserView.as_view(),
        name="power-embedded-ensure-user",
    ),
]
