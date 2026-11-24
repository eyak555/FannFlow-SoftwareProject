from django import forms

from core.forms import FannFlowModelForm
from .models import AccessPoint, Attendance, Registration, Ticket


class RegistrationForm(FannFlowModelForm):
    class Meta:
        model = Registration
        exclude = ("registration_date",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event_id"].widget.attrs["min"] = 1


class TicketForm(FannFlowModelForm):
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


class AccessPointForm(FannFlowModelForm):
    class Meta:
        model = AccessPoint
        fields = "__all__"
