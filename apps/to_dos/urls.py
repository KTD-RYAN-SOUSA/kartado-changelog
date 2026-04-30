from django.urls import include, path
from rest_framework_nested import routers

from . import views

# Create router
router = routers.SimpleRouter()

# Define routes
router.register("ToDo", views.ToDoView, basename="to_do_view")
router.register("ToDoAction", views.ToDoActionView, basename="to_do_action_view")

# View patterns
urlpatterns = [path("", include(router.urls))]
