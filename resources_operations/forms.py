from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q
from django.utils import timezone

from core.forms import FannFlowFormMixin, FannFlowModelForm
from events_program.models import Event

from .events import event_choices
from .models import EventRequirements, Resource, ResourceAllocation, Venue


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
        fields = ("name", "type", "quantity", "unit_cost", "location", "status", "low_stock_threshold")
        help_texts = {"low_stock_threshold": "Une alerte apparaît lorsque le stock disponible atteint ce seuil."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].required = False

    def clean_status(self):
        return self.cleaned_data["status"] or self.instance.status

    def clean_low_stock_threshold(self):
        threshold = self.cleaned_data["low_stock_threshold"]
        return self.instance.low_stock_threshold if threshold is None else threshold


class LocalDateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self):
        super().__init__(attrs={"step": 1}, format="%Y-%m-%dT%H:%M:%S")


class ResourceChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, resource):
        return f"{resource.name} · {resource.location} (#{resource.pk})"


class EventSelectionField(forms.TypedChoiceField):
    def __init__(self):
        super().__init__(label="Événement", coerce=int)


class EventSelectionForm(FannFlowFormMixin, forms.Form):
    event_id = EventSelectionField()

    def __init__(self, *args, event_scope, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event_id"].choices = event_choices(event_scope)


class EventRequirementsForm(FannFlowModelForm):
    class Meta:
        model = EventRequirements
        fields = ("venue", "attendees", "minimum_surface", "parking_spaces", "needs_accessibility")

    def clean_parking_spaces(self):
        return self.cleaned_data["parking_spaces"] or 0


class ResourceAllocationForm(FannFlowModelForm):
    resource = ResourceChoiceField(label="Ressource", queryset=Resource.objects.none())
    event_id = EventSelectionField()

    class Meta:
        model = ResourceAllocation
        fields = ("resource", "event_id", "quantity", "start_time", "end_time", "used_quantity")
        widgets = {
            "start_time": LocalDateTimeInput(),
            "end_time": LocalDateTimeInput(),
        }
        help_texts = {
            "start_time": "Heure locale de Tunis.",
            "used_quantity": "Renseignez les unités réellement utilisées à partir du début de l’allocation.",
        }

    def __init__(self, *args, event_scope=None, allow_legacy=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_scope = Event.objects.all() if event_scope is None else event_scope
        choices = event_choices(self.event_scope)
        self.preserve_legacy = allow_legacy and bool(self.instance.pk) and self.instance.program_event_id is None
        if self.preserve_legacy:
            choices.append((0, f"Référence historique #{self.instance.event_id}"))
            self.initial["event_id"] = 0
        self.fields["event_id"].choices = choices
        self.fields["resource"].queryset = Resource.objects.filter(
            Q(status=Resource.Status.AVAILABLE, quantity__gt=0) | Q(pk=self.instance.resource_id),
        )

    def clean_event_id(self):
        selected = self.cleaned_data["event_id"]
        if selected == 0 and self.preserve_legacy:
            return self.instance.event_id
        if not self.event_scope.filter(pk=selected).exists():
            raise forms.ValidationError("Cet événement n’est plus disponible.")
        self.instance.program_event_id = selected
        return selected


class AllocationPlanningForm(EventSelectionForm):
    resource_type = forms.ChoiceField(label="Type de ressource")
    quantity = forms.IntegerField(label="Quantité nécessaire", min_value=1)
    start_time = forms.DateTimeField(label="Début souhaité", widget=LocalDateTimeInput())
    end_time = forms.DateTimeField(label="Fin souhaitée", widget=LocalDateTimeInput())
    latest_start = forms.DateTimeField(
        label="Dernier début acceptable", widget=LocalDateTimeInput(), required=False,
        help_text="Indiquez une date limite pour chercher un autre créneau de même durée.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        types = Resource.objects.filter(status=Resource.Status.AVAILABLE).order_by("type")
        self.fields["resource_type"].choices = [
            ("", "Sélectionner un type"),
            *((name, name) for name in types.values_list("type", flat=True).distinct()),
        ]

    def clean(self):
        data = super().clean()
        start, end, latest = (data.get(field) for field in ("start_time", "end_time", "latest_start"))
        if start and end and end <= start:
            self.add_error("end_time", "La fin doit être postérieure au début.")
        if start and start < timezone.now().replace(second=0, microsecond=0):
            self.add_error("start_time", "Sélectionnez un début à venir.")
        if start and latest and latest < start:
            self.add_error("latest_start", "Cette limite doit être égale ou postérieure au début souhaité.")
        elif start and end and latest:
            try:
                latest + (end - start)
            except OverflowError:
                self.add_error("latest_start", "La fin du dernier créneau dépasse les dates prises en charge.")
        return data
