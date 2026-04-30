from django.urls import include, path

from .base import urlpatterns

urlpatterns.append(
    # Profiler URLs
    path("silk/", include("silk.urls", namespace="silk"))
)
