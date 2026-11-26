from django.urls import path
from core.routing import crud_patterns
from . import views

app_name = "events_program"
urlpatterns = [
    path("geocodage/", views.geocode_location, name="geocode"),
    path("calendrier/evenements/", views.calendar_events, name="calendar_events"),
    *crud_patterns(views),
]
