"""Contrôle d'accès du Module 1.

- Visiteur (anonyme) : redirigé vers la connexion.
- Utilisateur connecté sans le rôle requis : erreur 403.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class AdministratorRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Réservé au rôle Administrateur (CRUD utilisateurs)."""

    def test_func(self):
        return self.request.user.is_administrator


class ManagementAccessRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Administrateur, Directeur ou Organisateur (espace de gestion)."""

    def test_func(self):
        return self.request.user.has_management_access
