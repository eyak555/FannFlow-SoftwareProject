from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Venue(models.Model):
    name = models.CharField("nom", max_length=150)
    type = models.CharField("type", max_length=100)
    address = models.CharField("adresse", max_length=250)
    latitude = models.DecimalField(
        "latitude", max_digits=9, decimal_places=6, blank=True, null=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        "longitude", max_digits=9, decimal_places=6, blank=True, null=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    capacity = models.PositiveIntegerField("capacité", validators=[MinValueValidator(1)])
    surface = models.DecimalField(
        "surface (m²)", max_digits=10, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    parking_capacity = models.PositiveIntegerField("places de parking", default=0)
    accessibility = models.BooleanField("accessible aux personnes à mobilité réduite", default=False)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "lieu"
        verbose_name_plural = "lieux"
        constraints = [
            models.CheckConstraint(condition=models.Q(capacity__gt=0), name="venue_capacity_positive"),
            models.CheckConstraint(
                condition=(
                    models.Q(latitude__isnull=True, longitude__isnull=True)
                    | models.Q(
                        latitude__isnull=False, longitude__isnull=False,
                        latitude__range=(-90, 90), longitude__range=(-180, 180),
                    )
                ),
                name="venue_valid_coordinates",
            ),
            models.CheckConstraint(
                condition=models.Q(surface__isnull=True) | models.Q(surface__gt=0),
                name="venue_surface_positive",
            ),
        ]

    def clean(self):
        super().clean()
        if self.latitude is None and self.longitude is not None:
            raise ValidationError({"latitude": "Renseignez aussi la latitude."})
        if self.longitude is None and self.latitude is not None:
            raise ValidationError({"longitude": "Renseignez aussi la longitude."})

    def __str__(self):
        return self.name


class Resource(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Opérationnelle"
        MAINTENANCE = "maintenance", "En maintenance"
        UNAVAILABLE = "unavailable", "Hors service"

    name = models.CharField("nom", max_length=150)
    type = models.CharField("type", max_length=100)
    quantity = models.PositiveIntegerField("quantité en stock", default=0)
    unit_cost = models.DecimalField(
        "coût unitaire", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    location = models.CharField("emplacement", max_length=200)
    status = models.CharField("état", max_length=16, choices=Status, default=Status.AVAILABLE)
    low_stock_threshold = models.PositiveIntegerField("seuil de stock bas", default=2, blank=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "ressource"
        verbose_name_plural = "ressources"
        constraints = [
            models.CheckConstraint(condition=models.Q(unit_cost__gte=0), name="resource_cost_nonnegative"),
        ]

    def __str__(self):
        return self.name

    @property
    def bookable_quantity(self):
        return self.quantity if self.status == self.Status.AVAILABLE else 0


class EventRequirements(models.Model):
    event_id = models.PositiveBigIntegerField(
        "identifiant de l’événement", primary_key=True, validators=[MinValueValidator(1)],
    )
    name = models.CharField("nom de l’événement", max_length=200)
    program_event = models.OneToOneField(
        "events_program.Event", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="operations_requirements", verbose_name="événement du programme",
    )
    venue = models.ForeignKey(
        Venue, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="event_requirements", verbose_name="lieu prévu",
    )
    attendees = models.PositiveIntegerField(
        "participants attendus", null=True, blank=True, validators=[MinValueValidator(1)],
    )
    minimum_surface = models.DecimalField(
        "surface minimale (m²)", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    parking_spaces = models.PositiveIntegerField("places de parking requises", default=0, blank=True)
    needs_accessibility = models.BooleanField("accessibilité PMR requise", default=False)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "fiche de besoins événementiels"
        verbose_name_plural = "fiches de besoins événementiels"

    def __str__(self):
        return self.name


class ResourceAllocation(models.Model):
    resource = models.ForeignKey(
        Resource, on_delete=models.PROTECT, related_name="allocations", verbose_name="ressource",
    )
    event_id = models.PositiveBigIntegerField("identifiant de l’événement", validators=[MinValueValidator(1)])
    program_event = models.ForeignKey(
        "events_program.Event", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="resource_allocations", verbose_name="événement du programme",
    )
    quantity = models.PositiveIntegerField("quantité à allouer", validators=[MinValueValidator(1)])
    start_time = models.DateTimeField("début")
    end_time = models.DateTimeField("fin")
    used_quantity = models.PositiveIntegerField("quantité utilisée", null=True, blank=True)

    class Meta:
        ordering = ["-start_time", "-pk"]
        verbose_name = "allocation de ressource"
        verbose_name_plural = "allocations de ressources"
        indexes = [
            models.Index(fields=["resource", "end_time"], name="allocation_resource_end_idx"),
            models.Index(fields=["event_id"], name="allocation_event_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(event_id__gt=0), name="allocation_event_positive"),
            models.CheckConstraint(
                condition=models.Q(program_event__isnull=True) | models.Q(event_id=models.F("program_event_id")),
                name="allocation_program_event_matches_reference",
            ),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="allocation_quantity_positive"),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="allocation_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(used_quantity__isnull=True) | models.Q(used_quantity__lte=models.F("quantity")),
                name="allocation_used_within_quantity",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors["end_time"] = "La fin doit être postérieure au début."
        if self.used_quantity is not None:
            if self.quantity is not None and self.used_quantity > self.quantity:
                errors["used_quantity"] = "La quantité utilisée ne peut pas dépasser la quantité allouée."
            elif self.start_time and self.start_time > timezone.now():
                errors["used_quantity"] = "La consommation peut être renseignée dès le début de l’allocation."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.resource} · Événement n° {self.event_id}"
