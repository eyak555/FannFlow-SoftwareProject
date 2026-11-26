import os

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.template.defaultfilters import filesizeformat
from django.utils import timezone

from core.forms import FannFlowModelForm
from events_program.models import Event

from .models import (
    MEDIA_EXTENSIONS,
    MEDIA_FILE_RULES,
    Communication,
    Media,
    MediaContact,
    PressKit,
    Publication,
)


class MediaContactForm(FannFlowModelForm):
    """Formulaire de l'annuaire presse, en deux groupes : Identité et Coordonnées."""

    IDENTITY_FIELDS = ("name", "organization", "role")
    CONTACT_FIELDS = ("email", "phone")

    class Meta:
        model = MediaContact
        fields = ["name", "organization", "role", "email", "phone"]
        labels = {
            "name": "Nom complet",
            "organization": "Organisation ou média",
            "role": "Rôle",
            "email": "Adresse e-mail",
            "phone": "Téléphone",
        }
        help_texts = {
            "organization": "Facultatif. Exemple : Radio Culture, La Presse.",
            "email": "Facultatif. Exemple : prenom.nom@media.fr",
            "phone": "Facultatif. Exemple : +216 71 000 000",
        }
        error_messages = {
            "name": {
                "required": "Indiquez le nom du contact.",
                "max_length": "Le nom ne doit pas dépasser %(limit_value)d caractères.",
            },
            "organization": {
                "max_length": "L’organisation ne doit pas dépasser %(limit_value)d caractères.",
            },
            "email": {
                "invalid": "Saisissez une adresse e-mail valide, par exemple prenom.nom@media.fr.",
            },
            "role": {
                "required": "Choisissez un rôle.",
                "invalid_choice": "Choisissez un rôle dans la liste.",
            },
            "phone": {
                "max_length": "Le numéro ne doit pas dépasser %(limit_value)d caractères.",
            },
        }
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "name", "autofocus": True}),
            "organization": forms.TextInput(attrs={"autocomplete": "organization"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "inputmode": "email"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
        }

    def clean_name(self):
        # Le champ retire déjà les espaces de début et de fin ; on vérifie
        # explicitement pour garder le message même si ce comportement change.
        name = " ".join(self.cleaned_data.get("name", "").split())
        if not name:
            raise forms.ValidationError(
                self.fields["name"].error_messages["required"], code="required"
            )
        return name

    def clean_email(self):
        return self.cleaned_data.get("email", "").strip().lower()

    def clean_phone(self):
        return " ".join(self.cleaned_data.get("phone", "").split())

    def identity_fields(self):
        return [self[name] for name in self.IDENTITY_FIELDS]

    def contact_fields(self):
        return [self[name] for name in self.CONTACT_FIELDS]


# --- Outils communs aux quatre formulaires ---------------------------------


class DateTimeLocalInput(forms.DateTimeInput):
    """Sélecteur natif date + heure du navigateur (format ISO 8601)."""

    input_type = "datetime-local"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%dT%H:%M")


INVALID_DATETIME = "Saisissez une date et une heure valides, par exemple 15/12/2026 10:30."


EVENT_ERRORS = {
    "required": "Choisissez l’événement concerné.",
    "invalid_choice": "Cet événement n’existe pas. Choisissez un événement dans la liste.",
}


def event_label(event):
    return f"{event.title} — {timezone.localtime(event.start_date):%d/%m/%Y}"


class EventCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """Cases à cocher portant l'événement de chaque élément (``data-event``),
    pour masquer dans le navigateur celles d'un autre événement. Le contrôle
    qui fait foi reste celui du serveur (``PressKitForm.clean``)."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        option["attrs"]["data-event"] = getattr(instance, "event_id", "") or ""
        return option


class ModuleForm(FannFlowModelForm):
    """Formulaire présenté en groupes de champs (``fieldsets``).

    Les champs texte obligatoires sont revérifiés après suppression des
    espaces : une valeur faite uniquement d'espaces est refusée avec le
    message « obligatoire » du champ.

    Le champ ``event`` (s'il est présent) est obligatoire dans le formulaire,
    même si la colonne accepte NULL pour les données antérieures.
    """

    fieldsets = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields.get("event")
        if field is not None:
            field.required = True
            field.queryset = Event.objects.order_by("-start_date", "title")
            field.empty_label = "Choisissez un événement"
            field.label_from_instance = event_label
            field.error_messages.update(EVENT_ERRORS)
            field.widget.attrs["data-event-select"] = ""
            if self.instance.pk and self.instance.event_id is None:
                field.help_text = (
                    "Cet élément a été créé avant le lien avec les événements : "
                    "choisissez son événement pour l’enregistrer."
                )
        for form_field in self.fields.values():
            if isinstance(form_field.widget, forms.CheckboxSelectMultiple):
                form_field.widget.attrs.pop("class", None)

    def get_fieldsets(self):
        return [(legend, [self[name] for name in names]) for legend, names in self.fieldsets]

    def event_changed(self):
        """Vrai si un élément existant change d'événement."""
        event = self.cleaned_data.get("event")
        return bool(self.instance.pk and event and self.instance.event_id != event.pk)

    def check_press_kits_follow(self, item):
        """Refuse de changer l'événement d'un élément inclus dans un dossier
        de presse d'un autre événement : le dossier deviendrait incohérent."""
        event = self.cleaned_data.get("event")
        if not event or not self.event_changed():
            return
        kits = list(item.press_kits.exclude(event=event)[:3])
        if kits:
            titles = ", ".join(f"« {kit.title} »" for kit in kits)
            self.add_error(
                "event",
                f"Cet élément figure dans le dossier de presse {titles} d’un autre "
                "événement. Retirez-le d’abord de ce dossier.",
            )

    def _required_text(self, name, single_line=False):
        value = self.cleaned_data.get(name) or ""
        value = " ".join(value.split()) if single_line else value.strip()
        if not value and self.fields[name].required:
            raise forms.ValidationError(
                self.fields[name].error_messages["required"], code="required"
            )
        return value


# --- Communication ---------------------------------------------------------


class CommunicationForm(ModuleForm):
    fieldsets = (
        ("Contenu", ("event", "title", "type", "content")),
        ("Diffusion", ("language", "status", "publication_date")),
    )

    class Meta:
        model = Communication
        fields = ["event", "title", "type", "content", "language", "status", "publication_date"]
        labels = {
            "event": "Événement",
            "title": "Titre",
            "type": "Type de contenu",
            "content": "Contenu",
            "language": "Langue",
            "status": "Statut",
            "publication_date": "Date de publication",
        }
        help_texts = {
            "title": "Exemple : Ouverture de la billetterie du Festival des Arts.",
            "status": "Une nouvelle communication est enregistrée en brouillon par défaut.",
            "publication_date": "Facultative pour un brouillon, obligatoire pour un contenu publié.",
        }
        error_messages = {
            "title": {
                "required": "Indiquez le titre de la communication.",
                "max_length": "Le titre ne doit pas dépasser %(limit_value)d caractères.",
            },
            "content": {"required": "Rédigez le contenu de la communication."},
            "type": {
                "required": "Choisissez un type de contenu.",
                "invalid_choice": "Choisissez un type de contenu dans la liste.",
            },
            "language": {
                "required": "Choisissez une langue.",
                "invalid_choice": "Choisissez une langue dans la liste.",
            },
            "status": {
                "required": "Choisissez un statut.",
                "invalid_choice": "Choisissez un statut dans la liste.",
            },
            "publication_date": {"invalid": INVALID_DATETIME},
        }
        widgets = {
            "title": forms.TextInput(attrs={"autofocus": True}),
            "content": forms.Textarea(attrs={"rows": 10}),
            "publication_date": DateTimeLocalInput(),
        }

    def clean_title(self):
        return self._required_text("title", single_line=True)

    def clean_content(self):
        return self._required_text("content")

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("status") == Communication.Status.PUBLISHED
            and not cleaned.get("publication_date")
            and "publication_date" not in self.errors
        ):
            self.add_error(
                "publication_date", "Indiquez la date de publication d’un contenu publié."
            )
        event = cleaned.get("event")
        if event and self.event_changed():
            if self.instance.media.exclude(event=event).exists():
                self.add_error(
                    "event",
                    "Des médias liés à cette communication appartiennent à un autre "
                    "événement. Modifiez-les ou retirez-les d’abord.",
                )
            self.check_press_kits_follow(self.instance)
        return cleaned


# --- Média -----------------------------------------------------------------

# Signature (premiers octets) attendue pour chaque extension acceptée.
FILE_SIGNATURES = {
    "jpg": lambda head: head.startswith(b"\xff\xd8\xff"),
    "jpeg": lambda head: head.startswith(b"\xff\xd8\xff"),
    "png": lambda head: head.startswith(b"\x89PNG\r\n\x1a\n"),
    "webp": lambda head: head[:4] == b"RIFF" and head[8:12] == b"WEBP",
    "pdf": lambda head: head.startswith(b"%PDF-"),
    "mp4": lambda head: head[4:8] == b"ftyp",
    "webm": lambda head: head.startswith(b"\x1a\x45\xdf\xa3"),
    "docx": lambda head: head.startswith(b"PK\x03\x04"),
}


def extension_of(filename):
    return os.path.splitext(filename or "")[1].lstrip(".").lower()


def describe_rule(media_type):
    rule = MEDIA_FILE_RULES[media_type]
    formats = ", ".join(ext.upper() for ext in rule["extensions"] if ext != "jpeg")
    return f"{formats}, {rule['max_size'] // (1024 * 1024)} Mo maximum"


class MediaForm(ModuleForm):
    fieldsets = (
        ("Description", ("event", "name", "media_type", "communication")),
        ("Fichier", ("file",)),
    )

    class Meta:
        model = Media
        fields = ["event", "name", "media_type", "communication", "file"]
        labels = {
            "event": "Événement",
            "name": "Nom du média",
            "media_type": "Type de média",
            "communication": "Communication liée",
            "file": "Fichier",
        }
        help_texts = {
            "name": "Exemple : Affiche officielle 2026.",
            "communication": "Facultatif. La communication doit concerner le même événement.",
        }
        error_messages = {
            "name": {
                "required": "Indiquez le nom du média.",
                "max_length": "Le nom ne doit pas dépasser %(limit_value)d caractères.",
            },
            "media_type": {
                "required": "Choisissez un type de média.",
                "invalid_choice": "Choisissez un type de média dans la liste.",
            },
            "communication": {
                "invalid_choice": "Choisissez une communication existante dans la liste.",
            },
            "file": {
                "required": "Sélectionnez un fichier à téléverser.",
                "empty": "Le fichier envoyé est vide.",
                "invalid": "Aucun fichier n’a été reçu. Vérifiez le formulaire.",
                "max_length": "Le nom du fichier est trop long.",
            },
        }
        widgets = {
            "name": forms.TextInput(attrs={"autofocus": True}),
            "file": forms.FileInput(
                attrs={"accept": ",".join(f".{ext}" for ext in MEDIA_EXTENSIONS)}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["communication"].empty_label = "Aucune communication"
        self.fields["communication"].queryset = Communication.objects.select_related(
            "event"
        ).order_by("title")
        self.fields["communication"].label_from_instance = lambda c: (
            f"{c.title} ({c.event.title})" if c.event else f"{c.title} (sans événement)"
        )
        self.fields["media_type"].choices = [("", "Choisissez un type")] + list(
            Media.Type.choices
        )
        rules = " · ".join(
            f"{label} : {describe_rule(value)}" for value, label in Media.Type.choices
        )
        if self.instance.pk:
            self.fields["file"].help_text = (
                f"Fichier actuel : {self.instance.original_filename}. "
                f"Laissez vide pour le conserver. {rules}."
            )
        else:
            self.fields["file"].help_text = f"{rules}."

    def clean_name(self):
        return self._required_text("name", single_line=True)

    def clean(self):
        cleaned = super().clean()
        event, communication = cleaned.get("event"), cleaned.get("communication")
        if event and communication and communication.event_id != event.pk:
            self.add_error(
                "communication",
                f"Cette communication concerne un autre événement que « {event.title} ». "
                "Choisissez une communication du même événement, ou aucune.",
            )
        if self.instance.pk:
            self.check_press_kits_follow(self.instance)
        self._clean_file(cleaned)
        return cleaned

    def _clean_file(self, cleaned):
        media_type = cleaned.get("media_type")
        upload = cleaned.get("file")
        if not media_type or "file" in self.errors:
            return cleaned
        rule = MEDIA_FILE_RULES[media_type]
        type_label = Media.Type(media_type).label

        if isinstance(upload, UploadedFile):
            extension = extension_of(upload.name)
            if extension not in rule["extensions"]:
                self.add_error(
                    "file",
                    f"Format non accepté pour le type « {type_label} ». "
                    f"Formats acceptés : {describe_rule(media_type)}.",
                )
                return cleaned
            if upload.size > rule["max_size"]:
                self.add_error(
                    "file",
                    f"Le fichier pèse {filesizeformat(upload.size)} : la limite pour le type "
                    f"« {type_label} » est de {rule['max_size'] // (1024 * 1024)} Mo.",
                )
                return cleaned
            upload.seek(0)
            head = upload.read(16)
            upload.seek(0)
            if not FILE_SIGNATURES[extension](head):
                self.add_error(
                    "file",
                    f"Le contenu du fichier ne correspond pas à un fichier "
                    f"{extension.upper()} valide.",
                )
        elif self.instance.pk and extension_of(self.instance.file.name) not in rule["extensions"]:
            self.add_error(
                "media_type",
                f"Le fichier actuel ({self.instance.format}) ne correspond pas au type "
                f"« {type_label} ». Choisissez un autre type ou remplacez le fichier.",
            )
        return cleaned


# --- Dossier de presse -----------------------------------------------------


class PressKitForm(ModuleForm):
    fieldsets = (
        ("Dossier", ("event", "title", "description")),
        ("Contenu du dossier", ("communications", "media")),
    )

    class Meta:
        model = PressKit
        fields = ["event", "title", "description", "communications", "media"]
        labels = {
            "event": "Événement",
            "title": "Titre du dossier",
            "description": "Description",
            "communications": "Communications incluses",
            "media": "Médias inclus",
        }
        help_texts = {
            "title": "Exemple : Dossier de presse — Festival des Arts 2026.",
            "description": "Présentation, angles proposés aux journalistes, contacts utiles.",
            "communications": "Facultatif. Seules les communications de l’événement choisi sont acceptées.",
            "media": "Facultatif. Seuls les médias de l’événement choisi sont acceptés.",
        }
        error_messages = {
            "title": {
                "required": "Indiquez le titre du dossier de presse.",
                "max_length": "Le titre ne doit pas dépasser %(limit_value)d caractères.",
            },
            "description": {"required": "Rédigez la description du dossier."},
            "communications": {
                "invalid_choice": "Une communication sélectionnée n’existe pas.",
                "invalid_pk_value": "Une communication sélectionnée n’existe pas.",
            },
            "media": {
                "invalid_choice": "Un média sélectionné n’existe pas.",
                "invalid_pk_value": "Un média sélectionné n’existe pas.",
            },
        }
        widgets = {
            "title": forms.TextInput(attrs={"autofocus": True}),
            "description": forms.Textarea(attrs={"rows": 8}),
            "communications": EventCheckboxSelectMultiple(),
            "media": EventCheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["communications"].queryset = Communication.objects.select_related(
            "event"
        ).order_by("title")
        self.fields["media"].queryset = Media.objects.select_related("event").order_by("name")
        self.fields["communications"].label_from_instance = lambda c: (
            f"{c.title} — {c.get_type_display()}"
        )
        self.fields["media"].label_from_instance = lambda m: (
            f"{m.name} — {m.get_media_type_display()} ({m.format})"
        )

    def clean_title(self):
        return self._required_text("title", single_line=True)

    def clean_description(self):
        return self._required_text("description")

    def clean(self):
        cleaned = super().clean()
        event = cleaned.get("event")
        if not event:
            return cleaned
        for name, noun in (("communications", "communications"), ("media", "médias")):
            others = [item for item in cleaned.get(name) or [] if item.event_id != event.pk]
            if others:
                names = ", ".join(f"« {item} »" for item in others[:3])
                self.add_error(
                    name,
                    f"Sélection refusée : {names} ne concerne pas l’événement "
                    f"« {event.title} ». Ne sélectionnez que des {noun} de cet événement.",
                )
        return cleaned


# --- Publication -----------------------------------------------------------


class PublicationForm(ModuleForm):
    fieldsets = (
        ("Publication", ("event", "platform", "content")),
        ("Planification", ("publication_date", "status")),
    )

    class Meta:
        model = Publication
        fields = ["event", "platform", "content", "publication_date", "status"]
        labels = {
            "event": "Événement",
            "platform": "Plateforme",
            "content": "Contenu",
            "publication_date": "Date de publication",
            "status": "Statut",
        }
        help_texts = {
            "content": "280 caractères maximum pour X, 5 000 pour les autres plateformes.",
            "status": "« Programmée » exige une date future ; « Publiée », une date passée ou actuelle.",
        }
        error_messages = {
            "platform": {
                "required": "Choisissez une plateforme.",
                "invalid_choice": "Choisissez une plateforme dans la liste.",
            },
            "content": {
                "required": "Rédigez le contenu de la publication.",
                "max_length": "Le contenu ne doit pas dépasser %(limit_value)d caractères.",
            },
            "publication_date": {
                "required": "Indiquez la date et l’heure de publication.",
                "invalid": INVALID_DATETIME,
            },
            "status": {
                "required": "Choisissez un statut.",
                "invalid_choice": "Choisissez un statut dans la liste.",
            },
        }
        widgets = {
            "content": forms.Textarea(attrs={"rows": 6}),
            "publication_date": DateTimeLocalInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["platform"].choices = [("", "Choisissez une plateforme")] + list(
            Publication.Platform.choices
        )

    def clean_content(self):
        return self._required_text("content")

    def clean(self):
        cleaned = super().clean()
        platform, content = cleaned.get("platform"), cleaned.get("content")
        limit = Publication.PLATFORM_MAX_LENGTH.get(platform)
        if limit and content and len(content) > limit:
            self.add_error(
                "content",
                f"Sur {Publication.Platform(platform).label}, le contenu ne doit pas "
                f"dépasser {limit} caractères (actuellement {len(content)}).",
            )

        status, date = cleaned.get("status"), cleaned.get("publication_date")
        # Contrôle seulement si la date ou le statut changent : une publication
        # programmée dont la date est passée reste modifiable. La date est
        # comparée à la minute près, la précision du champ affiché.
        original = self.instance if self.instance.pk else None
        date_changed = original is None or (
            original.publication_date.replace(second=0, microsecond=0)
            != date.replace(second=0, microsecond=0)
            if date
            else True
        )
        status_changed = original is None or original.status != status
        if date and status and (date_changed or status_changed):
            now = timezone.now()
            if status == Publication.Status.SCHEDULED and date <= now:
                self.add_error(
                    "publication_date", "Une publication programmée doit avoir une date future."
                )
            elif status == Publication.Status.PUBLISHED and date > now:
                self.add_error(
                    "publication_date",
                    "Une publication publiée ne peut pas avoir une date future : "
                    "choisissez le statut « Programmée ».",
                )
        return cleaned
