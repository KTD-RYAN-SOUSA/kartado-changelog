from django.urls import include, path
from rest_framework import routers

from . import views

router = routers.SimpleRouter()
router.register("SqlChatMessage", views.SqlChatMessageView, basename="sql-chat-message")

urlpatterns = [path("", include(router.urls))]
