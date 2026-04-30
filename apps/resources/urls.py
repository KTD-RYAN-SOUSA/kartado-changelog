from django.urls import include, path
from rest_framework import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("Resource", views.ResourceViewSet, basename="resource-view")
router.register("Contract", views.ContractView, basename="contract-view")
router.register("HumanResource", views.HumanResourceView, basename="human-resource")
router.register(
    "HumanResourceItem",
    views.HumanResourceItemView,
    basename="human-resource-item",
)
router.register(
    "HumanResourceUsage",
    views.HumanResourceUsageView,
    basename="human-resource-usage",
)
router.register(
    "ContractService", views.ContractServiceView, basename="contract-service"
)
router.register(
    "ContractItemUnitPrice",
    views.ContractItemUnitPriceView,
    basename="contract-item-unit-price",
)
router.register(
    "ContractItemAdministration",
    views.ContractItemAdministrationView,
    basename="contract-item-administration",
)
router.register(
    "ContractItemPerformance",
    views.ContractItemPerformanceView,
    basename="contract-item-performance",
)

router.register(
    "MeasurementBulletinExport",
    views.MeasurementBulletinExportViewSet,
    basename="measurement-bulletin-export",
)
router.register(
    "FieldSurveyRoad", views.FieldSurveyRoadView, basename="field-survey-road"
)
router.register("FieldSurvey", views.FieldSurveyView, basename="field-survey")
router.register(
    "FieldSurveySignature",
    views.FieldSurveySignatureView,
    basename="field-survey-signature",
)
router.register(
    "FieldSurveyExport",
    views.FieldSurveyExportView,
    basename="field-survey-export",
)

router.register(
    "ContractAdditive", views.ContractAdditiveViewSet, basename="contract-additive"
)
router.register(
    "ContractPeriod", views.ContractPeriodViewSet, basename="contract-period"
)
# View patterns
urlpatterns = [path("", include(router.urls))]
