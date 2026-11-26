from django import forms

from core.forms import FannFlowModelForm
from .models import Venue


class VenueForm(FannFlowModelForm):
    class Meta:
        model = Venue
        fields = (
            "name",
            "venue_type",
            "address",
            "city",
            "latitude",
            "longitude",
            "capacity",
            "surface",
            "parking_capacity",
            "accessibility",
        )
        widgets = {
            "latitude": forms.NumberInput(attrs={"step": "0.000001"}),
            "longitude": forms.NumberInput(attrs={"step": "0.000001"}),
            "surface": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "accessibility": forms.Textarea(attrs={"rows": 3}),
        }
