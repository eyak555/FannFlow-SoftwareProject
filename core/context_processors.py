from urllib.parse import urlencode

from django.urls import reverse

from core.access import can_access_backoffice, is_backoffice_match
from core.registry import get_modules

# Pour un participant, certains modules ont un équivalent côté site public.
PARTICIPANT_DESTINATIONS = {
    "events_program": "core:events",
    "registration_access": "registration_access:home",
}


def _module_link(module, user):
    """Lien d'une carte module selon le profil du visiteur."""
    target = reverse(f"{module['app_name']}:home")
    if can_access_backoffice(user):
        return target, False
    if not user.is_authenticated:
        return f"{reverse('users_teams:login')}?{urlencode({'next': target})}", False
    destination = PARTICIPANT_DESTINATIONS.get(module["app_name"])
    if destination:
        return reverse(destination), False
    return "", True


def navigation(request):
    user = request.user
    modules = []
    for module in get_modules():
        href, locked = _module_link(module, user)
        modules.append({**module, "href": href, "locked": locked})

    match = request.resolver_match
    is_backoffice = is_backoffice_match(match) and can_access_backoffice(user)
    namespace = getattr(match, "namespace", "")
    current_module = next((m for m in modules if m["app_name"] == namespace), None)

    # Cloche du back-office : notifications d'administration des comptes.
    topbar_notifications = None
    if is_backoffice and getattr(user, "is_administrator", False):
        from users_teams.services import admin_notifications

        topbar_notifications = admin_notifications()
    # Fenêtre « Mon profil » du site public (formulaires non liés, sans requête).
    account_forms = None
    if user.is_authenticated and not is_backoffice:
        from django.utils.functional import SimpleLazyObject

        from users_teams.forms import PasswordSettingsForm, ProfileForm
        from users_teams.services import self_deletion_blocker

        account_forms = {
            "profile": ProfileForm(instance=user),
            "password": PasswordSettingsForm(user),
            "tab": "profile",
            "deletion_blocker": SimpleLazyObject(lambda: self_deletion_blocker(user)),
        }
    return {
        "account_forms": account_forms,
        "topbar_notifications": topbar_notifications,
        "current_module_title": current_module["title"] if current_module else "Tableau de bord",
        "fannflow_modules": modules,
        "is_backoffice": is_backoffice,
        "can_access_backoffice": can_access_backoffice(user),
        "current_namespace": getattr(match, "namespace", ""),
        "current_url_name": getattr(match, "url_name", ""),
    }
