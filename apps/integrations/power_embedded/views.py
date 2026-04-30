import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .client import PowerEmbeddedClient
from .helpers import ensure_user_in_pe, get_group_for_company
from .permissions import PowerBiPermissions

logger = logging.getLogger(__name__)


class ReportListView(APIView):
    permission_classes = [IsAuthenticated, PowerBiPermissions]
    permissions = None
    action = "list"

    def get(self, request):
        company_id = request.query_params.get("company")
        client = PowerEmbeddedClient()

        group = get_group_for_company(client, request.user, company_id)
        if not group:
            return Response([])

        group_id = group["id"]
        group_report_ids = set(group.get("reports") or [])

        ensure_user_in_pe(client, request.user, group_id)

        reports_response = client.list_reports()

        reports = [
            {
                "type": "PowerEmbeddedReport",
                "id": report["id"],
                "attributes": {
                    "name": report.get("name", ""),
                    "description": report.get("description"),
                    "workspace_name": report.get("workspaceName", ""),
                },
            }
            for report in reports_response.get("data", [])
            if report["id"] in group_report_ids
        ]

        return Response(reports)


class EmbedUrlView(APIView):
    permission_classes = [IsAuthenticated, PowerBiPermissions]
    permissions = None
    action = "retrieve"

    def get(self, request, report_id):
        company_id = request.query_params.get("company")
        client = PowerEmbeddedClient()

        result = client.generate_embed_url(
            user_email=request.user.email,
            report_id=str(report_id),
            company_id=company_id,
        )

        if not result or not result.get("embedUrl"):
            return Response(
                {"errors": ["Failed to generate embed URL"]},
                status=502,
            )

        return Response(
            {
                "type": "PowerEmbeddedEmbedUrl",
                "id": str(report_id),
                "attributes": {
                    "embed_url": result["embedUrl"],
                    "expires_at": result["expiresAt"],
                },
            }
        )


class EnsureUserView(APIView):
    permission_classes = [IsAuthenticated, PowerBiPermissions]
    permissions = None
    action = "retrieve"

    def post(self, request):
        company_id = request.query_params.get("company")
        client = PowerEmbeddedClient()

        group = get_group_for_company(client, request.user, company_id)
        if not group:
            return Response(
                {"errors": ["No PE group found for this company"]},
                status=404,
            )

        result = ensure_user_in_pe(client, request.user, group["id"])

        return Response(
            {
                "type": "PowerEmbeddedUser",
                "attributes": {
                    "status": result,
                    "user_email": request.user.email,
                    "group_id": group["id"],
                },
            }
        )
