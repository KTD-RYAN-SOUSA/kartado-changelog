from django.urls import include, path
from rest_framework import routers

from . import views

router = routers.SimpleRouter()
router.register("BIMModel", views.BIMModelViewSet, basename="bimmodel")

urlpatterns = [
    path("", include(router.urls)),
]
