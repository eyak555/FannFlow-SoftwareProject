from django.urls import path

from . import account, views

app_name = "core"

# Front-office : site public et espace participant.
urlpatterns = [
    path("", views.home, name="home"),
    path("evenements/", views.events, name="events"),
    path("evenements/<int:pk>/", views.event_detail, name="event_detail"),
    path("mon-espace/", views.my_space, name="my_space"),
    # Compte de l'utilisateur connecté (fenêtre « Mon profil »)
    path("mon-profil/", account.profile, name="profile"),
    path("mon-profil/mot-de-passe/", account.password, name="password"),
    path("mon-profil/supprimer/", account.delete_account, name="delete_account"),
]
