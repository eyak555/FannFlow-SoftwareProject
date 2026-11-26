from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth import get_user_model
from django.core import signing
from django.db.models import CharField, Q
from django.db.models.functions import Coalesce

from core.forms import FannFlowModelForm
from resources_operations.models import Venue
from .models import Activity, ActivitySpeaker, Event, Speaker


class VenueSelect(forms.Select):
    def __init__(self, *args, venue_data=None, **kwargs):
        self.venue_data = venue_data or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex=subindex,
            attrs=attrs,
        )
        raw_value = getattr(value, "value", value)
        venue = self.venue_data.get(str(raw_value))
        if venue:
            option["attrs"].update(
                {
                    "data-venue-name": venue["name"],
                    "data-venue-address": venue["address"],
                    "data-venue-city": venue["city"],
                }
            )
            if venue["latitude"] is not None and venue["longitude"] is not None:
                option["attrs"]["data-latitude"] = venue["latitude"]
                option["attrs"]["data-longitude"] = venue["longitude"]
        return option


class EventForm(FannFlowModelForm):
    selected_latitude = forms.DecimalField(
        required=False,
        max_digits=8,
        decimal_places=6,
        min_value=Decimal("-90"),
        max_value=Decimal("90"),
        widget=forms.HiddenInput(),
    )
    selected_longitude = forms.DecimalField(
        required=False,
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-180"),
        max_value=Decimal("180"),
        widget=forms.HiddenInput(),
    )
    location_token = forms.CharField(
        required=False,
        max_length=512,
        widget=forms.HiddenInput(),
    )
    new_venue_address = forms.CharField(
        required=False,
        max_length=255,
        label="Adresse de la position sélectionnée",
    )
    new_venue_city = forms.CharField(
        required=False,
        max_length=100,
        label="Ville de la position sélectionnée",
    )
    category = forms.ChoiceField(
        choices=Event.Category.choices,
        label="Catégorie",
    )

    class Meta:
        model = Event
        labels = {
            "ticket_price": "Prix Standard (DT)",
            "vip_ticket_price": "Prix VIP (DT)",
            "location": "Lieu (texte libre)",
        }
        fields = (
            "title",
            "description",
            "event_type",
            "category",
            "start_date",
            "end_date",
            "registration_deadline",
            "capacity",
            "ticket_price",
            "vip_ticket_price",
            "minimum_age",
            "maximum_age",
            "location",
            "venue",
            "image",
            "director",
            "status",
        )
        widgets = {
            "start_date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "end_date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "registration_deadline": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user_model = get_user_model()
        self.fields["director"].queryset = user_model.objects.filter(
            Q(role=user_model.Role.ADMIN) | ~Q(business_role="")
        ).filter(status=user_model.Status.ACTIVE)
        self.fields["director"].required = True
        self.fields["venue"].queryset = Venue.objects.order_by("city", "name")
        venues = list(self.fields["venue"].queryset)
        self.fields["venue"].required = False
        venue_data = {
            str(venue.pk): {
                "name": venue.name,
                "address": venue.address,
                "city": venue.city,
                "latitude": str(venue.latitude) if venue.latitude is not None else None,
                "longitude": str(venue.longitude) if venue.longitude is not None else None,
            }
            for venue in venues
        }
        self.fields["venue"].widget = VenueSelect(venue_data=venue_data)
        self.fields["venue"].widget.choices = self.fields["venue"].choices
        self.fields["venue"].help_text = (
            "Choisissez un lieu existant ou sélectionnez un nouvel emplacement sur la carte."
        )
        self.fields["location"].help_text = (
            "Nom affiché de l’événement ou du lieu."
        )
        self.fields["ticket_price"].min_value = 0
        self.fields["vip_ticket_price"].min_value = 0
        self.fields["vip_ticket_price"].required = True
        self.fields["capacity"].min_value = 1
        self.fields["minimum_age"].min_value = 0
        self.fields["minimum_age"].max_value = 120
        self.fields["maximum_age"].min_value = 0
        self.fields["maximum_age"].max_value = 120
        self.fields["image"].required = False
        if self.instance.pk and self.instance.category not in dict(Event.Category.choices):
            self.fields["category"].choices = (
                *Event.Category.choices,
                (self.instance.category, self.instance.category),
            )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("venue"):
            return cleaned_data

        latitude = cleaned_data.get("selected_latitude")
        longitude = cleaned_data.get("selected_longitude")
        if (latitude is None) != (longitude is None):
            self.add_error(
                "selected_latitude",
                "Sélectionnez une position complète sur la carte.",
            )
            return cleaned_data
        if latitude is None:
            return cleaned_data

        token = cleaned_data.get("location_token")
        try:
            verified = signing.loads(
                token,
                salt="events_program.verified_venue_coordinates",
                max_age=3600,
            )
            token_latitude = Decimal(verified["latitude"])
            token_longitude = Decimal(verified["longitude"])
        except (signing.BadSignature, InvalidOperation, KeyError, TypeError, ValueError):
            self.add_error(
                "selected_latitude",
                "La position doit être vérifiée par le service cartographique.",
            )
            return cleaned_data

        if (latitude, longitude) != (token_latitude, token_longitude):
            self.add_error(
                "selected_latitude",
                "La position sélectionnée ne correspond pas à sa vérification.",
            )
        if not cleaned_data.get("new_venue_address"):
            self.add_error("new_venue_address", "Renseignez l’adresse du lieu.")
        if not cleaned_data.get("new_venue_city"):
            self.add_error("new_venue_city", "Renseignez la ville du lieu.")
        return cleaned_data


class EventDashboardFilterForm(forms.Form):
    category = forms.ChoiceField(
        required=False,
        label="Catégorie",
        choices=(("", "Toutes les catégories"), *Event.Category.choices),
    )
    status = forms.ChoiceField(
        required=False,
        label="Statut",
        choices=(("", "Tous les statuts"), *Event.Status.choices),
    )
    city = forms.ChoiceField(
        required=False,
        label="Ville / lieu",
        choices=(("", "Toutes les villes / lieux"),),
    )
    start_date = forms.DateField(
        required=False,
        label="À partir du",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_date = forms.DateField(
        required=False,
        label="Jusqu’au",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, events, **kwargs):
        super().__init__(*args, **kwargs)
        places = (
            events.annotate(
                display_place=Coalesce(
                    "venue__city",
                    "location",
                    output_field=CharField(),
                )
            )
            .exclude(display_place="")
            .order_by("display_place")
            .values_list("display_place", flat=True)
            .distinct()
        )
        self.fields["city"].choices = (
            ("", "Toutes les villes / lieux"),
            *((place, place) for place in places),
        )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "La date de fin doit être égale ou postérieure à la date de début.")
        return cleaned_data


class ActivityForm(FannFlowModelForm):
    speakers = forms.ModelMultipleChoiceField(
        queryset=Speaker.objects.none(),
        required=False,
        label="Intervenants",
    )

    class Meta:
        model = Activity
        fields = (
            "event",
            "title",
            "description",
            "activity_type",
            "start_time",
            "end_time",
            "capacity",
            "room",
        )
        widgets = {
            "start_time": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "end_time": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["speakers"].queryset = Speaker.objects.all()
        if self.instance.pk:
            self.fields["speakers"].initial = self.instance.speakers.all()
        self.fields["capacity"].min_value = 1


class SpeakerForm(FannFlowModelForm):
    class Meta:
        model = Speaker
        fields = ("name", "bio", "organization", "country", "expertise", "email")
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}


class ActivitySpeakerForm(FannFlowModelForm):
    class Meta:
        model = ActivitySpeaker
        fields = ("activity", "speaker")

    def clean(self):
        cleaned_data = super().clean()
        activity = cleaned_data.get("activity")
        speaker = cleaned_data.get("speaker")
        if activity and speaker and ActivitySpeaker.objects.filter(
            activity=activity, speaker=speaker
        ).exclude(pk=self.instance.pk).exists():
            self.add_error("speaker", "Cet intervenant est déjà associé à cette activité.")
        return cleaned_data
