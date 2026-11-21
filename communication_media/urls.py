from django.urls import path
from core.routing import crud_patterns
from . import views

app_name = "communication_media"
urlpatterns = crud_patterns(views)
