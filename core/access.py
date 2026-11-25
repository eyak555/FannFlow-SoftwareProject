"""Séparation front-office / back-office.

- Front-office (site public) : accueil, catalogue des événements, espace
  participant. Accessible aux visiteurs et aux participants.
- Back-office (espace de gestion) : toutes les pages des modules métier.
  Réservé aux administrateurs, directeurs et organisateurs
  (``User.has_management_access``).

Le contrôle est centralisé ici pour que chaque module reste inchangé :
un module n'a rien à déclarer pour être protégé.
"""

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

# Espaces de noms d'URL qui appartiennent au back-office.
BACKOFFICE_NAMESPACES = {
    "users_teams",
    "events_program",
    "registration_access",
    "resources_operations",
    "sponsors_finance",
    "communication_media",
}

# Pages de ces espaces qui restent publiques (authentification).
PUBLIC_URL_NAMES = {
    ("users_teams", "login"),
    ("users_teams", "logout"),
    ("users_teams", "register"),
    ("users_teams", "password_forgotten"),
}

# Pages de modules destinées aussi aux participants : connexion requise,
# puis chaque vue applique ses propres règles (ex. Registration & Access :
# un participant ne voit que ses inscriptions et ses billets).
PARTICIPANT_URL_NAMES = {
    ("registration_access", "home"),
    ("registration_access", "my_registrations"),
    ("registration_access", "registration_request"),
    ("registration_access", "registration_cancel"),
    ("registration_access", "registration_confirm"),
    ("registration_access", "my_tickets"),
    ("registration_access", "my_ticket_detail"),
}


def is_participant_page(match):
    return match is not None and (match.namespace, match.url_name) in PARTICIPANT_URL_NAMES


def is_backoffice_match(match):
    if match is None or match.namespace not in BACKOFFICE_NAMESPACES:
        return False
    return (match.namespace, match.url_name) not in PUBLIC_URL_NAMES


def can_access_backoffice(user):
    return bool(user and user.is_authenticated and getattr(user, "has_management_access", False))


class BackOfficeAccessMiddleware:
    """Visiteur → connexion ; participant → 403 ; équipe → accès."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not is_backoffice_match(request.resolver_match):
            return None
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if is_participant_page(request.resolver_match):
            return None
        if not can_access_backoffice(request.user):
            raise PermissionDenied("Espace réservé à l’équipe d’organisation.")
        return None
