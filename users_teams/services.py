"""Statistiques et journal du Module 1 — lus en base, jamais inventés."""

from datetime import date, datetime

from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.urls import reverse
from django.utils import timezone

from .models import AccountActivity, User

MONTHS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

# Couleurs : catégorielles pour les rôles (ordre fixe), statut pour actif/inactif.
ROLE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6"]
STATUS_ACTIVE_COLOR = "#2f8a4c"
STATUS_INACTIVE_COLOR = "#9aa5b1"


# --- Journal --------------------------------------------------------------------


def log_activity(action, target, actor=None, details=""):
    return AccountActivity.objects.create(
        action=action,
        actor=actor if actor is not None and actor.is_authenticated else None,
        target=target if target is not None and target.pk else None,
        target_label=str(target),
        details=details[:255],
    )


def log_account_changes(before, after, actor):
    """Compare un compte avant/après modification et journalise ce qui a changé."""
    logged = []
    if before["role"] != after.role or before["business_role"] != after.business_role:
        old = before["business_role_label"] or before["role_label"]
        new = after.get_business_role_display() or after.get_role_display()
        logged.append(log_activity(AccountActivity.Action.ROLE_CHANGED, after, actor, f"{old} → {new}"))
    if before["status"] != after.status:
        action = AccountActivity.Action.ACTIVATED if after.status == User.Status.ACTIVE else AccountActivity.Action.DEACTIVATED
        logged.append(log_activity(action, after, actor))
    if not logged:
        logged.append(log_activity(AccountActivity.Action.UPDATED, after, actor))
    return logged


def snapshot(user):
    return {
        "role": user.role,
        "role_label": user.get_role_display(),
        "business_role": user.business_role,
        "business_role_label": user.get_business_role_display() if user.business_role else "",
        "status": user.status,
    }


ACTION_STYLE = {
    "created": ("user-plus", "teal"),
    AccountActivity.Action.UPDATED: ("pencil", "blue"),
    AccountActivity.Action.PROFILE_UPDATED: ("user-pen", "blue"),
    AccountActivity.Action.ROLE_CHANGED: ("shield", "orange"),
    AccountActivity.Action.ACTIVATED: ("user-check", "green"),
    AccountActivity.Action.DEACTIVATED: ("user-x", "red"),
    AccountActivity.Action.DELETED: ("trash-2", "red"),
}


def recent_activity(limit=8):
    """Créations de comptes (``created_at``) + opérations journalisées."""
    items = []
    for account in User.objects.order_by("-created_at")[:limit]:
        icon, tone = ACTION_STYLE["created"]
        items.append({
            "label": "Nouveau compte",
            "icon": icon, "tone": tone,
            "target": str(account),
            "url": reverse("users_teams:user_detail", args=[account.pk]),
            "details": account.get_business_role_display() or account.get_role_display(),
            "actor": "",
            "when": account.created_at,
        })
    for entry in AccountActivity.objects.select_related("actor", "target")[:limit]:
        icon, tone = ACTION_STYLE.get(entry.action, ("activity", "blue"))
        items.append({
            "label": entry.get_action_display(),
            "icon": icon, "tone": tone,
            "target": entry.target_label,
            "url": reverse("users_teams:user_detail", args=[entry.target_id]) if entry.target_id else "",
            "details": entry.details,
            "actor": str(entry.actor) if entry.actor else "",
            "when": entry.created_at,
        })
    items.sort(key=lambda item: item["when"], reverse=True)
    return items[:limit]


# --- Statistiques ---------------------------------------------------------------


def _month_starts(count):
    today = timezone.localdate()
    year, month = today.year, today.month
    months = []
    for _ in range(count):
        months.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


def account_evolution(months=12):
    starts = _month_starts(months)
    first = timezone.make_aware(datetime(starts[0].year, starts[0].month, 1))
    rows = (
        User.objects.filter(created_at__gte=first)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Count("pk"))
    )
    totals = {}
    for row in rows:
        month = row["month"]
        if timezone.is_aware(month):
            month = timezone.localtime(month)
        totals[(month.year, month.month)] = row["total"]
    return [
        {"label": f"{MONTHS_FR[s.month - 1]} {str(s.year)[2:]}", "value": totals.get((s.year, s.month), 0)}
        for s in starts
    ]


def _counts():
    today = timezone.localdate()
    month_start = timezone.make_aware(datetime(today.year, today.month, 1))
    return User.objects.aggregate(
        total=Count("pk"),
        admins=Count("pk", filter=Q(role=User.Role.ADMIN)),
        directors=Count("pk", filter=Q(business_role=User.BusinessRole.DIRECTOR)),
        organizers=Count("pk", filter=Q(business_role=User.BusinessRole.ORGANIZER)),
        sponsor_managers=Count(
            "pk", filter=Q(business_role=User.BusinessRole.SPONSOR_MANAGER)
        ),
        active=Count("pk", filter=Q(status=User.Status.ACTIVE)),
        new_this_month=Count("pk", filter=Q(created_at__gte=month_start)),
        never_logged=Count("pk", filter=Q(last_login__isnull=True, status=User.Status.ACTIVE)),
    )


def _notifications(counts):
    users_url = reverse("users_teams:user_list")
    inactive = counts["total"] - counts["active"]
    notifications = []
    if inactive:
        notifications.append({"icon": "user-x", "tone": "red", "title": f"{inactive} compte(s) inactif(s)",
                              "text": "Ces utilisateurs ne peuvent pas se connecter.",
                              "url": f"{users_url}?status={User.Status.INACTIVE}"})
    if counts["never_logged"]:
        notifications.append({"icon": "clock", "tone": "orange", "title": f"{counts['never_logged']} compte(s) jamais connecté(s)",
                              "text": "Comptes actifs sans aucune connexion.",
                              "url": f"{users_url}?connexion=never"})
    if counts["new_this_month"]:
        notifications.append({"icon": "user-plus", "tone": "teal", "title": f"{counts['new_this_month']} nouveau(x) compte(s) ce mois-ci",
                              "text": "Créés depuis le 1er du mois.",
                              "url": f"{users_url}?sort=-created_at"})
    return notifications


def admin_dashboard():
    counts = _counts()
    total = counts["total"] or 0
    team = counts["directors"] + counts["organizers"] + counts["sponsor_managers"]
    inactive = total - counts["active"]
    # Un administrateur avec rôle métier est compté une seule fois, comme administrateur.
    participants = User.objects.filter(role=User.Role.PARTICIPANT, business_role="").count()
    team_non_admin_directors = User.objects.filter(role=User.Role.PARTICIPANT, business_role=User.BusinessRole.DIRECTOR).count()
    team_non_admin_organizers = User.objects.filter(role=User.Role.PARTICIPANT, business_role=User.BusinessRole.ORGANIZER).count()
    team_non_admin_sponsor_managers = User.objects.filter(
        role=User.Role.PARTICIPANT,
        business_role=User.BusinessRole.SPONSOR_MANAGER,
    ).count()

    def pct(value):
        return round(value * 100 / total) if total else 0

    users_url = reverse("users_teams:user_list")
    kpis = [
        {"label": "Total utilisateurs", "value": total, "icon": "users", "tone": "blue",
         "hint": f"+{counts['new_this_month']} ce mois-ci", "trend": "up" if counts["new_this_month"] else "flat",
         "url": users_url},
        {"label": "Administrateurs", "value": counts["admins"], "icon": "shield-check", "tone": "orange",
         "hint": f"{pct(counts['admins'])} % des comptes", "progress": pct(counts["admins"]),
         "url": f"{users_url}?role={User.Role.ADMIN}"},
        {"label": "Équipe de gestion", "value": team, "icon": "briefcase", "tone": "teal",
         "hint": f"{counts['directors']} directeur(s) · {counts['organizers']} organisateur(s) · {counts['sponsor_managers']} responsable(s) sponsors", "progress": pct(team),
         "url": reverse("users_teams:organizers")},
        {"label": "Comptes actifs", "value": counts["active"], "icon": "user-check", "tone": "green",
         "hint": f"{pct(counts['active'])} % actifs · {inactive} inactif(s)", "progress": pct(counts["active"]),
         "url": f"{users_url}?status={User.Status.ACTIVE}"},
    ]
    return {
        "kpis": kpis,
        "notifications": _notifications(counts),
        "activities": recent_activity(8),
        "charts": {
            "roles": [
                {"label": "Administrateurs", "value": counts["admins"], "color": ROLE_COLORS[0]},
                {"label": "Directeurs", "value": team_non_admin_directors, "color": ROLE_COLORS[1]},
                {"label": "Organisateurs", "value": team_non_admin_organizers, "color": ROLE_COLORS[2]},
                {"label": "Responsables Sponsors", "value": team_non_admin_sponsor_managers, "color": ROLE_COLORS[3]},
                {"label": "Participants", "value": participants, "color": ROLE_COLORS[4]},
            ],
            "status": [
                {"label": "Actifs", "value": counts["active"], "color": STATUS_ACTIVE_COLOR},
                {"label": "Inactifs", "value": inactive, "color": STATUS_INACTIVE_COLOR},
            ],
            "evolution": account_evolution(12),
        },
    }


def admin_notifications():
    """Version légère pour la cloche de la barre supérieure."""
    return _notifications(_counts())


# --- Organisateurs d'événements -------------------------------------------------


def event_assignments():
    """Affectations par membre d'équipe, si le Module 2 fournit ``Event``.

    Renvoie ``None`` tant que le modèle n'existe pas (intégration préparée).
    """
    from core.services import optional_model

    Event = optional_model("events_program", "Event")
    if Event is None:
        return None
    field = next(
        (f for f in Event._meta.get_fields()
         if getattr(f, "related_model", None) is User and f.name in ("director", "organizer", "director_id", "owner")),
        None,
    )
    if field is None:
        return {}
    assignments = {}
    for event in Event.objects.exclude(**{f"{field.name}__isnull": True}).order_by("-pk")[:500]:
        assignments.setdefault(getattr(event, f"{field.name}_id"), []).append(event)
    return assignments




# --- Suppression du compte par son titulaire -----------------------------------


def self_deletion_blocker(user):
    """Raison qui empêche l'utilisateur de supprimer son propre compte, ou ``""``."""
    if user.is_administrator and not User.objects.filter(
        role=User.Role.ADMIN, status=User.Status.ACTIVE
    ).exclude(pk=user.pk).exists():
        return "Vous êtes le dernier administrateur actif : désignez un autre administrateur avant de supprimer votre compte."
    from core.services import optional_model

    Attendance = optional_model("registration_access", "Attendance")
    if Attendance is not None and Attendance.objects.filter(ticket__registration__user=user).exists():
        return ("Votre compte est lié à des entrées déjà enregistrées lors d’événements "
                "et ne peut pas être supprimé automatiquement. Contactez un administrateur.")
    return ""


def delete_own_account(user):
    """Supprime le compte et ses inscriptions. Renvoie un message d'erreur ou ``""``.

    Les présences enregistrées à l'entrée d'un événement sont protégées
    (historique de contrôle d'accès) : dans ce cas la suppression est refusée.
    """
    from django.db import transaction
    from django.db.models import ProtectedError

    blocker = self_deletion_blocker(user)
    if blocker:
        return blocker
    picture = user.profile_picture
    label = str(user)
    try:
        with transaction.atomic():
            AccountActivity.objects.create(
                action=AccountActivity.Action.DELETED, target_label=label,
                details="Suppression par l’utilisateur lui-même",
            )
            user.delete()
    except ProtectedError:
        return ("Votre compte est lié à des entrées déjà enregistrées lors d’événements "
                "et ne peut pas être supprimé automatiquement. Contactez un administrateur.")
    if picture:
        picture.delete(save=False)
    return ""
