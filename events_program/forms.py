from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from core.forms import FannFlowModelForm
from .models import Activity, ActivitySpeaker, Event, Speaker


class EventForm(FannFlowModelForm):
    category = forms.ChoiceField(
        choices=Event.Category.choices,
        label="Catégorie",
    )

    class Meta:
        model = Event
        labels = {
            "ticket_price": "Prix Standard (DT)",
            "vip_ticket_price": "Prix VIP (DT)",
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
