import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.templatetags.static import static

from resources_operations.models import Venue

EVENT_IMAGE_MAX_SIZE = 5 * 1024 * 1024
EVENT_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]


def event_image_upload_to(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    category = slugify(instance.category or "autre") or "autre"
    return f"events/{category}/{uuid.uuid4().hex}{extension}"


def validate_event_image_size(image):
    if image.size > EVENT_IMAGE_MAX_SIZE:
        raise ValidationError("L’image de l’événement ne doit pas dépasser 5 Mo.")


class Event(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        PUBLISHED = "published", "Publié"
        CANCELLED = "cancelled", "Annulé"

    class EventType(models.TextChoices):
        FESTIVAL = "festival", "Festival"
        CONCERT = "concert", "Concert"
        SHOW = "spectacle", "Spectacle"
        EXHIBITION = "exposition", "Exposition"
        CONFERENCE = "conference", "Conférence"
        WORKSHOP = "atelier", "Atelier"
        OTHER = "autre", "Autre"

    class Category(models.TextChoices):
        HACKATHON = "hackathon", "Hackathon"
        MUSIC = "music_festival", "Festival de musique"
        CINEMA = "film_festival", "Festival de cinéma"
        CONFERENCE = "conference", "Conférence"
        CULTURAL = "cultural", "Événement culturel"
        WORKSHOP = "workshop", "Atelier"
        OTHER = "other", "Autre"

    title = models.CharField("titre", max_length=200)
    description = models.TextField("description")
    event_type = models.CharField("type", max_length=20, choices=EventType.choices)
    category = models.CharField(
        "catégorie",
        max_length=80,
        default=Category.OTHER,
    )
    start_date = models.DateTimeField("début")
    end_date = models.DateTimeField("fin")
    registration_deadline = models.DateTimeField("date limite d’inscription")
    capacity = models.PositiveIntegerField(
        "capacité",
        validators=[MinValueValidator(1, message="La capacité doit être au moins égale à 1.")],
    )
    ticket_price = models.DecimalField(
        "prix du billet Standard (DT)",
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0, message="Le prix ne peut pas être négatif.")],
    )
    vip_ticket_price = models.DecimalField(
        "prix du billet VIP (DT)",
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0, message="Le prix ne peut pas être négatif.")],
        help_text="Tarif appliqué lorsque le participant choisit un billet VIP.",
    )
    minimum_age = models.PositiveSmallIntegerField(
        "âge minimum",
        null=True,
        blank=True,
        validators=[MaxValueValidator(120)],
        help_text="Laisser vide si aucun âge minimum ne s’applique.",
    )
    maximum_age = models.PositiveSmallIntegerField(
        "âge maximum",
        null=True,
        blank=True,
        validators=[MaxValueValidator(120)],
        help_text="Laisser vide si aucun âge maximum ne s’applique.",
    )
    location = models.CharField("lieu", max_length=255)
    venue = models.ForeignKey(
        Venue,
        verbose_name="lieu enregistré",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="events",
    )
    image = models.ImageField(
        "image de l’événement",
        upload_to=event_image_upload_to,
        blank=True,
        validators=[
            FileExtensionValidator(EVENT_IMAGE_EXTENSIONS),
            validate_event_image_size,
        ],
        help_text="JPG, PNG ou WEBP, 5 Mo maximum. Une illustration par catégorie est utilisée par défaut.",
    )
    director = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="responsable",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="directed_events",
    )
    status = models.CharField(
        "statut de publication",
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    class Meta:
        ordering = ["start_date", "title"]
        verbose_name = "événement"
        verbose_name_plural = "événements"

    def clean(self):
        super().clean()
        errors = {}
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            errors["end_date"] = "La date de fin doit être postérieure à la date de début."
        if (
            self.start_date
            and self.registration_deadline
            and self.registration_deadline > self.start_date
        ):
            errors["registration_deadline"] = (
                "La date limite d’inscription doit être antérieure ou égale au début de l’événement."
            )
        if (
            self.minimum_age is not None
            and self.maximum_age is not None
            and self.minimum_age > self.maximum_age
        ):
            errors["maximum_age"] = "L’âge maximum doit être supérieur ou égal à l’âge minimum."
        if self.pk and self.capacity is not None:
            from registration_access.models import Registration

            registered = (
                Registration.objects.filter(event_id=self.pk)
                .exclude(status=Registration.STATUS_CANCELLED)
                .count()
            )
            if self.capacity < registered:
                errors["capacity"] = (
                    "La capacité ne peut pas être inférieure au nombre d’inscriptions actives."
                )
        if self.pk and self.start_date and self.end_date:
            if self.activities.filter(
                Q(start_time__lt=self.start_date) | Q(end_time__gt=self.end_date)
            ).exists():
                errors["start_date"] = (
                    "Les dates de l’événement doivent inclure toutes les activités programmées."
                )
        if errors:
            raise ValidationError(errors)

    @property
    def lifecycle_status(self):
        if self.status == self.Status.DRAFT:
            return "draft"
        if self.status == self.Status.CANCELLED:
            return "cancelled"
        now = timezone.now()
        if self.start_date > now:
            return "upcoming"
        if self.end_date >= now:
            return "ongoing"
        return "completed"

    @property
    def lifecycle_status_label(self):
        return {
            "draft": "Brouillon",
            "published": "Publié",
            "cancelled": "Annulé",
            "upcoming": "À venir",
            "ongoing": "En cours",
            "completed": "Terminé",
        }[self.lifecycle_status]

    @property
    def display_image_url(self):
        if self.image:
            try:
                return self.image.url
            except ValueError:
                pass
        image_name = {
            self.Category.HACKATHON: "hackathon",
            self.Category.MUSIC: "music",
            self.Category.CINEMA: "cinema",
            self.Category.CONFERENCE: "conference",
            self.Category.CULTURAL: "cultural",
            self.Category.WORKSHOP: "workshop",
            self.Category.OTHER: "cultural",
        }.get(self.category, "cultural")
        return static(f"events_program/images/{image_name}.svg")

    @property
    def age_requirement_display(self):
        if self.minimum_age is not None and self.maximum_age is not None:
            return f"De {self.minimum_age} à {self.maximum_age} ans"
        if self.minimum_age is not None:
            return f"À partir de {self.minimum_age} ans"
        if self.maximum_age is not None:
            return f"Jusqu’à {self.maximum_age} ans"
        return "Tous âges"

    @property
    def category_display(self):
        return dict(self.Category.choices).get(self.category, self.category)

    def age_access_error(self, user):
        if self.minimum_age is None and self.maximum_age is None:
            return ""
        if not user or not user.is_authenticated or not user.birth_date:
            return "Renseignez votre date de naissance dans votre profil pour vérifier l’accès à cet événement."
        event_day = timezone.localtime(self.start_date).date()
        age = event_day.year - user.birth_date.year
        if (event_day.month, event_day.day) < (user.birth_date.month, user.birth_date.day):
            age -= 1
        if self.minimum_age is not None and age < self.minimum_age:
            return f"Cet événement est réservé aux personnes de {self.minimum_age} ans et plus."
        if self.maximum_age is not None and age > self.maximum_age:
            return f"L’accès à cet événement est limité aux personnes de {self.maximum_age} ans maximum."
        return ""

    def save(self, *args, **kwargs):
        previous_image = ""
        if self.pk:
            previous_image = (
                type(self).objects.filter(pk=self.pk)
                .values_list("image", flat=True)
                .first()
                or ""
            )
        current_image = self.image.name if self.image else ""
        super().save(*args, **kwargs)
        if previous_image and previous_image != current_image:
            storage = self.image.storage
            transaction.on_commit(lambda: storage.delete(previous_image))

    def delete(self, *args, **kwargs):
        image_name = self.image.name if self.image else ""
        storage = self.image.storage
        result = super().delete(*args, **kwargs)
        if image_name:
            transaction.on_commit(lambda: storage.delete(image_name))
        return result

    def get_absolute_url(self):
        return reverse("core:event_detail", args=[self.pk])

    def __str__(self):
        return self.title


class Speaker(models.Model):
    name = models.CharField("nom", max_length=150)
    bio = models.TextField("biographie", blank=True)
    organization = models.CharField("organisation", max_length=150, blank=True)
    country = models.CharField("pays", max_length=100, blank=True)
    expertise = models.CharField("expertise", max_length=200, blank=True)
    email = models.EmailField("email", blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "intervenant"
        verbose_name_plural = "intervenants"

    def __str__(self):
        return self.name


class Activity(models.Model):
    event = models.ForeignKey(
        Event,
        verbose_name="événement",
        on_delete=models.CASCADE,
        related_name="activities",
    )
    title = models.CharField("titre", max_length=200)
    description = models.TextField("description", blank=True)
    activity_type = models.CharField("type", max_length=100)
    start_time = models.DateTimeField("début")
    end_time = models.DateTimeField("fin")
    capacity = models.PositiveIntegerField(
        "capacité",
        null=True,
        blank=True,
        validators=[MinValueValidator(1, message="La capacité doit être au moins égale à 1.")],
    )
    room = models.CharField("salle", max_length=150, blank=True)
    speakers = models.ManyToManyField(
        Speaker,
        through="ActivitySpeaker",
        related_name="activities",
        verbose_name="intervenants",
        blank=True,
    )

    class Meta:
        ordering = ["start_time", "title"]
        verbose_name = "activité"
        verbose_name_plural = "activités"

    def clean(self):
        super().clean()
        errors = {}
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors["end_time"] = "La fin doit être postérieure au début de l’activité."
        if self.event_id and self.start_time and self.end_time:
            event = self.event
            if self.start_time < event.start_date or self.end_time > event.end_date:
                errors["start_time"] = (
                    "L’activité doit être comprise dans les dates de son événement."
                )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.title} — {self.event}"


class ActivitySpeaker(models.Model):
    activity = models.ForeignKey(
        Activity,
        verbose_name="activité",
        on_delete=models.CASCADE,
        related_name="speaker_assignments",
    )
    speaker = models.ForeignKey(
        Speaker,
        verbose_name="intervenant",
        on_delete=models.CASCADE,
        related_name="activity_assignments",
    )

    class Meta:
        ordering = ["activity", "speaker"]
        verbose_name = "affectation d’intervenant"
        verbose_name_plural = "affectations d’intervenants"
        constraints = [
            models.UniqueConstraint(
                fields=("activity", "speaker"),
                name="unique_activity_speaker",
            )
        ]

    def __str__(self):
        return f"{self.speaker} — {self.activity}"
