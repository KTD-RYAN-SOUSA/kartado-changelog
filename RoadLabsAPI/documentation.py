from django.urls import path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

open_api_info = openapi.Info(
    title="RoadLabs API",
    default_version="v1",
    description="RoadLabs Unified Application Backend",
    # terms_of_service="https://www.google.com/policies/terms/",
    contact=openapi.Contact(email="contato@roadlabs.com"),
    # license=openapi.License(name="BSD License"),
)

schema_view = get_schema_view(
    open_api_info,
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path(
        "docs/",
        schema_view.with_ui("swagger", cache_timeout=None),
        name="schema-swagger-ui",
    )
]
