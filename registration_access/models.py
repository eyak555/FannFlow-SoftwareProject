from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
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

    TICKET_TYPE_STANDARD = "standard"
    TICKET_TYPE_VIP = "vip"
    TICKET_TYPE_GROUP = "group"
    TICKET_TYPE_CHOICES = [
        (TICKET_TYPE_STANDARD, "Standard"),
        (TICKET_TYPE_VIP, "VIP"),
        (TICKET_TYPE_GROUP, "Groupe"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="registrations",
        verbose_name="Participant",
    )
    event_id = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Événement",
    )
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
        max_length=20,
        choices=TICKET_TYPE_CHOICES,
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

    def clean(self):
        super().clean()
        if self.pk:
            previous = Registration.objects.filter(pk=self.pk).first()
            has_used_ticket = self.tickets.filter(status=Ticket.STATUS_USED).exists()
            if has_used_ticket and previous and (
                self.user_id != previous.user_id
                or self.event_id != previous.event_id
                or self.ticket_type != previous.ticket_type
                or self.status != previous.status
                or self.payment_status != previous.payment_status
            ):
                raise ValidationError(
                    "Une inscription avec un billet déjà utilisé ne peut plus être modifiée."
                )
            has_attendance = self.tickets.filter(attendances__isnull=False).exists()
            if has_attendance and self.event_id != previous.event_id:
                raise ValidationError(
                    "L’événement d’une inscription ayant des présences liées ne peut pas être modifié."
                )

    def __str__(self):
        return f"{self.user} — Événement {self.event_id}"


class Ticket(models.Model):
    CATEGORY_STANDARD = Registration.TICKET_TYPE_STANDARD
    CATEGORY_VIP = Registration.TICKET_TYPE_VIP
    CATEGORY_GROUP = Registration.TICKET_TYPE_GROUP
    CATEGORY_CHOICES = Registration.TICKET_TYPE_CHOICES

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
    code = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        editable=False,
        verbose_name="Code billet",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(
                0,
                message="Le prix du billet ne peut pas être négatif.",
            )
        ],
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

    def clean(self):
        super().clean()
        if self.registration_id:
            registration = self.registration
            if self.status == self.STATUS_AVAILABLE:
                if registration.status != Registration.STATUS_CONFIRMED:
                    raise ValidationError({
                        "status": "Le billet ne peut pas être disponible avant la confirmation de l’inscription."
                    })
                if registration.payment_status == Registration.PAYMENT_REFUNDED:
                    raise ValidationError({
                        "status": "Un billet remboursé ne peut pas être disponible."
                    })
                if (
                    self.price is not None
                    and self.price > 0
                    and registration.payment_status != Registration.PAYMENT_PAID
                ):
                    raise ValidationError({
                        "status": "Le billet payant ne peut pas être disponible avant le paiement."
                    })
            elif self.status == self.STATUS_CANCELLED and registration.status != Registration.STATUS_CANCELLED:
                raise ValidationError({
                    "status": "L’inscription associée doit être annulée."
                })
            elif self.status == self.STATUS_REFUND and registration.payment_status != Registration.PAYMENT_REFUNDED:
                raise ValidationError({
                    "status": "Le remboursement doit être enregistré sur l’inscription."
                })
            elif self.status == self.STATUS_USED:
                if registration.status != Registration.STATUS_CONFIRMED or (
                    self.price is not None
                    and self.price > 0
                    and registration.payment_status != Registration.PAYMENT_PAID
                ):
                    raise ValidationError({
                        "status": "Un billet ne peut être utilisé que si l’inscription est confirmée et payée."
                    })
                if not self.attendances.filter(check_in__isnull=False).exists():
                    raise ValidationError({
                        "status": "Le statut « Utilisé » nécessite une entrée enregistrée."
                    })
            elif self.status == self.STATUS_PENDING and (
                registration.status == Registration.STATUS_CANCELLED
                or registration.payment_status == Registration.PAYMENT_REFUNDED
                or (
                    registration.status == Registration.STATUS_CONFIRMED
                    and (
                        self.price == 0
                        or registration.payment_status == Registration.PAYMENT_PAID
                    )
                )
            ):
                raise ValidationError({
                    "status": "Le statut du billet ne correspond pas à l’inscription et au paiement."
                })
        if not self.pk:
            return
        previous = Ticket.objects.filter(pk=self.pk).first()
        if previous and previous.status == self.STATUS_USED and any(
            getattr(self, field_name) != getattr(previous, field_name)
            for field_name in ("registration_id", "code", "price", "category")
        ):
            raise ValidationError(
                "Un billet déjà utilisé ne peut pas être modifié."
            )

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.code = ""
            using = kwargs.get("using") or self._state.db
            with transaction.atomic(using=using):
                super().save(*args, **kwargs)
                self.code = f"FF-{self.pk:06d}"
                super().save(using=using, update_fields=["code"])
            return
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_category_display()} — {self.code}"


class Attendance(models.Model):
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.PROTECT,
        related_name="attendances",
        verbose_name="Billet",
    )
    access_point = models.ForeignKey(
        "AccessPoint",
        on_delete=models.PROTECT,
        related_name="attendances",
        verbose_name="Point d’accès",
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
    class Meta:
        ordering = ["-check_in"]
        verbose_name = "Présence"
        verbose_name_plural = "Présences"

    def clean(self):
        super().clean()

        if self.check_out and self.check_in and self.check_out < self.check_in:
            raise ValidationError(
                {"check_out": "La sortie ne peut pas précéder l’entrée."}
            )
        if self.check_out and not self.check_in:
            raise ValidationError(
                {"check_out": "Une sortie ne peut pas être enregistrée sans entrée."}
            )
        if not self.ticket_id or not self.access_point_id:
            return

        if self.ticket.registration.event_id != self.access_point.event_id:
            raise ValidationError({
                "access_point": "Ce point d’accès appartient à un autre événement que le billet."
            })

        previous = Attendance.objects.filter(pk=self.pk).first() if self.pk else None
        if previous and previous.check_in:
            if (
                self.ticket_id != previous.ticket_id
                or self.access_point_id != previous.access_point_id
                or self.check_in != previous.check_in
            ):
                raise ValidationError(
                    "Une entrée déjà enregistrée ne peut pas être déplacée ni modifiée."
                )
            if previous.check_out and self.check_out != previous.check_out:
                raise ValidationError({
                    "check_out": "Une sortie déjà enregistrée ne peut pas être modifiée."
                })

        if not self.check_in or (previous and previous.check_in):
            return

        registration = self.ticket.registration
        is_registration_valid = (
            registration.status == Registration.STATUS_CONFIRMED
            and registration.payment_status != Registration.PAYMENT_REFUNDED
            and (
                self.ticket.price == 0
                or registration.payment_status == Registration.PAYMENT_PAID
            )
        )
        if self.ticket.status != Ticket.STATUS_AVAILABLE or not is_registration_valid:
            raise ValidationError({
                "ticket": "Seul un billet disponible, confirmé et payé si nécessaire peut être utilisé pour entrer."
            })
        if Attendance.objects.filter(
            ticket_id=self.ticket_id,
            check_in__isnull=False,
        ).exclude(pk=self.pk).exists():
            raise ValidationError({
                "ticket": "Ce billet a déjà été utilisé ; la réentrée n’est pas autorisée."
            })

        current_occupancy = Attendance.objects.filter(
            access_point_id=self.access_point_id,
            check_in__isnull=False,
            check_out__isnull=True,
        ).exclude(pk=self.pk).count()
        if current_occupancy >= self.access_point.capacity:
            raise ValidationError({
                "access_point": "La capacité maximale de ce point d’accès est atteinte."
            })

    def delete(self, *args, **kwargs):
        if self.check_in:
            raise ValidationError(
                "Une présence avec une entrée enregistrée ne peut pas être supprimée."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.ticket} — {self.access_point}"


class AccessPoint(models.Model):
    event_id = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Événement",
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Nom",
    )
    location = models.CharField(
        max_length=255,
        verbose_name="Localisation",
    )
    capacity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Capacité maximale simultanée",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Point d’accès"
        verbose_name_plural = "Points d’accès"

    def clean(self):
        super().clean()
        if self.capacity < 1:
            raise ValidationError({"capacity": "La capacité doit être au moins égale à 1."})
        if self.pk:
            previous = AccessPoint.objects.filter(pk=self.pk).first()
            if previous and self.event_id != previous.event_id and self.attendances.exists():
                raise ValidationError(
                    "L’événement d’un point d’accès ayant des présences liées ne peut pas être modifié."
                )
            if self.capacity < self.current_occupancy:
                raise ValidationError(
                    {"capacity": "La capacité ne peut pas être inférieure au nombre de personnes présentes."}
                )

    @property
    def current_occupancy(self):
        return self.attendances.filter(
            check_in__isnull=False,
            check_out__isnull=True,
        ).count()

    def __str__(self):
        return f"{self.name} — Événement {self.event_id}"
