from django.urls import path

from core.routing import crud_patterns
from . import views

app_name = "users_teams"

# Les routes réelles sont déclarées avant ``crud_patterns`` : les URL
# /users/users/... remplacent donc les pages placeholder de l'entité « users ».
urlpatterns = [
    # Authentification
    path("connexion/", views.LoginView.as_view(), name="login"),
    path("deconnexion/", views.LogoutView.as_view(), name="logout"),
    path("inscription/", views.RegisterView.as_view(), name="register"),
    path("mot-de-passe-oublie/", views.PasswordForgottenView.as_view(), name="password_forgotten"),
    # L'espace de gestion « home » (/users/) est fourni par crud_patterns
    # via views.module_home (admin, directeur, organisateur).
    # CRUD Utilisateur (administrateur)
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/nouveau/", views.UserCreateView.as_view(), name="user_create"),
    path("users/<int:pk>/", views.UserDetailView.as_view(), name="user_detail"),
    path("users/<int:pk>/modifier/", views.UserUpdateView.as_view(), name="user_update"),
    path("users/<int:pk>/supprimer/", views.UserDeleteView.as_view(), name="user_delete"),
    # Organisateurs d'événements et préférences (équipe d'organisation)
    path("organisateurs/", views.OrganizersView.as_view(), name="organizers"),
    path("profil/", views.ProfileView.as_view(), name="profile"),
    path("parametres/", views.SettingsView.as_view(), name="settings"),
    # Autres entités du module : encore en placeholder
    *crud_patterns(views),
]
