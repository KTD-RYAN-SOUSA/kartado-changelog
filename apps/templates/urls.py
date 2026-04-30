from django.urls import include, path
from rest_framework import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("Template", views.TemplateView, basename="template")
router.register("CanvasList", views.CanvasListView, basename="canvas-list")
router.register("CanvasCard", views.CanvasCardView, basename="canvas-card")
router.register("AppVersion", views.AppVersionView, basename="app-version")
router.register("MobileSync", views.MobileSyncView, basename="mobile-sync")
router.register("ActionLog", views.ActionLogView, basename="action-log")
router.register("ExportRequest", views.ExportRequestView, basename="export-request")
router.register("SearchTag", views.SearchTagView, basename="search-tag")
router.register("ExcelImport", views.ExcelImportView, basename="excel-import")
router.register("ExcelReporting", views.ExcelReportingView, basename="excel-reporting")
router.register("PDFImport", views.PDFImportView, basename="pdf-import")
router.register("CSVImport", views.CSVImportView, basename="csv-import")
router.register(
    "ReportingExport", views.ReportingExportView, basename="reporting-export"
)
router.register(
    "ExcelDnitReport", views.ExcelDnitReportView, basename="excel-dnit-report"
)
router.register("PhotoReport", views.PhotoReportView, basename="photo-report")

# View patterns
urlpatterns = [
    path("", include(router.urls)),
    path("Log/", views.LogView.as_view()),
]
