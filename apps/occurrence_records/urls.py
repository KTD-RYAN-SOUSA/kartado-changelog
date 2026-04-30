from django.urls import include, path
from rest_framework_nested import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("OccurrenceType", views.OccurrenceTypeView, basename="occurrence-types")
router.register("ParameterGroup", views.ParameterGroupView, basename="parameter-groups")
router.register(
    "OccurrenceRecord", views.OccurrenceRecordView, basename="occurrence-list"
)
router.register(
    "AdditionalDocument",
    views.AdditionalDocumentView,
    basename="additional-document-list",
)
router.register(
    "OccurrenceTypeSpecs",
    views.OccurrenceTypeSpecsView,
    basename="occurrence-type-specs",
)
router.register(
    "OccurrenceRecordGeo",
    views.OccurrenceRecordGeoView,
    basename="occurrence-geo",
)
router.register(
    "OccurrenceRecordWatcher",
    views.OccurrenceRecordWatcherView,
    basename="occurrence-watcher",
)
router.register("RecordPanel", views.RecordPanelView, basename="record-panel")
router.register(
    "CustomDashboard", views.CustomDashboardView, basename="custom-dashboard"
)
router.register("DataSeries", views.DataSeriesView, basename="data-series")
router.register("CustomTable", views.CustomTableView, basename="custom-table")
router.register(
    "TableDataSeries", views.TableDataSeriesView, basename="table-data-series"
)
router.register("InstrumentMap", views.InstrumentMapView, basename="instrument-map")
router.register(
    "SIHMonitoringPointMap",
    views.SIHMonitoringPointMapView,
    basename="sih-monitoring-point-map",
)
router.register("InstrumentMap", views.InstrumentMapView, basename="instrument-map")

# View patterns
urlpatterns = [
    path("", include(router.urls)),
    path(
        "OccurrenceRecord/<str:occurrence_record_pk>/pdf-notificacao-escrita/",
        views.ReportOccurrenceRecordWrittenNotificationPDFView.as_view(),
        name="written_notification",
    ),
]
