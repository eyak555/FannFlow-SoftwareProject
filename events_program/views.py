import hashlib
import json
import logging
import socket
from datetime import datetime, timedelta

from django.contrib import messages
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.db.models import CharField, Count, Q, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.formats import date_format
from django.utils import timezone
from django.views.decorators.http import require_GET
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from registration_access.models import AccessPoint, Attendance, Registration
from resources_operations.models import Venue
from .entities import MODULE
from .forms import (
    ActivityForm,
    ActivitySpeakerForm,
    EventDashboardFilterForm,
    EventForm,
    SpeakerForm,
)
from .models import Activity, ActivitySpeaker, Event, Speaker


logger = logging.getLogger(__name__)


ENTITY_CONFIG = {
    "events": {
        "model": Event,
        "form": EventForm,
        "name": "Événement",
        "plural": "Événements",
    },
    "activities": {
        "model": Activity,
        "form": ActivityForm,
        "name": "Activité",
        "plural": "Activités",
    },
    "speakers": {
        "model": Speaker,
        "form": SpeakerForm,
        "name": "Intervenant",
        "plural": "Intervenants",
    },
    "activity-speakers": {
        "model": ActivitySpeaker,
        "form": ActivitySpeakerForm,
        "name": "Affectation intervenant",
        "plural": "Affectations intervenants",
    },
}

ACTION_LABELS = {
    "list": "Liste",
    "create": "Création",
    "detail": "Détail",
    "update": "Modification",
    "delete": "Suppression",
}

TUNISIA_BOUNDS = {
    "south": 30.0,
    "west": 7.0,
    "north": 37.6,
    "east": 11.7,
}


def _month_start(day):
    month_index = day.month - 1
    return day.replace(
        year=day.year + month_index // 12,
        month=month_index % 12 + 1,
        day=1,
    )


def _shift_month(month, offset):
    month_index = month.month - 1 + offset
    return month.replace(
        year=month.year + month_index // 12,
        month=month_index % 12 + 1,
        day=1,
    )


def _monthly_counts(queryset, field_name, first_month, month_count):
    start = timezone.make_aware(
        datetime.combine(first_month, datetime.min.time()),
        timezone.get_current_timezone(),
    )
    end = timezone.make_aware(
        datetime.combine(_shift_month(first_month, month_count), datetime.min.time()),
        timezone.get_current_timezone(),
    )
    grouped = (
        queryset.filter(
            **{
                f"{field_name}__gte": start,
                f"{field_name}__lt": end,
            }
        )
        .annotate(month=TruncMonth(field_name))
        .values("month")
        .annotate(value=Count("pk"))
    )
    counts = {
        (row["month"].year, row["month"].month): row["value"]
        for row in grouped
    }
    return [
        {
            "label": date_format(_shift_month(first_month, offset), "b Y"),
            "value": counts.get(
                (
                    _shift_month(first_month, offset).year,
                    _shift_month(first_month, offset).month,
                ),
                0,
            ),
        }
        for offset in range(month_count)
    ]


def _dashboard_event_queryset(user, filter_data):
    visible_events = Event.objects.all()
    if user is not None and not user.is_administrator:
        visible_events = visible_events.filter(director=user)

    filter_form = EventDashboardFilterForm(
        data=filter_data,
        events=visible_events,
    )
    filters_valid = not filter_form.is_bound or filter_form.is_valid()
    if filters_valid and filter_form.is_bound:
        filters = filter_form.cleaned_data
        if filters["category"]:
            visible_events = visible_events.filter(category=filters["category"])
        if filters["status"]:
            visible_events = visible_events.filter(status=filters["status"])
        if filters["city"]:
            visible_events = visible_events.filter(
                Q(venue__city=filters["city"])
                | Q(venue__isnull=True, location=filters["city"])
            )
        if filters["start_date"]:
            visible_events = visible_events.filter(
                start_date__date__gte=filters["start_date"]
            )
        if filters["end_date"]:
            visible_events = visible_events.filter(
                start_date__date__lte=filters["end_date"]
            )
    return visible_events, filter_form, filters_valid


def event_dashboard(user=None, filter_data=None):
    now = timezone.now()
    visible_events, filter_form, filters_valid = _dashboard_event_queryset(
        user,
        filter_data,
    )

    published = visible_events.filter(status=Event.Status.PUBLISHED)
    event_ids = visible_events.values("pk")
    registrations = Registration.objects.filter(event_id__in=event_ids)
    confirmed_registrations = registrations.filter(
        status=Registration.STATUS_CONFIRMED
    )
    admissions = Attendance.objects.filter(
        ticket__registration__event_id__in=event_ids,
        check_in__isnull=False,
    )
    total_capacity = visible_events.aggregate(total=Sum("capacity"))["total"] or 0
    confirmed_count = confirmed_registrations.count()
    attendance_count = admissions.count()
    counts = {
        "total": visible_events.count(),
        "upcoming": published.filter(start_date__gt=now).count(),
        "ongoing": published.filter(start_date__lte=now, end_date__gte=now).count(),
        "completed": published.filter(end_date__lt=now).count(),
        "draft": visible_events.filter(status=Event.Status.DRAFT).count(),
        "cancelled": visible_events.filter(status=Event.Status.CANCELLED).count(),
        "activities": Activity.objects.filter(event_id__in=event_ids).count(),
        "speakers": Speaker.objects.filter(
            activities__event_id__in=event_ids
        ).distinct().count(),
        "registrations": registrations.count(),
        "confirmed_registrations": confirmed_count,
        "admissions": attendance_count,
        "capacity": total_capacity,
        "fill_rate": round(confirmed_count / total_capacity * 100) if total_capacity else 0,
    }
    category_labels = dict(Event.Category.choices)
    categories = list(
        visible_events.exclude(category="")
        .values("category")
        .annotate(total=Count("pk"))
        .order_by("-total", "category")[:8]
    )
    for row in categories:
        row["label"] = category_labels.get(row["category"], row["category"])

    city_field = Coalesce(
        "venue__city",
        "location",
        output_field=CharField(),
    )
    places = list(
        visible_events.annotate(display_place=city_field)
        .exclude(display_place="")
        .values("display_place")
        .annotate(total=Count("pk"))
        .order_by("-total", "display_place")[:6]
    )
    place_chart = [
        {"label": row["display_place"], "value": row["total"]}
        for row in places
    ]

    first_month = _month_start(timezone.localdate())
    event_schedule = _monthly_counts(visible_events, "start_date", first_month, 6)
    registration_month = _shift_month(first_month, -5)
    registration_schedule = _monthly_counts(
        confirmed_registrations,
        "registration_date",
        registration_month,
        6,
    )

    upcoming = list(
        published.filter(start_date__gte=now)
        .select_related("director", "venue")
        .order_by("start_date")[:5]
    )
    upcoming_ids = [event.pk for event in upcoming]
    upcoming_confirmed = dict(
        Registration.objects.filter(
            event_id__in=upcoming_ids,
            status=Registration.STATUS_CONFIRMED,
        )
        .values("event_id")
        .annotate(total=Count("pk"))
        .values_list("event_id", "total")
    )
    upcoming_admissions = dict(
        Attendance.objects.filter(
            ticket__registration__event_id__in=upcoming_ids,
            check_in__isnull=False,
        )
        .values("ticket__registration__event_id")
        .annotate(total=Count("pk"))
        .values_list("ticket__registration__event_id", "total")
    )
    for event in upcoming:
        event.confirmed_registrations = upcoming_confirmed.get(event.pk, 0)
        event.admissions = upcoming_admissions.get(event.pk, 0)

    map_candidates = list(
        visible_events.filter(
            status=Event.Status.PUBLISHED,
            start_date__gte=now,
            venue__latitude__gte=TUNISIA_BOUNDS["south"],
            venue__latitude__lte=TUNISIA_BOUNDS["north"],
            venue__longitude__gte=TUNISIA_BOUNDS["west"],
            venue__longitude__lte=TUNISIA_BOUNDS["east"],
            venue__latitude__isnull=False,
            venue__longitude__isnull=False,
        )
        .select_related("venue")
        .order_by("start_date")[:151]
    )
    map_events = [
        {
            "latitude": float(event.venue.latitude),
            "longitude": float(event.venue.longitude),
            "title": event.title,
            "place": event.venue.city,
            "start": date_format(event.start_date, "j F Y, H:i"),
            "url": reverse(
                "events_program:entity_detail",
                args=["events", event.pk],
            ),
        }
        for event in map_candidates[:150]
    ]

    return {
        "counts": counts,
        "categories": categories,
        "upcoming": upcoming,
        "filter_form": filter_form,
        "filters_valid": filters_valid,
        "map_events": map_events,
        "map_truncated": len(map_candidates) > 150,
        "charts": {
            "events_by_month": event_schedule,
            "confirmed_by_month": registration_schedule,
            "categories": [
                {"label": row["label"], "value": row["total"]}
                for row in categories
            ],
            "places": place_chart,
        },
    }


def module_home(request):
    dashboard = event_dashboard(request.user, request.GET)
    return render(
        request,
        "events_program/dashboard.html",
        {
            "module": MODULE,
            "dashboard": dashboard,
            "osm_tile_url": settings.OSM_TILE_URL,
            "calendar_today": timezone.localdate(),
            "page_title": MODULE["title"],
            "page_intro": MODULE["summary"],
        },
    )


@require_GET
def calendar_events(request):
    start_date = parse_date(request.GET.get("start", ""))
    end_date = parse_date(request.GET.get("end", ""))
    if (
        start_date is None
        or end_date is None
        or end_date <= start_date
        or (end_date - start_date).days > 42
    ):
        return JsonResponse(
            {"error": "La période demandée est invalide."},
            status=400,
        )

    events, _, filters_valid = _dashboard_event_queryset(
        request.user,
        request.GET,
    )
    if not filters_valid:
        return JsonResponse(
            {"error": "Les filtres du tableau de bord sont invalides."},
            status=400,
        )

    current_timezone = timezone.get_current_timezone()
    range_start = timezone.make_aware(
        datetime.combine(start_date, datetime.min.time()),
        current_timezone,
    )
    range_end = timezone.make_aware(
        datetime.combine(end_date, datetime.min.time()),
        current_timezone,
    )
    candidates = list(
        events.filter(
            start_date__lt=range_end,
            end_date__gt=range_start,
        )
        .select_related("venue")
        .order_by("start_date", "title")[:501]
    )

    calendar_items = []
    for event in candidates[:500]:
        local_start = timezone.localtime(event.start_date, current_timezone)
        local_end = timezone.localtime(event.end_date, current_timezone)
        end_day = local_end.date()
        if local_end.time() == datetime.min.time():
            end_day -= timedelta(days=1)
        if event.venue_id:
            place_parts = [event.venue.name]
            if event.venue.city and event.venue.city != event.venue.name:
                place_parts.append(event.venue.city)
            place = " · ".join(place_parts)
        else:
            place = event.location
        calendar_items.append(
            {
                "id": event.pk,
                "title": event.title,
                "start_day": local_start.date().isoformat(),
                "end_day": end_day.isoformat(),
                "start_time": local_start.strftime("%H:%M"),
                "end_time": local_end.strftime("%H:%M"),
                "place": place,
                "status": event.lifecycle_status,
                "status_label": event.lifecycle_status_label,
                "url": reverse(
                    "events_program:entity_detail",
                    args=["events", event.pk],
                ),
            }
        )
    return JsonResponse(
        {
            "events": calendar_items,
            "truncated": len(candidates) > 500,
        }
    )


def _nominatim_lookup(kind, params):
    query = urlencode(sorted(params.items()))
    cache_key = "events_program:nominatim:" + hashlib.sha256(
        f"{kind}:{query}".encode("utf-8")
    ).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    if not cache.add("events_program:nominatim:throttle", True, timeout=1):
        return None

    url = f"{settings.NOMINATIM_API_URL.rstrip('/')}/{kind}?{query}"
    request = Request(
        url,
        headers={
            "User-Agent": settings.NOMINATIM_USER_AGENT,
            "Accept-Language": "fr",
        },
    )
    try:
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        logger.warning("Nominatim returned HTTP %s", error.code)
        raise
    except (URLError, TimeoutError, socket.timeout, json.JSONDecodeError, UnicodeDecodeError):
        logger.exception("Nominatim lookup failed")
        raise

    cache.set(cache_key, result, timeout=60 * 60 * 24)
    return result


def _coordinate_token(latitude, longitude):
    return signing.dumps(
        {
            "latitude": str(latitude),
            "longitude": str(longitude),
        },
        salt="events_program.verified_venue_coordinates",
        compress=True,
    )


def _location_fields(address):
    address = address or {}
    city = next(
        (
            value.strip()
            for key in ("city", "town", "village", "municipality", "county", "state_district")
            if isinstance((value := address.get(key)), str) and value.strip()
        ),
        "",
    )
    street = next(
        (
            value.strip()
            for key in ("road", "pedestrian", "suburb")
            if isinstance((value := address.get(key)), str) and value.strip()
        ),
        "",
    )
    return {
        "address": street,
        "city": city[:100],
    }


@require_GET
def geocode_location(request):
    query = request.GET.get("q", "").strip()
    reverse = request.GET.get("reverse") == "1"
    if reverse:
        try:
            latitude = round(float(request.GET.get("lat", "")), 6)
            longitude = round(float(request.GET.get("lon", "")), 6)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Coordonnées invalides."}, status=400)
        if not (
            TUNISIA_BOUNDS["south"] <= latitude <= TUNISIA_BOUNDS["north"]
            and TUNISIA_BOUNDS["west"] <= longitude <= TUNISIA_BOUNDS["east"]
        ):
            return JsonResponse(
                {"error": "Choisissez une position dans la zone de la Tunisie."},
                status=400,
            )
        params = {
            "format": "jsonv2",
            "lat": f"{latitude:.6f}",
            "lon": f"{longitude:.6f}",
            "zoom": "18",
            "addressdetails": "1",
        }
        kind = "reverse"
    else:
        if not query or len(query) > 200:
            return JsonResponse(
                {"error": "Saisissez une adresse ou une ville de 1 à 200 caractères."},
                status=400,
            )
        params = {
            "format": "jsonv2",
            "q": query,
            "countrycodes": "tn",
            "addressdetails": "1",
            "limit": "5",
        }
        kind = "search"

    try:
        result = _nominatim_lookup(kind, params)
    except HTTPError:
        return JsonResponse(
            {"error": "Le service de recherche de lieux est temporairement indisponible."},
            status=502,
        )
    except (URLError, TimeoutError, socket.timeout, json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Impossible de joindre le service de recherche. Vous pouvez continuer sans coordonnées."},
            status=502,
        )
    if result is None:
        response = JsonResponse(
            {"error": "Veuillez patienter une seconde avant une nouvelle recherche."},
            status=429,
        )
        response["Retry-After"] = "1"
        return response

    if reverse:
        address = result.get("address", {}) if isinstance(result, dict) else {}
        country_code = address.get("country_code") if isinstance(address, dict) else None
        if not isinstance(country_code, str) or country_code.lower() != "tn":
            return JsonResponse(
                {"error": "Cette position n’a pas pu être confirmée en Tunisie."},
                status=400,
            )
        fields = _location_fields(address)
        display_name = result.get("display_name", "")
        if not isinstance(display_name, str):
            display_name = ""
        name = result.get("name")
        if not isinstance(name, str) or not name:
            name = display_name.split(",")[0]
        return JsonResponse(
            {
                "latitude": f"{latitude:.6f}",
                "longitude": f"{longitude:.6f}",
                "name": name.split(",")[0][:150],
                "label": display_name,
                **fields,
                "token": _coordinate_token(
                    f"{latitude:.6f}",
                    f"{longitude:.6f}",
                ),
            }
        )

    results = []
    for item in result if isinstance(result, list) else []:
        if not isinstance(item, dict):
            continue
        address = item.get("address", {})
        country_code = address.get("country_code") if isinstance(address, dict) else None
        if not isinstance(country_code, str) or country_code.lower() != "tn":
            continue
        try:
            latitude = f"{float(item['lat']):.6f}"
            longitude = f"{float(item['lon']):.6f}"
        except (KeyError, TypeError, ValueError):
            continue
        if not (
            TUNISIA_BOUNDS["south"] <= float(latitude) <= TUNISIA_BOUNDS["north"]
            and TUNISIA_BOUNDS["west"] <= float(longitude) <= TUNISIA_BOUNDS["east"]
        ):
            continue
        fields = _location_fields(address)
        display_name = item.get("display_name", "")
        if not isinstance(display_name, str):
            display_name = ""
        name = item.get("name")
        if not isinstance(name, str) or not name:
            name = display_name.split(",")[0]
        results.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "name": name[:150],
                "label": display_name,
                **fields,
                "token": _coordinate_token(latitude, longitude),
            }
        )
    return JsonResponse({"results": results})


def _entity_queryset(entity_slug):
    model = ENTITY_CONFIG[entity_slug]["model"]
    queryset = model.objects.all()
    if entity_slug == "events":
        return queryset.select_related("director", "venue").prefetch_related("activities")
    if entity_slug == "activities":
        return queryset.select_related("event").prefetch_related("speakers")
    if entity_slug == "activity-speakers":
        return queryset.select_related("activity", "speaker")
    return queryset


def _set_activity_speakers(activity, speakers):
    selected_ids = {speaker.pk for speaker in speakers}
    existing_ids = set(
        ActivitySpeaker.objects.filter(activity=activity).values_list("speaker_id", flat=True)
    )
    ActivitySpeaker.objects.filter(activity=activity).exclude(speaker_id__in=selected_ids).delete()
    ActivitySpeaker.objects.bulk_create(
        [
            ActivitySpeaker(activity=activity, speaker_id=speaker_id)
            for speaker_id in selected_ids - existing_ids
        ]
    )


def _event_delete_blocker(event):
    if Registration.objects.filter(event_id=event.pk).exists():
        return "Des inscriptions sont liées à cet événement. Annulez-les ou archivez l’événement au lieu de le supprimer."
    if AccessPoint.objects.filter(event_id=event.pk).exists():
        return "Des points d’accès sont liés à cet événement. Supprimez-les depuis le module Inscriptions et Accès avant de continuer."
    return ""


def crud_placeholder(request, entity, action, pk=None):
    config = ENTITY_CONFIG.get(entity)
    if config is None or action not in ACTION_LABELS:
        raise Http404("Cette page n’existe pas dans le module.")
    if request.method not in ("GET", "HEAD", "POST"):
        return HttpResponseNotAllowed(["GET", "HEAD", "POST"])

    obj = get_object_or_404(_entity_queryset(entity), pk=pk) if pk is not None else None
    title = config["name"]
    context = {
        "module": MODULE,
        "entity": {"slug": entity, "name": title, "plural": config["plural"]},
        "entity_slug": entity,
        "object": obj,
        "pk": pk,
        "action": action,
        "page_title": f"{ACTION_LABELS[action]} — {title}",
    }

    if action == "list":
        queryset = _entity_queryset(entity)
        search = request.GET.get("q", "").strip()
        selected_status = request.GET.get("status", "")
        if search:
            if entity == "events":
                queryset = queryset.filter(
                    Q(title__icontains=search)
                    | Q(description__icontains=search)
                    | Q(location__icontains=search)
                    | Q(category__icontains=search)
                )
            elif entity == "activities":
                queryset = queryset.filter(Q(title__icontains=search) | Q(event__title__icontains=search))
            elif entity == "speakers":
                queryset = queryset.filter(
                    Q(name__icontains=search)
                    | Q(organization__icontains=search)
                    | Q(expertise__icontains=search)
                )
        if entity == "events" and selected_status in Event.Status.values:
            queryset = queryset.filter(status=selected_status)
        context.update(
            objects=queryset,
            search=search,
            selected_status=selected_status,
            status_choices=Event.Status.choices if entity == "events" else (),
            page_title=config["plural"],
        )
        return render(request, "events_program/list.html", context)

    if action in ("create", "update"):
        if request.method == "POST":
            form = config["form"](request.POST, request.FILES, instance=obj)
            if form.is_valid():
                with transaction.atomic():
                    if entity == "events":
                        saved = form.save(commit=False)
                        selected_venue = form.cleaned_data.get("venue")
                        latitude = form.cleaned_data.get("selected_latitude")
                        longitude = form.cleaned_data.get("selected_longitude")
                        if selected_venue:
                            saved.venue = selected_venue
                        elif latitude is not None and longitude is not None:
                            venue = Venue(
                                name=saved.location[:150],
                                venue_type=Venue.VenueType.OTHER,
                                address=form.cleaned_data["new_venue_address"],
                                city=form.cleaned_data["new_venue_city"],
                                latitude=latitude,
                                longitude=longitude,
                            )
                            venue.full_clean()
                            venue.save()
                            saved.venue = venue
                        saved.save()
                        form.save_m2m()
                    else:
                        saved = form.save()
                    if entity == "activities":
                        _set_activity_speakers(saved, form.cleaned_data["speakers"])
                messages.success(request, f"{title} enregistré avec succès.")
                return redirect(
                    "events_program:entity_detail",
                    entity=entity,
                    pk=saved.pk,
                )
        else:
            initial = {}
            if entity == "events" and action == "create":
                initial["director"] = request.user
            if entity == "activities" and action == "create":
                event_id = request.GET.get("event", "")
                if event_id.isdecimal():
                    initial["event"] = Event.objects.filter(pk=int(event_id)).first()
            form = config["form"](instance=obj, initial=initial)
        context.update(form=form, page_title=f"{ACTION_LABELS[action]} — {title}")
        if entity == "events":
            context["osm_tile_url"] = settings.OSM_TILE_URL
            context["geocode_url"] = reverse("events_program:geocode")
        return render(request, "events_program/form.html", context)

    if obj is None:
        raise Http404("Élément introuvable.")

    if action == "detail":
        if entity == "events":
            context["registration_count"] = Registration.objects.filter(event_id=obj.pk).count()
            context["osm_tile_url"] = settings.OSM_TILE_URL
            context["event_map"] = (
                {
                    "latitude": str(obj.venue.latitude),
                    "longitude": str(obj.venue.longitude),
                    "title": obj.venue.name,
                }
                if obj.venue
                and obj.venue.latitude is not None
                and obj.venue.longitude is not None
                else None
            )
        return render(request, "events_program/detail.html", context)

    if action == "delete":
        blocker = _event_delete_blocker(obj) if entity == "events" else ""
        if request.method == "POST":
            if blocker:
                messages.error(request, blocker)
                return redirect("events_program:entity_detail", entity=entity, pk=obj.pk)
            obj.delete()
            messages.success(request, f"{title} supprimé avec succès.")
            return redirect("events_program:entity_list", entity=entity)
        context["delete_blocker"] = blocker
        return render(request, "events_program/confirm_delete.html", context)

    raise Http404("Cette page n’existe pas dans le module.")
