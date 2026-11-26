from django import forms

from core.forms import FannFlowModelForm

from .models import MediaContact


class MediaContactForm(FannFlowModelForm):
    """Formulaire de l'annuaire presse, en deux groupes : Identité et Coordonnées."""

    IDENTITY_FIELDS = ("name", "organization", "role")
    CONTACT_FIELDS = ("email", "phone")

    class Meta:
        model = MediaContact
        fields = ["name", "organization", "role", "email", "phone"]
        labels = {
            "name": "Nom complet",
            "organization": "Organisation ou média",
            "role": "Rôle",
            "email": "Adresse e-mail",
            "phone": "Téléphone",
        }
        help_texts = {
            "organization": "Facultatif. Exemple : Radio Culture, La Presse.",
            "email": "Facultatif. Exemple : prenom.nom@media.fr",
            "phone": "Facultatif. Exemple : +216 71 000 000",
        }
        error_messages = {
            "name": {
                "required": "Indiquez le nom du contact.",
                "max_length": "Le nom ne doit pas dépasser %(limit_value)d caractères.",
            },
            "organization": {
                "max_length": "L’organisation ne doit pas dépasser %(limit_value)d caractères.",
            },
            "email": {
                "invalid": "Saisissez une adresse e-mail valide, par exemple prenom.nom@media.fr.",
            },
            "role": {
                "required": "Choisissez un rôle.",
                "invalid_choice": "Choisissez un rôle dans la liste.",
            },
            "phone": {
                "max_length": "Le numéro ne doit pas dépasser %(limit_value)d caractères.",
            },
        }
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "name", "autofocus": True}),
            "organization": forms.TextInput(attrs={"autocomplete": "organization"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "inputmode": "email"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
        }

    def clean_name(self):
        # Le champ retire déjà les espaces de début et de fin ; on vérifie
        # explicitement pour garder le message même si ce comportement change.
        name = " ".join(self.cleaned_data.get("name", "").split())
        if not name:
            raise forms.ValidationError(
                self.fields["name"].error_messages["required"], code="required"
            )
        return name

    def clean_email(self):
        return self.cleaned_data.get("email", "").strip().lower()

    def clean_phone(self):
        return " ".join(self.cleaned_data.get("phone", "").split())

    def identity_fields(self):
        return [self[name] for name in self.IDENTITY_FIELDS]

    def contact_fields(self):
        return [self[name] for name in self.CONTACT_FIELDS]
