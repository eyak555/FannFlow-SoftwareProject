from django.urls import path

from core.routing import crud_patterns
from . import views

app_name = "users_teams"

urlpatterns = [
    path("connexion/", views.login_placeholder, name="login"),
    *crud_patterns(views),
]
