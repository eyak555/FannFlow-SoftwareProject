from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


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
    name = models.CharField("nom", max_length=150)
    type = models.CharField("type", max_length=100)
    quantity = models.PositiveIntegerField("quantité en stock", default=0)
    unit_cost = models.DecimalField(
        "coût unitaire", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    location = models.CharField("emplacement", max_length=200)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "ressource"
        verbose_name_plural = "ressources"
        constraints = [
            models.CheckConstraint(condition=models.Q(unit_cost__gte=0), name="resource_cost_nonnegative"),
        ]

    def __str__(self):
        return self.name


class ResourceAllocation(models.Model):
    resource = models.ForeignKey(
        Resource, on_delete=models.PROTECT, related_name="allocations", verbose_name="ressource",
    )
    # La relation pourra devenir une clé étrangère lorsque le modèle Event du M2 existera.
    event_id = models.PositiveBigIntegerField("identifiant de l’événement", validators=[MinValueValidator(1)])
    quantity = models.PositiveIntegerField("quantité à allouer", validators=[MinValueValidator(1)])
    start_time = models.DateTimeField("début")
    end_time = models.DateTimeField("fin")

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
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="allocation_quantity_positive"),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="allocation_end_after_start",
            ),
        ]

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "La fin doit être postérieure au début."})

    def __str__(self):
        return f"{self.resource} · Événement n° {self.event_id}"
