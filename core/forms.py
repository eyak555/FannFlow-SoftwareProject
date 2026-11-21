"""Point d'entrée commun pour les formulaires des modules.

Les ModelForm métier héritent de ``FannFlowModelForm`` afin de recevoir
les classes du socle, sans recopier de HTML.
"""

from django import forms


class FannFlowFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} ff-input".strip()


class FannFlowModelForm(FannFlowFormMixin, forms.ModelForm):
    pass
