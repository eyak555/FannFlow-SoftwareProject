from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.forms import FannFlowFormMixin, FannFlowModelForm
from .models import AccessPoint, Attendance, Registration, Ticket


def validate_event_registration(event, user=None):
    from events_program.models import Event

    if event.status != Event.Status.PUBLISHED:
        raise ValidationError("Les inscriptions ne sont ouvertes que pour un événement publié.")
    if event.registration_deadline <= timezone.now():
        raise ValidationError("La période d’inscription à cet événement est terminée.")
    age_error = event.age_access_error(user)
    if age_error:
        raise ValidationError(age_error)
    if (
        Registration.objects.filter(event_id=event.pk)
        .exclude(status=Registration.STATUS_CANCELLED)
        .count()
        >= event.capacity
    ):
        raise ValidationError("La capacité maximale de cet événement est atteinte.")


class RegistrationForm(FannFlowModelForm):
    class Meta:
        model = Registration
        exclude = ("registration_date",)
        error_messages = {
            "user": {
                "required": "Veuillez sélectionner un participant.",
            },
            "event_id": {
                "required": "Veuillez saisir le numéro de l’événement.",
            },
            "ticket_type": {
                "required": "Veuillez choisir un type de billet.",
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event_id"].widget.attrs["min"] = 1

    def clean(self):
        cleaned_data = super().clean()
        event_id = cleaned_data.get("event_id")
        user = cleaned_data.get("user")
        if event_id and user and (
            not self.instance.pk
            or event_id != self.instance.event_id
            or user.pk != self.instance.user_id
        ):
            from events_program.models import Event

            event = Event.objects.filter(pk=event_id).first()
            if event:
                age_error = event.age_access_error(user)
                if age_error:
                    self.add_error("user", age_error)
        status = cleaned_data.get("status")
        payment_status = cleaned_data.get("payment_status")

        if payment_status == Registration.PAYMENT_PAID:
            if status == Registration.STATUS_CANCELLED:
                self.add_error(
                    "payment_status",
                    "Une inscription annulée ne peut pas être marquée comme payée.",
                )
            else:
                cleaned_data["status"] = Registration.STATUS_CONFIRMED
        elif payment_status == Registration.PAYMENT_NOT_REQUIRED:
            has_paid_ticket = (
                not self.instance.pk
                or self.instance.tickets.filter(price__gt=0).exists()
            )
            if status == Registration.STATUS_CANCELLED or has_paid_ticket:
                self.add_error(
                    "payment_status",
                    "« Sans paiement » est réservé aux billets gratuits non annulés.",
                )
            else:
                cleaned_data["status"] = Registration.STATUS_CONFIRMED
        elif payment_status == Registration.PAYMENT_REFUNDED:
            cleaned_data["status"] = Registration.STATUS_CANCELLED
        elif (
            status == Registration.STATUS_CONFIRMED
            and (
                not self.instance.pk
                or self.instance.tickets.filter(price__gt=0).exists()
            )
        ):
            self.add_error(
                "payment_status",
                "Le paiement doit être validé avant de confirmer cette inscription.",
            )

        if self.instance.pk and self.instance.tickets.filter(
            status=Ticket.STATUS_USED
        ).exists():
            if any(
                cleaned_data.get(field_name) != getattr(self.instance, field_name)
                for field_name in (
                    "user",
                    "event_id",
                    "ticket_type",
                    "status",
                    "payment_status",
                )
            ):
                raise forms.ValidationError(
                    "Une inscription avec un billet déjà utilisé ne peut plus être modifiée."
                )
        return cleaned_data


class ParticipantRegistrationForm(FannFlowModelForm):
    class Meta:
        model = Registration
        fields = ("event_id", "ticket_type")
        labels = {
            "event_id": "Numéro de l’événement",
            "ticket_type": "Catégorie de billet souhaitée",
        }
        error_messages = {
            "event_id": {
                "required": "Veuillez saisir le numéro de l’événement.",
            },
            "ticket_type": {
                "required": "Veuillez choisir une catégorie de billet.",
            },
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["event_id"].widget.attrs["min"] = 1

    def clean_event_id(self):
        event_id = self.cleaned_data["event_id"]
        from events_program.models import Event

        event = Event.objects.filter(pk=event_id).first()
        if event is not None:
            validate_event_registration(event, self.user)
        return event_id


class PrototypePaymentForm(forms.Form):
    pass


class FreeTicketConfirmationForm(FannFlowFormMixin, forms.Form):
    confirmation = forms.BooleanField(
        label="Je confirme cette inscription gratuite.",
    )


class TicketForm(FannFlowModelForm):
    price = forms.DecimalField(
        label="Prix (DT)",
        min_value=Decimal("0.00"),
        max_digits=10,
        decimal_places=2,
        error_messages={
            "required": "Veuillez saisir le prix du billet.",
            "invalid": "Saisissez un montant valide, par exemple 25,00.",
            "min_value": "Le prix du billet ne peut pas être négatif.",
            "max_digits": "Le prix ne peut pas dépasser 10 chiffres.",
            "max_decimal_places": "Le prix ne peut pas comporter plus de 2 chiffres après la virgule.",
            "max_whole_digits": "Le prix ne peut pas dépasser 8 chiffres avant la virgule.",
        },
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
    )

    class Meta:
        model = Ticket
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        registration = cleaned_data.get("registration")
        status = cleaned_data.get("status")
        price = cleaned_data.get("price")

        if status == Ticket.STATUS_AVAILABLE and registration and price is not None:
            if registration.status != Registration.STATUS_CONFIRMED:
                self.add_error("status", "Le billet ne peut pas être disponible avant la confirmation de l’inscription.")
            elif price > 0 and registration.payment_status != Registration.PAYMENT_PAID:
                self.add_error("status", "Le billet payant ne peut pas être disponible avant le paiement.")
        if status == Ticket.STATUS_USED and self.instance.status != Ticket.STATUS_USED:
            self.add_error("status", "Le statut « Utilisé » est attribué uniquement lors de l’enregistrement d’une entrée.")
        if self.instance.status == Ticket.STATUS_USED and status != Ticket.STATUS_USED:
            self.add_error("status", "Un billet déjà utilisé ne peut pas être réactivé ou annulé.")
        if status == Ticket.STATUS_CANCELLED and registration and registration.status != Registration.STATUS_CANCELLED:
            self.add_error("status", "Annulez d’abord l’inscription associée.")
        if status == Ticket.STATUS_REFUND and registration and registration.payment_status != Registration.PAYMENT_REFUNDED:
            self.add_error("status", "Le remboursement doit d’abord être enregistré sur l’inscription.")
        if (
            self.instance.pk
            and registration
            and registration.pk != self.instance.registration_id
            and self.instance.attendances.exists()
        ):
            self.add_error("registration", "Un billet avec une présence liée ne peut pas être déplacé vers une autre inscription.")
        if self.instance.pk and self.instance.status == Ticket.STATUS_USED:
            if any(
                cleaned_data.get(field_name) != getattr(self.instance, field_name)
                for field_name in ("registration", "price", "category")
            ):
                raise forms.ValidationError(
                    "Un billet déjà utilisé ne peut pas être modifié."
                )
        return cleaned_data


class AttendanceForm(FannFlowModelForm):
    class Meta:
        model = Attendance
        fields = "__all__"
        widgets = {
            "check_in": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "check_out": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        datetime_format = "%Y-%m-%dT%H:%M"
        for field_name in ("check_in", "check_out"):
            self.fields[field_name].input_formats = [datetime_format]


class CheckInForm(FannFlowFormMixin, forms.Form):
    code = forms.CharField(
        label="Code billet",
        max_length=255,
        widget=forms.TextInput(attrs={"autocomplete": "off", "autofocus": True}),
    )
    access_point = forms.ModelChoiceField(
        label="Point d’accès",
        queryset=AccessPoint.objects.all(),
    )


class AccessPointForm(FannFlowModelForm):
    class Meta:
        model = AccessPoint
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event_id"].widget.attrs["min"] = 1
        self.fields["capacity"].widget.attrs["min"] = 1
