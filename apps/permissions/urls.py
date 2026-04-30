from django.urls import include, path
from rest_framework import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("Permission", views.PermissionView, basename="permission_view")

# View patterns
urlpatterns = [path("", include(router.urls))]
