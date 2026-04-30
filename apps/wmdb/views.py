from django.http import response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.companies.models import Company
from apps.reportings.models import Reporting

from .permissions import WmdbPermissions
from .serializers import versions
from .sync import Synchronization


@api_view(["GET"])
@permission_classes([IsAuthenticated, WmdbPermissions])
def wmdb_sync(request):
    """
    View class for Inventory sync used in the app.
    It uses a custom version of the ReportingSerializer to return only the necessary fields
    It builds an pagination resilient type of response to avoid sync errors
    The query_params utilized are:
    - company: UUID of the Company to filter the Inventory items
    - schema_version: InventorySerializer version to use according to what the app is requiring from the database
    - last_pulled_at: timestamp used to only sync items created after a certain date, to avoid syncing all items every time a sync happens
    """
    try:
        last_pulled_at = int(request.query_params.get("lastPulledAt"))
        company = request.query_params.get("company")
        schema_version = int(request.query_params.get("schemaVersion"))
    except Exception:
        return Response("Invalid query params", status.HTTP_400_BAD_REQUEST)

    wmdb_serializers = versions.get_serializer(schema_version)
    if not wmdb_serializers:
        return Response("SchemaVersion not exists", status.HTTP_400_BAD_REQUEST)

    try:
        user_companie = Company.objects.get(uuid=company)
        reporting = Reporting.objects.prefetch_related(
            "occurrence_type", "active_shape_files"
        ).filter(company=user_companie, occurrence_type__occurrence_kind="2")
    except Exception as e:
        return Response(str(e), status.HTTP_400_BAD_REQUEST)

    sync = Synchronization(request, last_pulled_at)
    sync.add_model("inventory", reporting, wmdb_serializers.InventorySerializer)

    return response.JsonResponse(
        {
            "changes": sync.get_changes(),
            "timestamp": sync.get_timestamp(),
            "next_page": sync.next_page,
        }
    )
