from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django_ses.views import handle_bounce

# DRF Imports
from rest_framework_jwt.views import verify_jwt_token

from apps.approval_flows import urls as approval_flows_urls
from apps.bim import urls as bim_urls
from apps.companies import urls as companies_urls
from apps.constructions import urls as construction_urls
from apps.daily_reports import urls as daily_reports_urls
from apps.dashboard import urls as dashboard_urls
from apps.email_handler import urls as email_handler_urls
from apps.files import urls as files_urls
from apps.forms_ia import urls as forms_ia_urls
from apps.integrations import urls as integrations_urls
from apps.locations import urls as location_urls
from apps.maps import urls as maps_urls
from apps.ml_predictions import urls as ml_predictions_urls
from apps.monitorings import urls as monitorings_urls
from apps.notifications import urls as notifications_urls
from apps.occurrence_records import urls as occurrence_records_urls
from apps.permissions import urls as permissions_urls
from apps.quality_control import urls as quality_control_urls
from apps.reportings import urls as reportings_urls
from apps.resources import urls as resources_urls
from apps.roads import urls as roads_urls
from apps.saml2_auth import urls as saml2_auth_urls
from apps.service_orders import urls as service_orders_urls
from apps.services import urls as services_urls
from apps.sql_chat import urls as sql_chat_urls
from apps.templates import urls as templates_urls
from apps.to_dos import urls as to_dos_urls

# Import routers from apps
from apps.users import urls as users_urls
from apps.wmdb import urls as wmdb_urls
from apps.work_plans import urls as work_plans_urls
from helpers.auth_views import custom_obtain_jwt_token, custom_refresh_jwt_token
from helpers.aws import email_events

from ..documentation import urlpatterns as docs_url_patterns


@csrf_exempt
@never_cache
def health_check(request):
    """
    Health check endpoint for ECS Fargate / ALB monitoring.
    Returns a simple JSON response with status OK.

    Decorators:
    - @csrf_exempt: Bypass CSRF middleware (não precisa de token)
    - @never_cache: Nunca cachear (sempre responder rápido)
    """
    return JsonResponse({"status": "ok", "service": "kartado-backend"})


urlpatterns = [
    # Health check endpoint
    path("health/", health_check, name="health_check"),
    path("saml2/", include(saml2_auth_urls.urlpatterns)),
    path("admin/", admin.site.urls),
    # Token login configuration
    path("token/login/", custom_obtain_jwt_token),
    path("token/refresh/", custom_refresh_jwt_token),
    path("token/verify/", verify_jwt_token),
    # DRF Login Configuration
    path("api-auth/", include("rest_framework.urls")),
    # SES
    path("ses/bounce/", csrf_exempt(handle_bounce)),
    path("EmailEvents/", csrf_exempt(email_events)),
    # Url Patterns
    path("", include(users_urls.urlpatterns)),
    path("", include(companies_urls.urlpatterns)),
    path("", include(occurrence_records_urls.urlpatterns)),
    path("", include(service_orders_urls.urlpatterns)),
    path("", include(location_urls.urlpatterns)),
    path("", include(resources_urls.urlpatterns)),
    path("", include(permissions_urls.urlpatterns)),
    path("", include(work_plans_urls.urlpatterns)),
    path("", include(dashboard_urls.urlpatterns)),
    path("", include(reportings_urls.urlpatterns)),
    path("", include(templates_urls.urlpatterns)),
    path("", include(roads_urls.urlpatterns)),
    path("", include(services_urls.urlpatterns)),
    path("", include(files_urls.urlpatterns)),
    path("", include(monitorings_urls.urlpatterns)),
    path("", include(maps_urls.urlpatterns)),
    path("", include(approval_flows_urls.urlpatterns)),
    path("", include(email_handler_urls.urlpatterns)),
    path("", include(notifications_urls.urlpatterns)),
    path("", include(forms_ia_urls.urlpatterns)),
    path("", include(sql_chat_urls.urlpatterns)),
    path("", include(ml_predictions_urls.urlpatterns)),
    path("", include(wmdb_urls.urlpatterns)),
    path("", include(daily_reports_urls.urlpatterns)),
    path("", include(construction_urls.urlpatterns)),
    path("", include(quality_control_urls.urlpatterns)),
    path("", include(to_dos_urls.urlpatterns)),
    path("", include(integrations_urls.urlpatterns)),
    path("", include(bim_urls.urlpatterns)),
    # Documentation
    path("", include(docs_url_patterns)),
]
