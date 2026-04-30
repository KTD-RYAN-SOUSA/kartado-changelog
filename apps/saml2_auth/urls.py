from django.urls import re_path

from . import views

urlpatterns = [
    re_path(r"^acs/$", views.acs, name="acs"),
    # re_path(r'^welcome/$', views.welcome, name="welcome"),
    re_path(r"^denied/$", views.denied, name="denied"),
    re_path(r"^login/$", views.signin, name="signin"),
]
