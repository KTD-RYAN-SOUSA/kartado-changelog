from django.urls import path

from .views import wmdb_sync

urlpatterns = [path("WmDBSync/", wmdb_sync)]
