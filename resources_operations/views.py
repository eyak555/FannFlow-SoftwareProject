from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from core.placeholders import render_crud_placeholder, render_module_home
from .entities import MODULE
from .forms import VenueForm
from .models import Venue


VENUE_ENTITY = {
    "slug": "venues",
    "name": "Lieu",
    "plural": "Lieux",
    "fields": MODULE["entities"][0]["fields"],
}


def module_home(request):
    return render_module_home(request, MODULE)


def crud_placeholder(request, entity, action, pk=None):
    if entity == "venues":
        return venue_crud(request, action, pk)
    return render_crud_placeholder(request, MODULE, entity, action, pk)


def venue_crud(request, action, pk=None):
    action_labels = {
        "list": "Liste",
        "create": "Création",
        "detail": "Détail",
        "update": "Modification",
        "delete": "Suppression",
    }
    if action not in action_labels:
        raise Http404("Cette page n’existe pas dans le module.")
    if request.method not in ("GET", "HEAD", "POST"):
        return HttpResponseNotAllowed(["GET", "HEAD", "POST"])

    venue = get_object_or_404(Venue, pk=pk) if pk is not None else None
    context = {
        "module": MODULE,
        "entity": VENUE_ENTITY,
        "object": venue,
        "pk": pk,
        "action": action,
        "page_title": f"{action_labels[action]} — {VENUE_ENTITY['name']}",
    }

    if action == "list":
        search = request.GET.get("q", "").strip()
        queryset = Venue.objects.all()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(address__icontains=search)
                | Q(city__icontains=search)
            )
        page_obj = Paginator(queryset, 20).get_page(request.GET.get("page"))
        context.update(
            objects=page_obj.object_list,
            page_obj=page_obj,
            search=search,
            page_title=VENUE_ENTITY["plural"],
            page_intro="Lieux enregistrés et coordonnées disponibles pour les événements.",
        )
        return render(
            request,
            "resources_operations/venues/list.html",
            context,
        )

    if action in ("create", "update"):
        if request.method == "POST":
            form = VenueForm(request.POST, instance=venue)
            if form.is_valid():
                venue = form.save()
                messages.success(request, f"Le lieu « {venue.name} » a été enregistré.")
                return redirect(
                    "resources_operations:entity_detail",
                    entity="venues",
                    pk=venue.pk,
                )
        else:
            form = VenueForm(instance=venue)
        context.update(
            form=form,
            page_title=f"{action_labels[action]} — {VENUE_ENTITY['name']}",
            page_intro="Les coordonnées sont facultatives et doivent être renseignées ensemble.",
        )
        return render(request, "core/layouts/form.html", context)

    if venue is None:
        raise Http404("Lieu introuvable.")

    if action == "detail":
        return render(
            request,
            "resources_operations/venues/detail.html",
            context,
        )

    if action == "delete":
        blocker = venue.events.exists()
        if request.method == "POST":
            if blocker:
                messages.error(
                    request,
                    "Ce lieu est associé à un ou plusieurs événements et ne peut pas être supprimé.",
                )
                return redirect(
                    "resources_operations:entity_detail",
                    entity="venues",
                    pk=venue.pk,
                )
            name = venue.name
            venue.delete()
            messages.success(request, f"Le lieu « {name} » a été supprimé.")
            return redirect(
                "resources_operations:entity_list",
                entity="venues",
            )
        context["delete_blocker"] = blocker
        return render(
            request,
            "resources_operations/venues/confirm_delete.html",
            context,
        )

    raise Http404("Cette page n’existe pas dans le module.")
