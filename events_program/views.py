from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from registration_access.models import AccessPoint, Registration
from .entities import MODULE
from .forms import ActivityForm, ActivitySpeakerForm, EventForm, SpeakerForm
from .models import Activity, ActivitySpeaker, Event, Speaker


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


def event_dashboard():
    now = timezone.now()
    published = Event.objects.filter(status=Event.Status.PUBLISHED)
    counts = {
        "total": Event.objects.count(),
        "upcoming": published.filter(start_date__gt=now).count(),
        "ongoing": published.filter(start_date__lte=now, end_date__gte=now).count(),
        "completed": published.filter(end_date__lt=now).count(),
        "draft": Event.objects.filter(status=Event.Status.DRAFT).count(),
        "cancelled": Event.objects.filter(status=Event.Status.CANCELLED).count(),
        "activities": Activity.objects.count(),
        "speakers": Speaker.objects.count(),
        "registrations": Registration.objects.filter(
            event_id__in=Event.objects.values("pk")
        ).count(),
    }
    categories = list(
        Event.objects.exclude(category="")
        .values("category")
        .annotate(total=Count("pk"))
        .order_by("-total", "category")[:8]
    )
    upcoming = published.filter(start_date__gte=now).select_related("director").order_by("start_date")[:5]
    return {"counts": counts, "categories": categories, "upcoming": upcoming}


def module_home(request):
    dashboard = event_dashboard()
    return render(
        request,
        "events_program/dashboard.html",
        {
            "module": MODULE,
            "dashboard": dashboard,
            "page_title": MODULE["title"],
            "page_intro": MODULE["summary"],
        },
    )


def _entity_queryset(entity_slug):
    model = ENTITY_CONFIG[entity_slug]["model"]
    queryset = model.objects.all()
    if entity_slug == "events":
        return queryset.select_related("director").prefetch_related("activities")
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
        return render(request, "events_program/form.html", context)

    if obj is None:
        raise Http404("Élément introuvable.")

    if action == "detail":
        if entity == "events":
            context["registration_count"] = Registration.objects.filter(event_id=obj.pk).count()
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
