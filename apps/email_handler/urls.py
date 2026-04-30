from django.urls import include, path
from rest_framework_nested import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register(
    "QueuedJudiciaryEmail",
    views.QueuedJudiciaryEmailView,
    basename="queued-judiciary-email",
)

# View patterns
urlpatterns = [path("", include(router.urls))]
