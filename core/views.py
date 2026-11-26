from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.access import can_access_backoffice
from core.services import event_card_payload, platform_snapshot, upcoming_events
from events_program.models import Event


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
    """Catalogue public paginé, filtré et recherché en base."""
    filters = {
        key: request.GET.get(key, "").strip()
        for key in ("q", "salle", "date", "categorie", "status", "sort")
    }
    queryset = Event.objects.filter(status=Event.Status.PUBLISHED)
    if filters["q"]:
        queryset = queryset.filter(
            Q(title__icontains=filters["q"])
            | Q(description__icontains=filters["q"])
        )

    venues = list(
        Event.objects.filter(status=Event.Status.PUBLISHED)
        .exclude(location="")
        .order_by("location")
        .values_list("location", flat=True)
        .distinct()
    )
    categories = Event.Category.choices
    valid_categories = {value for value, _ in categories}
    if filters["categorie"] in valid_categories:
        queryset = queryset.filter(category=filters["categorie"])
    if filters["salle"] in venues:
        queryset = queryset.filter(location=filters["salle"])

    today = timezone.localdate()
    if filters["date"] in {value for value, _ in DATE_PERIODS}:
        if filters["date"] == "aujourdhui":
            first_day = today
            last_day = today + timedelta(days=1)
        elif filters["date"] == "week-end":
            first_day = (
                today + timedelta(days=(5 - today.weekday()) % 7)
                if today.weekday() != 6
                else today - timedelta(days=1)
            )
            last_day = first_day + timedelta(days=2)
        elif filters["date"] == "semaine":
            first_day = today
            last_day = today + timedelta(days=7 - today.weekday())
        else:
            first_day = today.replace(day=1)
            last_day = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
        start = timezone.make_aware(datetime.combine(first_day, datetime.min.time()))
        end = timezone.make_aware(datetime.combine(last_day, datetime.min.time()))
        queryset = queryset.filter(start_date__gte=start, start_date__lt=end)

    status_filters = {
        "upcoming": Q(start_date__gt=timezone.now()),
        "ongoing": Q(start_date__lte=timezone.now(), end_date__gte=timezone.now()),
        "completed": Q(end_date__lt=timezone.now()),
    }
    if filters["status"] in status_filters:
        queryset = queryset.filter(status_filters[filters["status"]])

    sort_options = {
        "date": ("start_date", "Date : plus proche"),
        "date_desc": ("-start_date", "Date : plus éloignée"),
        "title": ("title", "Nom : A à Z"),
        "title_desc": ("-title", "Nom : Z à A"),
    }
    sort = filters["sort"] if filters["sort"] in sort_options else "date"
    queryset = queryset.order_by(sort_options[sort][0], "pk")
    paginator = Paginator(queryset, 9)
    page_obj = paginator.get_page(request.GET.get("page"))
    page_numbers = [
        {"number": number, "ellipsis": False}
        if isinstance(number, int)
        else {"number": "", "ellipsis": True}
        for number in paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1)
    ]
    pagination_filters = request.GET.copy()
    pagination_filters.pop("page", None)
    has_filters = any(filters[key] for key in ("q", "salle", "date", "categorie", "status"))
    return render(
        request,
        "core/events.html",
        {
            "page_title": "Événements",
            "events": {
                "available": True,
                "error": False,
                "items": [event_card_payload(event) for event in page_obj.object_list],
            },
            "page_obj": page_obj,
            "page_numbers": page_numbers,
            "pagination_query": pagination_filters.urlencode(),
            "result_count": paginator.count,
            "has_filters": has_filters,
            "unfiltered_count": Event.objects.filter(status=Event.Status.PUBLISHED).count(),
            "categories": categories,
            "selected_category": filters["categorie"],
            "status_choices": (
                ("upcoming", "À venir"),
                ("ongoing", "En cours"),
                ("completed", "Terminés"),
            ),
            "sort_choices": tuple((value, label) for value, (_, label) in sort_options.items()),
            "search": {
                "venues": venues,
                "periods": DATE_PERIODS,
                "categories": categories,
                "statuses": (
                    ("upcoming", "À venir"),
                    ("ongoing", "En cours"),
                    ("completed", "Terminés"),
                ),
                "sorts": tuple((value, label) for value, (_, label) in sort_options.items()),
                "filters": filters,
            },
            "organize_url": _organize_url(request.user),
        },
    )


def event_detail(request, pk):
    event = get_object_or_404(
        Event.objects.prefetch_related("activities__speakers"),
        pk=pk,
        status=Event.Status.PUBLISHED,
    )
    return render(
        request,
        "core/event_detail.html",
        {
            "event": event,
            "event_image": event.display_image_url,
            "event_access_error": event.age_access_error(request.user),
            "page_title": event.title,
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
