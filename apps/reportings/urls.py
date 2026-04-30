from django.urls import include, path
from rest_framework_nested import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("Reporting", views.ReportingView, basename="reporting-list")
router.register(
    "DashboardReporting",
    views.DashboardReportingView,
    basename="dashboard-reporting-list",
)
router.register("Inventory", views.InventoryView, basename="inventory-list")
router.register("ReportingFile", views.ReportingFileView, basename="reporting-files")
router.register("ReportingGeo", views.ReportingGeoView, basename="reporting-geo")
router.register(
    "ReportingGisIntegration",
    views.ReportingGisIntegrationView,
    basename="reporting-gis-integration",
)
router.register(
    "InventoryGisIntegration",
    views.InventoryGisIntegrationView,
    basename="inventory-gis-integration",
)
router.register(
    "ReportingMessage",
    views.ReportingMessageView,
    basename="reporting-message",
)
router.register(
    "ReportingMessageReadReceipt",
    views.ReportingMessageReadReceiptView,
    basename="reporting-message-read-receipts",
)
router.register(
    "RecordMenu",
    views.RecordMenuView,
    basename="reporting-record-menu",
)
router.register(
    "ReportingRelation", views.ReportingRelationView, basename="reporting-relation"
)

router.register(
    "ReportingInReporting",
    views.ReportingInReportingView,
    basename="reporting-in-reporting",
)
router.register(
    "ReportingWithInventoryCandidates",
    views.ReportingWithInventoryCandidatesView,
    basename="reporting-with-inventory-candidates",
)

# View patterns
urlpatterns = [path("", include(router.urls))]
