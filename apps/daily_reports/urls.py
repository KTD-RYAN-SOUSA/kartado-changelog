from django.urls import include, path
from rest_framework_nested import routers

from .views import (
    DailyReportContractUsageViewSet,
    DailyReportEquipmentViewSet,
    DailyReportExportViewSet,
    DailyReportExternalTeamViewSet,
    DailyReportOccurrenceViewSet,
    DailyReportRelationViewSet,
    DailyReportResourceViewSet,
    DailyReportSignalingViewSet,
    DailyReportVehicleViewSet,
    DailyReportViewSet,
    DailyReportWorkerViewSet,
    MultipleDailyReportFileView,
    MultipleDailyReportSignatureView,
    MultipleDailyReportViewSet,
    ProductionGoalViewSet,
    RecalculateExtraHours,
)

# Create router
router = routers.SimpleRouter()

# Define routes
router.register("DailyReport", DailyReportViewSet, basename="daily_report_view")
router.register(
    "MultipleDailyReport",
    MultipleDailyReportViewSet,
    basename="multiple_daily_report_view",
)
router.register(
    "DailyReportWorker",
    DailyReportWorkerViewSet,
    basename="daily_report_worker_view",
)
router.register(
    "DailyReportRelation",
    DailyReportRelationViewSet,
    basename="daily_report_relation_view",
)
router.register(
    "DailyReportExternalTeam",
    DailyReportExternalTeamViewSet,
    basename="daily_report_external_team_view",
)
router.register(
    "DailyReportEquipment",
    DailyReportEquipmentViewSet,
    basename="daily_report_equipment_view",
)
router.register(
    "DailyReportVehicle",
    DailyReportVehicleViewSet,
    basename="daily_report_vehicle_view",
)
router.register(
    "DailyReportSignaling",
    DailyReportSignalingViewSet,
    basename="daily_report_signaling_view",
)
router.register(
    "DailyReportOccurrence",
    DailyReportOccurrenceViewSet,
    basename="daily_report_occurrence_view",
)
router.register(
    "DailyReportResource",
    DailyReportResourceViewSet,
    basename="daily_report_resource",
)
router.register(
    "ProductionGoal", ProductionGoalViewSet, basename="production_goal_view"
)
router.register(
    "DailyReportExport",
    DailyReportExportViewSet,
    basename="daily_report_export_view",
)
router.register(
    "DailyReportContractUsage",
    DailyReportContractUsageViewSet,
    basename="daily_report_contract_usage_view",
)
router.register(
    "MultipleDailyReportFile",
    MultipleDailyReportFileView,
    basename="multiple_daily_report_file_view",
)

router.register(
    "MultipleDailyReportSignature",
    MultipleDailyReportSignatureView,
    basename="multiple_daily_report_signature_view",
)


# View patterns
urlpatterns = [
    path("", include(router.urls)),
    path("RecalculateExtraHours/", RecalculateExtraHours.as_view()),
]
