from django.urls import include, path
from rest_framework import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("Company", views.CompanyView, basename="company_view")
router.register("SubCompany", views.SubCompanyView, basename="subcompany_view")
router.register("Firm", views.FirmView, basename="company-firms")
router.register("UserInCompany", views.UserInCompanyView, basename="company-users")
router.register("UserInFirm", views.UserInFirmView, basename="firm-users")
router.register(
    "InspectorInFirm", views.InspectorInFirmView, basename="firm-inspectors"
)
router.register("CompanyGroup", views.CompanyGroupView, basename="company-group")
router.register("AccessRequest", views.AccessRequestView, basename="acess-request")
router.register("Entity", views.EntityView, basename="entity")
router.register("CompanyUsage", views.CompanyUsageView, basename="company-usage")
router.register("UserUsage", views.UserUsageView, basename="user-usage")
router.register(
    "SingleCompanyUsage", views.SingleCompanyUsageView, basename="single-company-usage"
)
router.register(
    "ShareableUserInCompany",
    views.ShareableUserInCompanyView,
    basename="shareable-user-in-company",
)

# View patterns
urlpatterns = [
    path("", include(router.urls)),
    path("AccessRequestApproval/", views.AccessRequestApprovalView.as_view()),
]
