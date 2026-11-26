from django.core.validators import RegexValidator
from django.db import models
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
