from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Venue(models.Model):
    class VenueType(models.TextChoices):
        CULTURAL_CENTER = "cultural_center", "Centre culturel"
        THEATER = "theater", "Théâtre"
        CONCERT_HALL = "concert_hall", "Salle de spectacle"
        OUTDOOR = "outdoor", "Plein air"
        OTHER = "other", "Autre"

    name = models.CharField("nom", max_length=150)
    venue_type = models.CharField(
        "type de lieu",
        max_length=30,
        choices=VenueType.choices,
        default=VenueType.OTHER,
    )
    address = models.CharField("adresse", max_length=255)
    city = models.CharField("ville", max_length=100)
    latitude = models.DecimalField(
        "latitude",
        max_digits=8,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        "longitude",
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    capacity = models.PositiveIntegerField("capacité", null=True, blank=True)
    surface = models.DecimalField(
        "surface (m²)",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    parking_capacity = models.PositiveIntegerField(
        "capacité du parking",
        null=True,
        blank=True,
    )
    accessibility = models.TextField("accessibilité", blank=True)

    class Meta:
        ordering = ["city", "name"]
        verbose_name = "lieu"
        verbose_name_plural = "lieux"

    def clean(self):
        super().clean()
        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError(
                {
                    "latitude": "Renseignez ensemble la latitude et la longitude.",
                    "longitude": "Renseignez ensemble la latitude et la longitude.",
                }
            )

    def __str__(self):
        return f"{self.name} — {self.city}"
