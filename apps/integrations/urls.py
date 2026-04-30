from django.urls import include, path
from rest_framework_nested import routers

from .power_embedded import urls as power_embedded_urls
from .views import ContentTypeViewSet, IntegrationConfigViewSet, IntegrationRunViewSet

# Create router
router = routers.SimpleRouter()

# Define routes
router.register(
    "IntegrationConfig",
    IntegrationConfigViewSet,
    basename="integration_config_view",
)
router.register(
    "IntegrationRun", IntegrationRunViewSet, basename="integration_run_view"
)
router.register("ContentType", ContentTypeViewSet, basename="content-type")


# View patterns
urlpatterns = [
    path("", include(router.urls)),
    path("", include(power_embedded_urls.urlpatterns)),
]
