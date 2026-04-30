from django.urls import include, path
from rest_framework import routers

from . import views

router = routers.SimpleRouter()
router.register("MLPrediction", views.MLPredictionViewSet, basename="ml-prediction")

urlpatterns = [path("", include(router.urls))]
