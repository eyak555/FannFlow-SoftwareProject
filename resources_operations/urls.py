from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views
from .forms import OperationsLoginForm

app_name = "resources_operations"
urlpatterns = [
    path("", views.ModuleHomeView.as_view(), name="home"),
    path(
        "connexion/",
        LoginView.as_view(
            authentication_form=OperationsLoginForm,
            template_name="resources_operations/login.html",
            next_page="resources_operations:home",
            extra_context={"page_title": "Connexion à Resources & Operations"},
        ),
        name="login",
    ),
    path("deconnexion/", LogoutView.as_view(next_page="resources_operations:login"), name="logout"),
    path("<slug:entity>/nouveau/", views.EntityCreateView.as_view(), name="entity_create"),
    path("<slug:entity>/<int:pk>/modifier/", views.EntityUpdateView.as_view(), name="entity_update"),
    path("<slug:entity>/<int:pk>/supprimer/", views.EntityDeleteView.as_view(), name="entity_delete"),
    path("<slug:entity>/<int:pk>/", views.EntityDetailView.as_view(), name="entity_detail"),
    path("<slug:entity>/", views.EntityListView.as_view(), name="entity_list"),
]
