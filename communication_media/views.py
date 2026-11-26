from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.placeholders import render_crud_placeholder, render_module_home

from .entities import MODULE
from .forms import MediaContactForm
from .models import MediaContact


def module_home(request):
    return render_module_home(request, MODULE)


def crud_placeholder(request, entity, action, pk=None):
    return render_crud_placeholder(request, MODULE, entity, action, pk)


# --- Annuaire presse (entité « Contact média ») -------------------------
#
# Accès : comme toutes les pages de gestion des modules, l'annuaire est
# réservé à l'équipe (administrateur, directeur, organisateur) par
# ``core.access.BackOfficeAccessMiddleware`` — aucun mixin à ajouter ici.

MEDIA_CONTACT_ENTITY = next(
    entity for entity in MODULE["entities"] if entity["slug"] == "media-contacts"
)
DIRECTORY_TITLE = "Annuaire presse"


class MediaContactMixin:
    model = MediaContact

    def get_context_data(self, **kwargs):
        kwargs.setdefault("module", MODULE)
        kwargs.setdefault("entity", MEDIA_CONTACT_ENTITY)
        kwargs.setdefault("directory_title", DIRECTORY_TITLE)
        return super().get_context_data(**kwargs)


class MediaContactListView(MediaContactMixin, ListView):
    template_name = "communication_media/media_contacts/list.html"
    context_object_name = "contacts"
    paginate_by = 20

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            page_title=DIRECTORY_TITLE,
            page_intro="Journalistes, rédactions et relais médias de FannFlow.",
            **kwargs,
        )


class MediaContactDetailView(MediaContactMixin, DetailView):
    template_name = "communication_media/media_contacts/detail.html"
    context_object_name = "contact"

    def get_context_data(self, **kwargs):
        return super().get_context_data(page_title=self.object.name, **kwargs)


class MediaContactCreateView(MediaContactMixin, CreateView):
    form_class = MediaContactForm
    template_name = "communication_media/media_contacts/form.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            page_title="Ajouter un contact",
            page_intro="Les champs marqués d’un astérisque sont obligatoires.",
            cancel_url=reverse("communication_media:media_contact_list"),
            **kwargs,
        )

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Le contact « {self.object.name} » a été ajouté.")
        return response


class MediaContactUpdateView(MediaContactMixin, UpdateView):
    form_class = MediaContactForm
    template_name = "communication_media/media_contacts/form.html"
    context_object_name = "contact"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            page_title=f"Modifier « {self.object.name} »",
            page_intro="Les champs marqués d’un astérisque sont obligatoires.",
            cancel_url=self.object.get_absolute_url(),
            **kwargs,
        )

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Le contact « {self.object.name} » a été modifié.")
        return response


class MediaContactDeleteView(MediaContactMixin, DeleteView):
    template_name = "communication_media/media_contacts/confirm_delete.html"
    context_object_name = "contact"
    success_url = reverse_lazy("communication_media:media_contact_list")

    def get_context_data(self, **kwargs):
        return super().get_context_data(page_title="Supprimer le contact", **kwargs)

    def form_valid(self, form):
        name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, f"Le contact « {name} » a été supprimé.")
        return response
