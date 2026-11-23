from django import forms
from django.contrib.auth.forms import AuthenticationForm

from core.forms import FannFlowFormMixin, FannFlowModelForm

from .models import Resource, ResourceAllocation, Venue


class OperationsLoginForm(FannFlowFormMixin, AuthenticationForm):
    pass


class VenueForm(FannFlowModelForm):
    class Meta:
        model = Venue
        fields = (
            "name", "type", "address", "latitude", "longitude",
            "capacity", "surface", "parking_capacity", "accessibility",
        )
        help_texts = {
            "latitude": "Saisissez les deux coordonnées GPS ou laissez-les vides.",
        }


class ResourceForm(FannFlowModelForm):
    class Meta:
        model = Resource
        fields = ("name", "type", "quantity", "unit_cost", "location")


class LocalDateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self):
        super().__init__(attrs={"step": 1}, format="%Y-%m-%dT%H:%M:%S")


class ResourceChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, resource):
        return f"{resource.name} · {resource.location} (#{resource.pk})"


class ResourceAllocationForm(FannFlowModelForm):
    resource = ResourceChoiceField(label="Ressource", queryset=Resource.objects.all())

    class Meta:
        model = ResourceAllocation
        fields = ("resource", "event_id", "quantity", "start_time", "end_time")
        widgets = {
            "start_time": LocalDateTimeInput(),
            "end_time": LocalDateTimeInput(),
        }
        help_texts = {
            "event_id": "Saisissez l’identifiant numérique de l’événement.",
            "start_time": "Heure locale de Tunis.",
        }
