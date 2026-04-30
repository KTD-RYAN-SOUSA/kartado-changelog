from django.urls import path

from . import views

# View patterns
urlpatterns = [
    path("dashboard/ResourceHistory/", views.ResourceHistoryView.as_view()),
    path("dashboard/RecordStatus/", views.RecordStatusView.as_view()),
    path("dashboard/ProcedureStatus/", views.ProcedureStatusView.as_view()),
    path("dashboard/Top5RecordLocal/", views.Top5RecordLocalView.as_view()),
    path("dashboard/RecordNature/", views.RecordNatureView.as_view()),
    path("dashboard/RecordTypes/", views.RecordTypesView.as_view()),
    path("dashboard/ActionStatus/", views.ActionStatusView.as_view()),
    path("dashboard/ServiceOrderCost/", views.ServiceOrderCostView.as_view()),
    path("dashboard/ContractCost/", views.ContractCostView.as_view()),
    path("dashboard/ActionCount/", views.ActionCountView.as_view()),
    path("dashboard/FirmPerformance/", views.FirmPerformanceView.as_view()),
    path("dashboard/Resources/", views.ResourcesView.as_view()),
    path("dashboard/ReportingSLA/", views.ReportingSLAView.as_view()),
    path(
        "dashboard/ReportingRecentlyExecuted/",
        views.ReportingRecentlyExecutedView.as_view(),
    ),
    path(
        "dashboard/MeasurementBulletins/",
        views.MeasurementBulletinsView.as_view(),
    ),
    path("dashboard/ReportingStats/", views.ReportingStatsView.as_view()),
    path(
        "dashboard/UniqueMeasurementBulletins/",
        views.UniqueMeasurementBulletinsView.as_view(),
    ),
    path(
        "dashboard/ContractSpendSchedule/",
        views.ContractSpendScheduleView.as_view(),
    ),
    path("dashboard/ReportingCount/", views.ReportingCountView.as_view()),
    path("dashboard/ReportingCountRoad/", views.ReportingCountRoadView.as_view()),
    path("dashboard/RainData/", views.RainDataView.as_view()),
]
