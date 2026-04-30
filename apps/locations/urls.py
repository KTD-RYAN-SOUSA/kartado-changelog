from django.urls import include, path
from rest_framework import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("City", views.CityViewSet, basename="city-view")
router.register("Location", views.LocationViewSet, basename="location-view")
router.register("River", views.RiverViewSet, basename="river-view")

# View patterns
urlpatterns = [path("Location/", include(router.urls))]
