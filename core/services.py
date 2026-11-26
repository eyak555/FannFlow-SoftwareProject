"""Statistiques de la plateforme, lues dans les vraies tables des modules.

Aucune donnée n'est inventée : quand un module n'a pas encore livré son
modèle (Événement, Budget…), la fonction renvoie ``available=False`` et
l'interface affiche un état vide explicite.
"""

import logging
from datetime import date, datetime

from django.apps import apps
from django.db import DatabaseError
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

MONTHS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

PUBLISHED_VALUES = ("published", "publie", "publié", "public")


def optional_model(app_label, model_name):
    """Modèle d'un autre module, ou ``None`` s'il n'existe pas encore."""
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def _field_names(model):
    return {field.name for field in model._meta.get_fields()}


def _display(obj, field):
    getter = getattr(obj, f"get_{field}_display", None)
    if callable(getter):
        return getter()
    value = getattr(obj, field, "")
    return str(value) if value not in (None, "") else ""


def _month_starts(count, today=None):
    today = today or timezone.localdate()
    year, month = today.year, today.month
    months = []
    for _ in range(count):
        months.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


def month_label(value):
    return f"{MONTHS_FR[value.month - 1]} {value.year}"


# --- Événements (Module 2) ---------------------------------------------------


def _event_payload(event, names):
    start = getattr(event, "start_date", None)
    location = ""
    for field in ("venue", "id_venue", "location", "city"):
        if field in names and getattr(event, field, None):
            location = str(getattr(event, field))
            break
    image = ""
    for field in ("image", "cover", "cover_image", "poster", "banner"):
        file = getattr(event, field, None) if field in names else None
        if file:
            try:
                image = file.url
            except ValueError:
                image = ""
            break
    if not image and hasattr(event, "display_image_url"):
        image = event.display_image_url
    url = ""
    if hasattr(event, "get_absolute_url"):
        url = event.get_absolute_url()
    else:
        try:
            url = reverse("events_program:entity_detail", args=["events", event.pk])
        except NoReverseMatch:
            url = ""
    return {
        "pk": event.pk,
        "title": getattr(event, "title", None) or str(event),
        "description": getattr(event, "description", "") or "",
        "start": start,
        "category": (
            dict(getattr(type(event), "Category", ()).choices).get(
                getattr(event, "category", ""),
                _display(event, "category"),
            )
            if "category" in names and hasattr(getattr(type(event), "Category", None), "choices")
            else (_display(event, "category") if "category" in names else "")
        ),
        "event_type": _display(event, "event_type") if "event_type" in names else "",
        "status": getattr(event, "lifecycle_status_label", ""),
        "location": location,
        "image": image,
        "url": url,
    }


def event_card_payload(event):
    """Affichage commun d’un événement dans les cartes du site public."""
    return _event_payload(event, _field_names(type(event)))


def upcoming_events(limit=6):
    """Prochains événements publiés, si le Module 2 fournit ``Event``."""
    Event = optional_model("events_program", "Event")
    if Event is None:
        return {"available": False, "error": False, "items": []}
    names = _field_names(Event)
    queryset = Event.objects.all()
    try:
        for field in ("status", "publication_status"):
            if field in names:
                queryset = queryset.filter(**{f"{field}__in": PUBLISHED_VALUES})
        if "is_published" in names:
            queryset = queryset.filter(is_published=True)
        if "start_date" in names:
            field = Event._meta.get_field("start_date")
            now = timezone.now() if field.get_internal_type() == "DateTimeField" else timezone.localdate()
            queryset = queryset.filter(start_date__gte=now).order_by("start_date")
        items = [_event_payload(event, names) for event in queryset[:limit]]
    except DatabaseError:
        logger.exception("Lecture des événements impossible")
        return {"available": True, "error": True, "items": []}
    return {"available": True, "error": False, "items": items}


def event_category_distribution():
    Event = optional_model("events_program", "Event")
    if Event is None or "category" not in _field_names(Event):
        return None
    try:
        rows = list(Event.objects.values("category").annotate(total=Count("pk")).order_by("-total"))
    except DatabaseError:
        return None
    choices = dict(Event._meta.get_field("category").choices or [])
    return [{"label": str(choices.get(row["category"], row["category"] or "Sans catégorie")), "value": row["total"]} for row in rows]


def budget_distribution():
    """Budget prévu par événement, si le Module 5 fournit ``Budget``."""
    Budget = optional_model("sponsors_finance", "Budget")
    if Budget is None:
        return None
    names = _field_names(Budget)
    amount = next((f for f in ("planned_amount", "amount") if f in names), None)
    group = next((f for f in ("event", "id_event", "event_id", "category") if f in names), None)
    if amount is None:
        return None
    try:
        if group:
            rows = Budget.objects.values(group).annotate(total=Sum(amount)).order_by("-total")[:8]
            return [{"label": f"Événement {row[group]}" if "event" in group else str(row[group]), "value": float(row["total"] or 0)} for row in rows]
        total = Budget.objects.aggregate(total=Sum(amount))["total"] or 0
        return [{"label": "Budget total", "value": float(total)}]
    except DatabaseError:
        return None


# --- Inscriptions & accès (Module 3) -----------------------------------------


def registration_models():
    return (
        optional_model("registration_access", "Registration"),
        optional_model("registration_access", "Ticket"),
        optional_model("registration_access", "Attendance"),
        optional_model("registration_access", "AccessPoint"),
    )


def registration_evolution(months=6):
    Registration = optional_model("registration_access", "Registration")
    starts = _month_starts(months)
    if Registration is None:
        return []
    first = timezone.make_aware(datetime(starts[0].year, starts[0].month, 1))
    rows = (
        Registration.objects.filter(registration_date__gte=first)
        .annotate(month=TruncMonth("registration_date"))
        .values("month")
        .annotate(total=Count("pk"))
    )
    totals = {}
    for row in rows:
        month = row["month"]
        if hasattr(month, "date"):
            month = timezone.localtime(month).date() if timezone.is_aware(month) else month.date()
        totals[(month.year, month.month)] = row["total"]
    return [{"label": month_label(start), "value": totals.get((start.year, start.month), 0)} for start in starts]


def registration_status_distribution():
    Registration = optional_model("registration_access", "Registration")
    if Registration is None:
        return []
    counts = dict(Registration.objects.values_list("status").annotate(total=Count("pk")))
    return [{"label": str(label), "value": counts.get(value, 0)} for value, label in Registration.STATUS_CHOICES]


def platform_snapshot():
    """Chiffres publics affichés sur l'accueil (agrégats, aucune donnée personnelle)."""
    from users_teams.models import User

    Registration, Ticket, Attendance, _ = registration_models()
    team = User.objects.filter(status=User.Status.ACTIVE).exclude(business_role="")
    events = upcoming_events(limit=50)
    return {
        "registrations": Registration.objects.count() if Registration else 0,
        "tickets": Ticket.objects.count() if Ticket else 0,
        "check_ins": Attendance.objects.filter(check_in__isnull=False).count() if Attendance else 0,
        "team_members": team.count(),
        "directors": team.filter(business_role=User.BusinessRole.DIRECTOR).count(),
        "organizers": team.filter(business_role=User.BusinessRole.ORGANIZER).count(),
        "administrators": User.objects.filter(role=User.Role.ADMIN, status=User.Status.ACTIVE).count(),
        "participants": User.objects.filter(role=User.Role.PARTICIPANT, business_role="").count(),
        "upcoming_events": len(events["items"]) if events["available"] else None,
        "evolution": registration_evolution(6),
        "status_distribution": registration_status_distribution(),
    }


def _kpi(label, value, icon, tone="blue", hint="", url=""):
    return {"label": label, "value": value, "icon": icon, "tone": tone, "hint": hint, "url": url}


def dashboard_data(user):
    """Contexte du tableau de bord, adapté au rôle de l'utilisateur."""
    from users_teams.models import User

    Registration, Ticket, Attendance, AccessPoint = registration_models()
    is_admin = user.is_administrator
    is_director = user.business_role == User.BusinessRole.DIRECTOR
    sees_finance = is_admin or is_director
    today = timezone.localdate()
    month_start = timezone.make_aware(datetime(today.year, today.month, 1))

    reg_stats = Registration.objects.aggregate(
        total=Count("pk"),
        confirmed=Count("pk", filter=Q(status=Registration.STATUS_CONFIRMED)),
        pending=Count("pk", filter=Q(status=Registration.STATUS_PENDING)),
        unpaid=Count("pk", filter=Q(status=Registration.STATUS_CONFIRMED, payment_status=Registration.PAYMENT_PENDING)),
        this_month=Count("pk", filter=Q(registration_date__gte=month_start)),
    )
    revenue = (
        Ticket.objects.filter(registration__payment_status=Registration.PAYMENT_PAID)
        .exclude(status=Ticket.STATUS_REFUND)
        .aggregate(total=Sum("price"))["total"]
        or 0
    )
    tickets_total = Ticket.objects.count()
    check_ins = Attendance.objects.filter(check_in__isnull=False).count()
    present = Attendance.objects.filter(check_in__isnull=False, check_out__isnull=True).count()
    events = upcoming_events(limit=5)

    def list_url(entity, query=""):
        url = reverse("registration_access:entity_list", args=[entity])
        return f"{url}?{query}" if query else url

    kpis = [
        _kpi("Événements à venir", events["items"].__len__() if events["available"] else "—", "calendar-days", "blue",
             "publiés" if events["available"] else "module Events en cours", reverse("events_program:home")),
        _kpi("Inscriptions", reg_stats["total"], "clipboard-list", "teal",
             f"+{reg_stats['this_month']} ce mois-ci", list_url("registrations")),
        _kpi("Billets émis", tickets_total, "ticket", "orange",
             f"{reg_stats['confirmed']} inscription(s) confirmée(s)", list_url("tickets")),
        _kpi("Entrées enregistrées", check_ins, "scan-line", "green",
             f"{present} personne(s) sur site", list_url("attendances")),
    ]
    if sees_finance:
        kpis.append(_kpi("Recettes billetterie", f"{revenue:,.2f} DT".replace(",", " "), "banknote", "blue",
                         "billets payés, hors remboursements", list_url("tickets")))
    if is_admin:
        kpis.append(_kpi("Utilisateurs", User.objects.count(), "users", "teal",
                         f"{User.objects.exclude(business_role='').count()} membre(s) d’équipe", reverse("users_teams:user_list")))

    # Alertes calculées à partir de l'état réel.
    alerts = []
    if reg_stats["pending"]:
        alerts.append({"tone": "warning", "icon": "clock", "title": f"{reg_stats['pending']} inscription(s) en attente",
                       "text": "À confirmer ou refuser.", "url": list_url("registrations", "status=pending")})
    if reg_stats["unpaid"]:
        alerts.append({"tone": "warning", "icon": "credit-card", "title": f"{reg_stats['unpaid']} paiement(s) en attente",
                       "text": "Inscriptions confirmées non réglées.", "url": list_url("registrations", "payment=pending")})
    crowded = (
        AccessPoint.objects.annotate(
            present=Count("attendances", filter=Q(attendances__check_in__isnull=False, attendances__check_out__isnull=True))
        )
        .filter(present__gte=F("capacity") * 0.8)
        .order_by("-present")
    )
    for point in crowded[:3]:
        alerts.append({"tone": "danger", "icon": "triangle-alert", "title": f"{point.name} : {point.present}/{point.capacity}",
                       "text": "Point d’accès proche de sa capacité maximale.",
                       "url": reverse("registration_access:entity_detail", args=["access-points", point.pk])})
    if is_admin:
        inactive = User.objects.filter(status=User.Status.INACTIVE).count()
        if inactive:
            alerts.append({"tone": "info", "icon": "user-x", "title": f"{inactive} compte(s) inactif(s)",
                           "text": "Ces utilisateurs ne peuvent pas se connecter.",
                           "url": f"{reverse('users_teams:user_list')}?status=inactif"})

    # Activité récente : inscriptions, entrées et (admin) nouveaux comptes.
    activities = []
    for registration in Registration.objects.select_related("user").order_by("-registration_date")[:6]:
        activities.append({"icon": "clipboard-list", "when": registration.registration_date,
                           "text": f"{registration.user.get_full_name()} s’est inscrit·e à l’événement {registration.event_id}",
                           "meta": registration.get_status_display(),
                           "url": reverse("registration_access:entity_detail", args=["registrations", registration.pk])})
    for attendance in Attendance.objects.filter(check_in__isnull=False).select_related("ticket", "access_point").order_by("-check_in")[:6]:
        activities.append({"icon": "scan-line", "when": attendance.check_in,
                           "text": f"Entrée du billet {attendance.ticket.code} — {attendance.access_point.name}",
                           "meta": "Sortie enregistrée" if attendance.check_out else "Sur site",
                           "url": reverse("registration_access:entity_detail", args=["attendances", attendance.pk])})
    if is_admin:
        for account in User.objects.order_by("-created_at")[:4]:
            activities.append({"icon": "user-plus", "when": account.created_at,
                               "text": f"Nouveau compte : {account.get_full_name()}",
                               "meta": account.get_business_role_display() or account.get_role_display(),
                               "url": reverse("users_teams:user_detail", args=[account.pk])})
    activities.sort(key=lambda item: item["when"], reverse=True)

    ticket_categories = dict(Ticket.objects.values_list("category").annotate(total=Count("pk")))
    quick_actions = [
        {"label": "Enregistrer une entrée", "icon": "scan-line", "url": reverse("registration_access:attendance_check_in")},
        {"label": "Nouvelle inscription", "icon": "user-round-plus", "url": reverse("registration_access:entity_create", args=["registrations"])},
        {"label": "Points d’accès", "icon": "door-open", "url": list_url("access-points")},
    ]
    if is_admin:
        quick_actions.insert(0, {"label": "Nouvel utilisateur", "icon": "user-plus", "url": reverse("users_teams:user_create")})
    if is_admin or is_director:
        quick_actions.append({"label": "Programme des événements", "icon": "calendar-plus", "url": reverse("events_program:home")})

    return {
        "kpis": kpis,
        "alerts": alerts,
        "activities": activities[:8],
        "upcoming": events,
        "quick_actions": quick_actions,
        "sees_finance": sees_finance,
        "charts": {
            "evolution": registration_evolution(6),
            "status": registration_status_distribution(),
            "ticket_categories": [{"label": str(label), "value": ticket_categories.get(value, 0)} for value, label in Ticket.CATEGORY_CHOICES],
            "event_categories": event_category_distribution(),
            "budget": budget_distribution() if sees_finance else None,
        },
    }
