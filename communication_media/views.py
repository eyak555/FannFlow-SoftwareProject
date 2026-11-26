from django.contrib import messages
from django.db.models import Count
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.placeholders import render_crud_placeholder
from events_program.models import Event

from .entities import MODULE
from .forms import CommunicationForm, MediaContactForm, MediaForm, PressKitForm, PublicationForm
from .models import Communication, Media, MediaContact, PressKit, Publication


def module_home(request):
    """Accueil du module, avec les compteurs réels de chaque entité."""
    from core.registry import get_modules

    module = next(m for m in get_modules() if m["app_name"] == MODULE["app_name"])
    cards = [
        ("communication", "Communications", "Communiqués et contenus officiels.", Communication),
        ("media", "Médiathèque", "Images, affiches, vidéos et documents.", Media),
        ("press_kit", "Dossiers de presse", "Dossiers remis aux journalistes.", PressKit),
        ("media_contact", "Annuaire presse", "Journalistes et relais médias.", MediaContact),
        ("publication", "Publications", "Réseaux sociaux et site web.", Publication),
    ]
    return render(
        request,
        "communication_media/home.html",
        {
            "module": module,
            "page_title": MODULE["title"],
            "page_intro": MODULE["summary"],
            "counts": {
                "communications": Communication.objects.count(),
                "drafts": Communication.objects.filter(status=Communication.Status.DRAFT).count(),
                "media": Media.objects.count(),
                "publications": Publication.objects.count(),
                "scheduled": Publication.objects.filter(status=Publication.Status.SCHEDULED).count(),
                "without_event": sum(
                    model.objects.filter(event__isnull=True).count()
                    for model in (Communication, Media, PressKit, Publication)
                ),
            },
            "event_rows": [
                {
                    "event": event,
                    "communications": event.n_communications,
                    "media": event.n_media,
                    "publications": event.n_publications,
                }
                for event in Event.objects.annotate(
                    n_communications=Count("communications", distinct=True),
                    n_media=Count("media_files", distinct=True),
                    n_publications=Count("publications", distinct=True),
                ).order_by("-start_date")[:6]
            ],
            "cards": [
                {
                    "title": title,
                    "text": text,
                    "count": model.objects.count(),
                    "list_url": reverse(f"communication_media:{prefix}_list"),
                    "create_url": reverse(f"communication_media:{prefix}_create"),
                }
                for prefix, title, text, model in cards
            ],
        },
    )


def crud_placeholder(request, entity, action, pk=None):
    return render_crud_placeholder(request, MODULE, entity, action, pk)


# --- Annuaire presse (entité « Contact média ») -------------------------
#
# Le socle n'active encore aucune authentification (voir README) : ces
# vues suivent la même règle que le reste de FannFlow sur ``main``. Pour
# restreindre l'accès plus tard, ajouter un mixin d'accès à MediaContactMixin.

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


# --- Communication, Média, Dossier de presse, Publication -----------------
#
# Les quatre CRUD partagent la même mécanique : seule la description de
# l'entité (``EntityCrud``) change. L'accès est contrôlé par le middleware du
# socle (core.access) : visiteur → connexion, participant → 403.


class EntityCrud:
    """Description d'une entité du module pour ses cinq écrans."""

    def __init__(self, *, slug, model, form_class, url_prefix, template_dir,
                 list_title, list_intro, noun, feminine, add_label,
                 empty_title, empty_text):
        self.slug = slug
        self.model = model
        self.form_class = form_class
        self.url_prefix = url_prefix
        self.template_dir = template_dir
        self.list_title = list_title
        self.list_intro = list_intro
        self.noun = noun  # « La communication », « Le média »…
        self.feminine = feminine
        self.add_label = add_label
        self.empty_title = empty_title
        self.empty_text = empty_text
        self.entity = next(item for item in MODULE["entities"] if item["slug"] == slug)

    def url_name(self, action):
        return f"communication_media:{self.url_prefix}_{action}"

    def done(self, verb):
        return f"{verb}e" if self.feminine else verb

    def success_message(self, obj, verb):
        return f"{self.noun} « {label_of(obj)} » a été {self.done(verb)}."


def label_of(obj):
    return getattr(obj, "title", None) or getattr(obj, "name", None) or str(obj)


class EntityCrudMixin:
    crud = None

    @property
    def model(self):
        return self.crud.model

    def get_context_data(self, **kwargs):
        crud = self.crud
        kwargs.setdefault("module", MODULE)
        kwargs.setdefault("entity", crud.entity)
        kwargs.setdefault("crud", crud)
        kwargs.setdefault("list_url", reverse(crud.url_name("list")))
        kwargs.setdefault("create_url", reverse(crud.url_name("create")))
        return super().get_context_data(**kwargs)


class EntityListView(EntityCrudMixin, ListView):
    """Liste paginée, filtrable par événement : ``?evenement=<id>``.

    Un identifiant d'événement inconnu ou mal formé renvoie une 404.
    """

    context_object_name = "items"
    paginate_by = 20
    related = ("event",)

    def get_template_names(self):
        return [f"communication_media/{self.crud.template_dir}/list.html"]

    def get_selected_event(self):
        if not hasattr(self, "_selected_event"):
            raw = self.request.GET.get("evenement", "")
            if not raw:
                self._selected_event = None
            elif not raw.isdigit():
                raise Http404("Événement introuvable.")
            else:
                self._selected_event = get_object_or_404(Event, pk=int(raw))
        return self._selected_event

    def get_queryset(self):
        queryset = super().get_queryset().select_related(*self.related)
        event = self.get_selected_event()
        return queryset.filter(event=event) if event else queryset

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            page_title=self.crud.list_title,
            page_intro=self.crud.list_intro,
            selected_event=self.get_selected_event(),
            events=Event.objects.order_by("-start_date", "title"),
            **kwargs,
        )


class EntityDetailView(EntityCrudMixin, DetailView):
    context_object_name = "item"

    def get_queryset(self):
        return super().get_queryset().select_related("event")

    def get_template_names(self):
        return [f"communication_media/{self.crud.template_dir}/detail.html"]

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            page_title=label_of(self.object),
            update_url=reverse(self.crud.url_name("update"), args=[self.object.pk]),
            delete_url=reverse(self.crud.url_name("delete"), args=[self.object.pk]),
            **kwargs,
        )


class EntityFormMixin(EntityCrudMixin):
    template_name = "communication_media/shared/form.html"

    def get_form_class(self):
        return self.crud.form_class


class EntityCreateView(EntityFormMixin, CreateView):
    def get_context_data(self, **kwargs):
        return super().get_context_data(
            page_title=self.crud.add_label,
            page_intro="Les champs marqués d’un astérisque sont obligatoires.",
            breadcrumb_current="Ajout",
            cancel_url=reverse(self.crud.url_name("list")),
            **kwargs,
        )

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, self.crud.success_message(self.object, "ajouté"))
        return response


class EntityUpdateView(EntityFormMixin, UpdateView):
    context_object_name = "item"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            page_title=f"Modifier « {label_of(self.object)} »",
            page_intro="Les champs marqués d’un astérisque sont obligatoires.",
            breadcrumb_current="Modification",
            cancel_url=self.object.get_absolute_url(),
            **kwargs,
        )

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, self.crud.success_message(self.object, "modifié"))
        return response


class EntityDeleteView(EntityCrudMixin, DeleteView):
    """GET : page de confirmation (rien n'est supprimé). POST + CSRF : suppression."""

    context_object_name = "item"
    template_name = "communication_media/shared/confirm_delete.html"

    def get_success_url(self):
        return reverse(self.crud.url_name("list"))

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            page_title=f"Supprimer {self.crud.noun.lower()}",
            breadcrumb_current="Suppression",
            item_label=label_of(self.object),
            **kwargs,
        )

    def form_valid(self, form):
        message = self.crud.success_message(self.object, "supprimé")
        response = super().form_valid(form)
        messages.success(self.request, message)
        return response


COMMUNICATION_CRUD = EntityCrud(
    slug="communications",
    model=Communication,
    form_class=CommunicationForm,
    url_prefix="communication",
    template_dir="communications",
    list_title="Communications",
    list_intro="Communiqués de presse, annonces et contenus officiels de FannFlow.",
    noun="La communication",
    feminine=True,
    add_label="Ajouter une communication",
    empty_title="Aucune communication",
    empty_text="Rédigez un premier communiqué ; il sera enregistré en brouillon.",
)

MEDIA_CRUD = EntityCrud(
    slug="media",
    model=Media,
    form_class=MediaForm,
    url_prefix="media",
    template_dir="media_library",
    list_title="Médiathèque",
    list_intro="Images, affiches, vidéos et documents téléversés pour la communication.",
    noun="Le média",
    feminine=False,
    add_label="Ajouter un média",
    empty_title="La médiathèque est vide",
    empty_text="Téléversez une première image, affiche, vidéo ou un document.",
)

PRESS_KIT_CRUD = EntityCrud(
    slug="press-kits",
    model=PressKit,
    form_class=PressKitForm,
    url_prefix="press_kit",
    template_dir="press_kits",
    list_title="Dossiers de presse",
    list_intro="Dossiers remis aux journalistes et aux partenaires médias.",
    noun="Le dossier de presse",
    feminine=False,
    add_label="Ajouter un dossier de presse",
    empty_title="Aucun dossier de presse",
    empty_text="Créez un premier dossier à remettre aux journalistes.",
)

PUBLICATION_CRUD = EntityCrud(
    slug="publications",
    model=Publication,
    form_class=PublicationForm,
    url_prefix="publication",
    template_dir="publications",
    list_title="Publications",
    list_intro="Publications prévues ou diffusées sur les réseaux sociaux et le site.",
    noun="La publication",
    feminine=True,
    add_label="Ajouter une publication",
    empty_title="Aucune publication",
    empty_text="Préparez une première publication pour les réseaux sociaux.",
)

ENTITY_CRUDS = (COMMUNICATION_CRUD, MEDIA_CRUD, PRESS_KIT_CRUD, PUBLICATION_CRUD)


class MediaListView(EntityListView):
    crud = MEDIA_CRUD
    related = ("event", "communication")


class MediaDetailView(EntityDetailView):
    crud = MEDIA_CRUD

    def get_queryset(self):
        return super().get_queryset().select_related("event", "communication")


def media_file(request, pk):
    """Sert le fichier d'un média enregistré sur le disque (MEDIA_ROOT).

    La vue appartient à l'espace de noms du module : elle bénéficie donc du
    contrôle d'accès du back-office, contrairement à l'URL /media/ brute.
    """
    media = get_object_or_404(Media, pk=pk)
    if not media.file or not media.file.storage.exists(media.file.name):
        raise Http404("Le fichier de ce média est introuvable sur le serveur.")
    inline = media.is_image or media.is_video or media.is_pdf
    return FileResponse(
        media.file.open("rb"),
        as_attachment=not inline,
        filename=media.original_filename or None,
    )
