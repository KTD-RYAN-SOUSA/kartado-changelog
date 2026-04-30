from django.urls import include, path
from rest_framework import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register(
    "ServiceOrderActionStatus",
    views.ServiceOrderActionStatusView,
    basename="service-order-statuses",
)
router.register(
    "ServiceOrderActionStatusSpecs",
    views.ServiceOrderActionStatusSpecsView,
    basename="service-order-statuses",
)
router.register("ServiceOrder", views.ServiceOrderView, basename="service-order-view")
router.register(
    "ServiceOrderAction",
    views.ServiceOrderActionView,
    basename="service-order-action-view",
)
router.register("Procedure", views.ProcedureView, basename="service-order-procedure")
router.register(
    "ProcedureFile",
    views.ProcedureFileView,
    basename="service-order-procedure-files",
)
router.register(
    "ProcedureResource",
    views.ProcedureResourceView,
    basename="service-order-procedure-resources",
)
router.register(
    "ServiceOrderResource",
    views.ServiceOrderResourceView,
    basename="service-order-resources",
)
router.register(
    "MeasurementBulletin",
    views.MeasurementBulletinView,
    basename="service-order-measurement-bulletin",
)
router.register(
    "AdministrativeInformation",
    views.AdministrativeInformationView,
    basename="service-order-administrative-information",
)
router.register(
    "ServiceOrderWatcher",
    views.ServiceOrderWatcherView,
    basename="service-order-watcher",
)
router.register(
    "AdditionalControl",
    views.AdditionalControlView,
    basename="service-order-additional-control",
)
router.register(
    "PendingProceduresExport",
    views.PendingProceduresExportView,
    basename="service-order-pending-procedures-export",
)

# View patterns
urlpatterns = [path("", include(router.urls))]
