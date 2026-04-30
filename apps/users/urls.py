from django.urls import include, path
from rest_framework import routers

from . import views

# DRF Routers
router = routers.SimpleRouter()
router.register("User", views.UserViewSet, basename="users-view")
router.register(
    "ListCompanies", views.ListCompaniesViewSet, basename="listcompanies-view"
)
router.register(
    "UserNotification",
    views.UserNotificationView,
    basename="user-notification-view",
)

router.register("UserSignature", views.UserSignatureView, basename="users-signatures")

# View patterns
urlpatterns = [
    path("", include(router.urls)),
    path("CheckGid/", views.CheckGidView.as_view()),
    path("CheckEmail/", views.CheckEmailView.as_view()),
    path(
        "ResetPassword/",
        views.ResetPasswordRequestTokenCustom.as_view(),
    ),
    path("ConfirmPassword/", views.ResetPasswordConfirmCustom.as_view()),
    path("IsNewPasswordValid/", views.IsNewPasswordValid.as_view()),
]
