import os
import uuid

from django.core.validators import RegexValidator
from django.db import models, transaction
from django.urls import reverse


phone_validator = RegexValidator(
    regex=r"^\+?[0-9][0-9 .()\-]{5,19}$",
    message=(
        "Saisissez un numéro valide : chiffres, espaces, points, tirets "
        "ou parenthèses, avec un « + » facultatif au début."
    ),
)


class MediaContact(models.Model):
    """Contact de l'annuaire presse (entité « Contact média » du module 6).

    Le contact est indépendant des événements : aucun lien vers Event.
    """

    class Role(models.TextChoices):
        JOURNALIST = "journaliste", "Journaliste"
        EDITOR = "redaction", "Rédaction en chef"
        PHOTOGRAPHER = "photographe", "Photographe"
        VIDEOGRAPHER = "videaste", "Vidéaste"
        PRESS_OFFICER = "attache_presse", "Attaché·e de presse"
        INFLUENCER = "influenceur", "Influenceur·se"
        OTHER = "autre", "Autre"

    name = models.CharField("nom", max_length=150)
    organization = models.CharField("organisation", max_length=150, blank=True)
    email = models.EmailField("adresse e-mail", max_length=254, blank=True)
    phone = models.CharField(
        "téléphone", max_length=20, blank=True, validators=[phone_validator]
    )
    role = models.CharField(
        "rôle", max_length=20, choices=Role.choices, default=Role.JOURNALIST
    )
    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        verbose_name = "contact média"
        verbose_name_plural = "contacts médias"
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("communication_media:media_contact_detail", args=[self.pk])

    @property
    def phone_href(self):
        """Numéro sans séparateurs, pour un lien ``tel:``."""
        return "".join(ch for ch in self.phone if ch.isdigit() or ch == "+")


# --- Liens vers les événements ---------------------------------------------
#
# Communication, Média, Dossier de presse et Publication sont rattachés à un
# événement (Id_event du cahier des charges) par une vraie clé étrangère vers
# ``events_program.Event``.
#
# - La colonne accepte NULL : les lignes créées avant l'intégration d'Event
#   (migration 0002) restent valides. Les formulaires, eux, exigent un
#   événement : toute création ou modification en choisit un.
# - SET_NULL à la suppression : le module Événements supprime ses événements
#   par ``delete()`` sans gérer d'erreur ; PROTECT y provoquerait une erreur
#   500 et CASCADE effacerait les contenus de communication sans prévenir.


def event_link(related_name):
    return models.ForeignKey(
        "events_program.Event",
        verbose_name="événement",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name=related_name,
    )


class Communication(models.Model):
    """Communiqué ou contenu officiel (entité « Communication »)."""

    class Type(models.TextChoices):
        PRESS_RELEASE = "communique", "Communiqué de presse"
        ANNOUNCEMENT = "annonce", "Annonce officielle"
        NEWSLETTER = "newsletter", "Newsletter"
        INFORMATION = "note", "Note d’information"
        INVITATION = "invitation", "Invitation presse"

    class Language(models.TextChoices):
        FRENCH = "fr", "Français"
        ARABIC = "ar", "Arabe"
        ENGLISH = "en", "Anglais"

    class Status(models.TextChoices):
        DRAFT = "brouillon", "Brouillon"
        VALIDATED = "valide", "Validé"
        PUBLISHED = "publie", "Publié"
        ARCHIVED = "archive", "Archivé"

    title = models.CharField("titre", max_length=200)
    content = models.TextField("contenu")
    type = models.CharField(
        "type", max_length=20, choices=Type.choices, default=Type.PRESS_RELEASE
    )
    language = models.CharField(
        "langue", max_length=2, choices=Language.choices, default=Language.FRENCH
    )
    status = models.CharField(
        "statut", max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    publication_date = models.DateTimeField("date de publication", null=True, blank=True)
    event = event_link("communications")
    created_at = models.DateTimeField("créée le", auto_now_add=True)
    updated_at = models.DateTimeField("modifiée le", auto_now=True)

    class Meta:
        verbose_name = "communication"
        verbose_name_plural = "communications"
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("communication_media:communication_detail", args=[self.pk])


# Règles des fichiers médias, sur le modèle de la photo de profil du projet
# (extensions + taille maximale + nom aléatoire). Pillow n'étant pas installé,
# le contenu réel est contrôlé par la signature des premiers octets (forms.py).
MEGABYTE = 1024 * 1024

MEDIA_FILE_RULES = {
    "image": {"extensions": ["jpg", "jpeg", "png", "webp"], "max_size": 5 * MEGABYTE},
    "affiche": {"extensions": ["jpg", "jpeg", "png", "webp", "pdf"], "max_size": 10 * MEGABYTE},
    "video": {"extensions": ["mp4", "webm"], "max_size": 50 * MEGABYTE},
    "document": {"extensions": ["pdf", "docx"], "max_size": 10 * MEGABYTE},
}

MEDIA_EXTENSIONS = sorted(
    {ext for rule in MEDIA_FILE_RULES.values() for ext in rule["extensions"]}
)


def media_upload_to(instance, filename):
    """Nom de fichier aléatoire : le nom fourni est conservé à part."""
    extension = os.path.splitext(filename)[1].lower()
    folder = instance.media_type or "autre"
    return f"communication_media/{folder}/{uuid.uuid4().hex}{extension}"


class Media(models.Model):
    """Image, affiche, vidéo ou document (entité « Média »)."""

    class Type(models.TextChoices):
        IMAGE = "image", "Image"
        POSTER = "affiche", "Affiche"
        VIDEO = "video", "Vidéo"
        DOCUMENT = "document", "Document"

    name = models.CharField("nom", max_length=150)
    media_type = models.CharField("type", max_length=10, choices=Type.choices)
    file = models.FileField("fichier", upload_to=media_upload_to, max_length=255)
    original_filename = models.CharField(
        "nom du fichier d’origine", max_length=255, editable=False, default=""
    )
    format = models.CharField("format", max_length=10, editable=False, default="")
    size = models.PositiveBigIntegerField("taille (octets)", editable=False, default=0)
    event = event_link("media_files")
    communication = models.ForeignKey(
        Communication,
        verbose_name="communication liée",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="media",
    )
    uploaded_at = models.DateTimeField("téléversé le", auto_now_add=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        verbose_name = "média"
        verbose_name_plural = "médias"
        ordering = ["-uploaded_at", "-pk"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("communication_media:media_detail", args=[self.pk])

    @property
    def url(self):
        """Adresse du fichier, servie par la vue protégée du module."""
        return reverse("communication_media:media_file", args=[self.pk])

    @property
    def is_image(self):
        return self.format in {"JPG", "JPEG", "PNG", "WEBP"}

    @property
    def is_video(self):
        return self.format in {"MP4", "WEBM"}

    @property
    def is_pdf(self):
        return self.format == "PDF"

    def save(self, *args, **kwargs):
        previous_name = None
        if self.pk:
            previous_name = (
                Media.objects.filter(pk=self.pk).values_list("file", flat=True).first()
            )
        # Nouveau fichier (envoi non encore écrit, ou fichier déjà écrit par
        # ``file.save(..., save=False)``) : les métadonnées sont recalculées.
        new_file = self.file and (
            not self.file._committed or self.file.name != previous_name or not self.format
        )
        if new_file:
            if not self.file._committed or not self.original_filename:
                self.original_filename = os.path.basename(self.file.name)[:255]
            self.format = os.path.splitext(self.file.name)[1].lstrip(".").upper()
            self.size = self.file.size
        super().save(*args, **kwargs)
        # Fichier remplacé : l'ancien est supprimé une fois la base à jour.
        if previous_name and previous_name != self.file.name:
            storage = self.file.storage
            transaction.on_commit(lambda: storage.delete(previous_name))

    def delete(self, *args, **kwargs):
        storage, name = self.file.storage, self.file.name
        result = super().delete(*args, **kwargs)
        if name:
            transaction.on_commit(lambda: storage.delete(name))
        return result


class PressKit(models.Model):
    """Dossier de presse (entité « Dossier de presse »)."""

    title = models.CharField("titre", max_length=200)
    description = models.TextField("description")
    event = event_link("press_kits")
    communications = models.ManyToManyField(
        Communication,
        verbose_name="communications incluses",
        blank=True,
        related_name="press_kits",
    )
    media = models.ManyToManyField(
        Media,
        verbose_name="médias inclus",
        blank=True,
        related_name="press_kits",
    )
    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        verbose_name = "dossier de presse"
        verbose_name_plural = "dossiers de presse"
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("communication_media:press_kit_detail", args=[self.pk])


class Publication(models.Model):
    """Publication sur un réseau social ou un site (entité « Publication »)."""

    class Platform(models.TextChoices):
        FACEBOOK = "facebook", "Facebook"
        INSTAGRAM = "instagram", "Instagram"
        X = "x", "X (Twitter)"
        LINKEDIN = "linkedin", "LinkedIn"
        TIKTOK = "tiktok", "TikTok"
        YOUTUBE = "youtube", "YouTube"
        WEBSITE = "site_web", "Site web FannFlow"
        OTHER = "autre", "Autre"

    class Status(models.TextChoices):
        DRAFT = "brouillon", "Brouillon"
        SCHEDULED = "programmee", "Programmée"
        PUBLISHED = "publiee", "Publiée"
        CANCELLED = "annulee", "Annulée"

    CONTENT_MAX_LENGTH = 5000
    # Limite de caractères imposée par certaines plateformes.
    PLATFORM_MAX_LENGTH = {"x": 280}

    platform = models.CharField("plateforme", max_length=12, choices=Platform.choices)
    event = event_link("publications")
    content = models.TextField("contenu", max_length=CONTENT_MAX_LENGTH)
    publication_date = models.DateTimeField("date de publication")
    status = models.CharField(
        "statut", max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    created_at = models.DateTimeField("créée le", auto_now_add=True)
    updated_at = models.DateTimeField("modifiée le", auto_now=True)

    class Meta:
        verbose_name = "publication"
        verbose_name_plural = "publications"
        ordering = ["-publication_date", "-pk"]

    def __str__(self):
        return f"{self.get_platform_display()} — {self.excerpt}"

    def get_absolute_url(self):
        return reverse("communication_media:publication_detail", args=[self.pk])

    @property
    def excerpt(self):
        text = " ".join(self.content.split())
        return text if len(text) <= 60 else f"{text[:57].rstrip()}…"
