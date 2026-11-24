from django.db import models
from django.conf import settings


class Registration(models.Model):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_CONFIRMED, "Confirmée"),
        (STATUS_CANCELLED, "Annulée"),
    ]

    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_REFUNDED = "refunded"
    PAYMENT_CHOICES = [
        (PAYMENT_PENDING, "En attente"),
        (PAYMENT_PAID, "Payé"),
        (PAYMENT_REFUNDED, "Remboursé"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="registrations",
        verbose_name="Participant",
    )
    event_id = models.PositiveIntegerField(verbose_name="Événement")
    registration_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d’inscription",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="Statut",
    )
    ticket_type = models.CharField(
        max_length=50,
        verbose_name="Type de billet",
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default=PAYMENT_PENDING,
        verbose_name="Paiement",
    )

    class Meta:
        ordering = ["-registration_date"]
        verbose_name = "Inscription"
        verbose_name_plural = "Inscriptions"

    def __str__(self):
        return f"{self.user} — Événement {self.event_id}"


class Ticket(models.Model):
    CATEGORY_STANDARD = "standard"
    CATEGORY_VIP = "vip"
    CATEGORY_GROUP = "group"
    CATEGORY_CHOICES = [
        (CATEGORY_STANDARD, "Standard"),
        (CATEGORY_VIP, "VIP"),
        (CATEGORY_GROUP, "Groupe"),
    ]

    STATUS_AVAILABLE = "available"
    STATUS_PENDING = "pending"
    STATUS_USED = "used"
    STATUS_CANCELLED = "cancelled"
    STATUS_REFUND = "refunded"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_AVAILABLE, "Disponible"),
        (STATUS_USED, "Utilisé"),
        (STATUS_CANCELLED, "Annulé"),
        (STATUS_REFUND, "Remboursé"),
    ]

    registration = models.ForeignKey(
        Registration,
        on_delete=models.CASCADE,
        related_name="tickets",
        verbose_name="Inscription",
    )
    qr_code = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Code QR",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix",
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_STANDARD,
        verbose_name="Catégorie",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_AVAILABLE,
        verbose_name="Statut",
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "Billet"
        verbose_name_plural = "Billets"

    def __str__(self):
        return f"{self.category} — {self.qr_code}"


class Attendance(models.Model):
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="attendances",
        verbose_name="Billet",
    )
    check_in = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Entrée",
    )
    check_out = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Sortie",
    )
    gate = models.CharField(
        max_length=100,
        verbose_name="Point d’accès",
    )

    class Meta:
        ordering = ["-check_in"]
        verbose_name = "Présence"
        verbose_name_plural = "Présences"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.check_out and self.check_in and self.check_out < self.check_in:
            raise ValidationError(
                {"check_out": "La sortie ne peut pas précéder l’entrée."}
            )

    def __str__(self):
        return f"{self.ticket} — {self.gate}"


class AccessPoint(models.Model):
    event_id = models.PositiveIntegerField(verbose_name="Événement")
    name = models.CharField(
        max_length=100,
        verbose_name="Nom",
    )
    location = models.CharField(
        max_length=255,
        verbose_name="Localisation",
    )
    capacity = models.PositiveIntegerField(verbose_name="Capacité")

    class Meta:
        ordering = ["name"]
        verbose_name = "Point d’accès"
        verbose_name_plural = "Points d’accès"

    def __str__(self):
        return f"{self.name} — Événement {self.event_id}"
