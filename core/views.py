from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from core.access import can_access_backoffice
from core.services import platform_snapshot, upcoming_events


def _organize_url(user):
    target = reverse("events_program:home")
    if can_access_backoffice(user):
        return target
    if user.is_authenticated:
        return ""
    return f"{reverse('users_teams:login')}?{urlencode({'next': target})}"


def home(request):
    snapshot = platform_snapshot()
    evolution = snapshot["evolution"]
    peak = max((item["value"] for item in evolution), default=0)
    home_events = upcoming_events(limit=6)
    return render(
        request,
        "core/home.html",
        {
            "page_title": "Accueil",
            "snapshot": snapshot,
            "evolution_bars": [
                {**item, "height": round(item["value"] / peak * 100) if peak else 0} for item in evolution
            ],
            "events": home_events,
            "search": {**search_options(upcoming_events(limit=48)["items"]), "filters": {}},
            "organize_url": _organize_url(request.user),
        },
    )


DATE_PERIODS = [
    ("aujourdhui", "Aujourd’hui"),
    ("week-end", "Ce week-end"),
    ("semaine", "Cette semaine"),
    ("mois", "Ce mois-ci"),
]


def _event_day(start):
    if isinstance(start, datetime):
        return timezone.localtime(start).date() if timezone.is_aware(start) else start.date()
    return start


def _in_period(start, period, today):
    day = _event_day(start)
    if day is None:
        return False
    if period == "aujourdhui":
        return day == today
    if period == "week-end":
        saturday = today + timedelta(days=(5 - today.weekday()) % 7) if today.weekday() != 6 else today - timedelta(days=1)
        return saturday <= day <= saturday + timedelta(days=1)
    if period == "semaine":
        return today <= day <= today + timedelta(days=6 - today.weekday())
    if period == "mois":
        return (day.year, day.month) == (today.year, today.month)
    return True


def search_options(items):
    """Valeurs proposées par la barre de recherche (issues des vrais événements)."""
    return {
        "venues": sorted({item["location"] for item in items if item["location"]}),
        "periods": DATE_PERIODS,
    }


def filter_events(items, params):
    query = params.get("q", "").strip().lower()
    venue = params.get("salle", "")
    period = params.get("date", "")
    category = params.get("categorie", "")
    today = timezone.localdate()
    result = []
    for item in items:
        if query and query not in f"{item['title']} {item['description']} {item['category']}".lower():
            continue
        if venue and item["location"] != venue:
            continue
        if period and not _in_period(item["start"], period, today):
            continue
        if category and item["category"] != category:
            continue
        result.append(item)
    return result


def events(request):
    """Catalogue public des événements publiés, avec recherche."""
    data = upcoming_events(limit=48)
    all_items = data["items"]
    filters = {key: request.GET.get(key, "") for key in ("q", "salle", "date", "categorie")}
    data = {**data, "items": filter_events(all_items, request.GET)}
    return render(
        request,
        "core/events.html",
        {
            "page_title": "Événements",
            "events": data,
            "has_filters": any(filters.values()),
            "unfiltered_count": len(all_items),
            "categories": sorted({item["category"] for item in all_items if item["category"]}),
            "selected_category": filters["categorie"],
            "search": {**search_options(all_items), "filters": filters},
            "organize_url": _organize_url(request.user),
        },
    )


@login_required
def my_space(request):
    """Espace participant : ses inscriptions et ses billets."""
    if can_access_backoffice(request.user):
        return redirect("users_teams:home")

    from registration_access.qr_codes import qr_code_data_uri
    from registration_access.services import ticket_is_ready_for_qr

    registrations = (
        request.user.registrations.prefetch_related("tickets").order_by("-registration_date")
    )
    items = []
    for registration in registrations:
        tickets = []
        for ticket in registration.tickets.all():
            ready = ticket_is_ready_for_qr(ticket)
            tickets.append({
                "ticket": ticket,
                "ready": ready,
                "qr": qr_code_data_uri(ticket.code) if ready else "",
            })
        items.append({"registration": registration, "tickets": tickets})
    return render(
        request,
        "core/my_space.html",
        {
            "page_title": "Mon espace",
            "items": items,
            "stats": {
                "total": len(items),
                "confirmed": sum(1 for i in items if i["registration"].status == "confirmed"),
                "ready": sum(1 for i in items for t in i["tickets"] if t["ready"]),
            },
        },
    )


def page_not_found(request, exception):
    return render(
        request,
        "404.html",
        {"page_title": "Page introuvable"},
        status=404,
    )
