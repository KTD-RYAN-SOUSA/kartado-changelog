from django.urls import include, path
from rest_framework import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("FormsIARequest", views.FormsIARequestView, basename="forms-ia-request")

# View patterns
urlpatterns = [path("", include(router.urls))]
