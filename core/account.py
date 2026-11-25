"""Compte de l'utilisateur connecté, côté site public.

Le profil s'ouvre dans une fenêtre depuis la barre du haut ; ces vues
traitent les formulaires de cette fenêtre. En cas d'erreur, la page
``/mon-profil/`` s'affiche avec les messages, sans perdre la saisie.
"""

from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from users_teams import services
from users_teams.forms import PasswordSettingsForm, ProfileForm
from users_teams.models import AccountActivity


def _next_url(request, default="core:my_space"):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
        return target
    return default


def _render_page(request, tab="profile", profile_form=None, password_form=None, status=200):
    return render(
        request,
        "core/profile.html",
        {
            "page_title": "Mon profil",
            "account_forms": {
                "profile": profile_form or ProfileForm(instance=request.user),
                "password": password_form or PasswordSettingsForm(request.user),
                "tab": tab,
                "deletion_blocker": services.self_deletion_blocker(request.user),
            },
        },
        status=status,
    )


@login_required
def profile(request):
    if request.method != "POST":
        return _render_page(request, tab=request.GET.get("onglet", "profile"))
    form = ProfileForm(request.POST, request.FILES, instance=request.user)
    if not form.is_valid():
        return _render_page(request, "profile", profile_form=form, status=400)
    form.save()
    services.log_activity(AccountActivity.Action.PROFILE_UPDATED, request.user, request.user)
    messages.success(request, "Votre profil a été mis à jour.")
    return redirect(_next_url(request))


@login_required
@require_POST
def password(request):
    form = PasswordSettingsForm(request.user, request.POST)
    if not form.is_valid():
        return _render_page(request, "password", password_form=form, status=400)
    form.save()
    update_session_auth_hash(request, form.user)  # reste connecté
    messages.success(request, "Votre mot de passe a été modifié.")
    return redirect(_next_url(request))


@login_required
def delete_account(request):
    if request.method != "POST":
        return _render_page(request, "delete")
    user = request.user
    if not request.POST.get("confirm"):
        messages.error(request, "Cochez la case de confirmation pour supprimer votre compte.")
        return _render_page(request, "delete", status=400)
    if not user.check_password(request.POST.get("password", "")):
        messages.error(request, "Mot de passe incorrect : votre compte n’a pas été supprimé.")
        return _render_page(request, "delete", status=400)
    error = services.self_deletion_blocker(user)
    if error:
        messages.error(request, error)
        return _render_page(request, "delete", status=400)

    account = user
    logout(request)
    error = services.delete_own_account(account)
    if error:
        messages.error(request, error)
        return redirect("users_teams:login")
    messages.info(request, "Votre compte a été supprimé. Merci d’avoir fait partie de FannFlow.")
    return redirect("core:home")
