import re

from django import forms
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.utils import timezone

from core.forms import FannFlowFormMixin, FannFlowModelForm
from .models import EventOrganizer, User

# Le sélecteur de fichiers ne propose que les formats acceptés par le modèle.
PICTURE_WIDGET = forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"})

PROFILE_FIELDS = ["first_name", "last_name", "email", "phone", "birth_date", "profile_picture"]
ADMIN_FIELDS = PROFILE_FIELDS + ["role", "business_role", "status"]

# --- Contrôles de saisie communs (nom, prénom, email) -------------------------

NAME_MIN_LENGTH = 3
# Lettres (accents compris), espaces, tirets et apostrophes : « Ben Salah », « Aït-Ali », « O'Neil ».
NAME_PATTERN = re.compile(r"^[^\W\d_]+(?:[ '’-][^\W\d_]+)*$")
EMAIL_INVALID_MESSAGE = "Adresse email invalide : elle doit contenir « @ » suivi d’un domaine (ex. nom@exemple.tn)."


def clean_person_name(value, label):
    """Nettoie et contrôle un nom ou prénom saisi."""
    value = " ".join((value or "").split())  # espaces superflus supprimés
    if len(value) < NAME_MIN_LENGTH:
        raise forms.ValidationError(f"Le {label} doit contenir au moins {NAME_MIN_LENGTH} caractères.")
    if not NAME_PATTERN.match(value):
        raise forms.ValidationError(
            f"Le {label} ne peut contenir que des lettres, des espaces, des tirets ou des apostrophes."
        )
    return value


def check_email_has_at(value):
    if "@" not in (value or ""):
        raise forms.ValidationError(EMAIL_INVALID_MESSAGE, code="invalid")


class PersonFieldsMixin:
    """Applique les contrôles de nom, prénom et email aux formulaires qui les contiennent."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("first_name", "last_name"):
            if name in self.fields:
                self.fields[name].widget.attrs.update({"minlength": NAME_MIN_LENGTH, "autocomplete": {
                    "first_name": "given-name", "last_name": "family-name"}[name]})
        if "email" in self.fields:
            self.fields["email"].error_messages["invalid"] = EMAIL_INVALID_MESSAGE

    def clean_first_name(self):
        return clean_person_name(self.cleaned_data.get("first_name"), "prénom")

    def clean_last_name(self):
        return clean_person_name(self.cleaned_data.get("last_name"), "nom")


class UserFormBase(PersonFieldsMixin, FannFlowModelForm):
    """Validation commune : email unique (insensible à la casse), date, mot de passe."""

    password_required = True

    password1 = forms.CharField(
        label="Mot de passe",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirmation du mot de passe",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ADMIN_FIELDS
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "profile_picture": PICTURE_WIDGET,
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].required = self.password_required
        self.fields["password2"].required = self.password_required
        if not self.password_required:
            self.fields["password1"].help_text = "Laisser vide pour conserver le mot de passe actuel."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        check_email_has_at(email)
        duplicates = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("Un compte existe déjà avec cet email.")
        return email

    def clean_birth_date(self):
        birth_date = self.cleaned_data.get("birth_date")
        if birth_date and birth_date >= timezone.localdate():
            raise forms.ValidationError("La date de naissance doit être dans le passé.")
        return birth_date

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "Les deux mots de passe ne correspondent pas.")
            else:
                # Les validateurs comparent le mot de passe aux nom/prénom/email saisis.
                candidate = self.instance
                for field in ("first_name", "last_name", "email"):
                    if cleaned_data.get(field):
                        setattr(candidate, field, cleaned_data[field])
                try:
                    password_validation.validate_password(password1, candidate)
                except forms.ValidationError as error:
                    self.add_error("password1", error)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)  # hachage natif Django
        if commit:
            user.save()
        return user


class UserCreateForm(UserFormBase):
    """Création par un administrateur : rôle et rôle métier au choix."""


class UserUpdateForm(UserFormBase):
    """Modification par un administrateur : mot de passe optionnel."""

    password_required = False


class RegisterForm(UserFormBase):
    """Inscription publique : le rôle est forcé à Participant."""

    class Meta(UserFormBase.Meta):
        fields = PROFILE_FIELDS

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.PARTICIPANT
        user.business_role = ""
        user.status = User.Status.ACTIVE
        user.is_superuser = False
        if commit:
            user.save()
        return user


class LoginForm(FannFlowFormMixin, AuthenticationForm):
    """Connexion par email ; distingue un compte inactif d'identifiants erronés."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
        error_messages={"invalid": EMAIL_INVALID_MESSAGE},
    )

    error_messages = {
        "invalid_login": "Email ou mot de passe incorrect.",
        "inactive": "Ce compte est inactif. Contactez un administrateur.",
    }

    def clean(self):
        email = (self.cleaned_data.get("username") or "").strip().lower()
        password = self.cleaned_data.get("password")
        if email and password:
            self.cleaned_data["username"] = email
            self.user_cache = authenticate(self.request, username=email, password=password)
            if self.user_cache is None:
                inactive_user = User.objects.filter(email__iexact=email).first()
                if (
                    inactive_user
                    and not inactive_user.is_active
                    and inactive_user.check_password(password)
                ):
                    raise forms.ValidationError(self.error_messages["inactive"], code="inactive")
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class ProfileForm(PersonFieldsMixin, FannFlowModelForm):
    """Mon profil : informations personnelles uniquement (ni email, ni rôle, ni statut)."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "birth_date", "profile_picture"]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "profile_picture": PICTURE_WIDGET,
        }

    def clean_birth_date(self):
        birth_date = self.cleaned_data.get("birth_date")
        if birth_date and birth_date >= timezone.localdate():
            raise forms.ValidationError("La date de naissance doit être dans le passé.")
        return birth_date


class PasswordSettingsForm(FannFlowFormMixin, PasswordChangeForm):
    """Paramètres : changement de mot de passe (validateurs Django)."""


# --- Affectation des organisateurs aux événements --------------------------------


def assignable_events():
    from events_program.models import Event

    return Event.objects.exclude(status=Event.Status.CANCELLED).order_by("start_date", "title")


def assignable_organizers():
    return User.objects.filter(
        business_role=User.BusinessRole.ORGANIZER, status=User.Status.ACTIVE
    ).order_by("last_name", "first_name")


class EventOrganizerAssignForm(FannFlowFormMixin, forms.Form):
    """Affecter un ou plusieurs organisateurs à un événement."""

    event = forms.ModelChoiceField(label="Événement", queryset=None, empty_label="— Choisir un événement —")
    organizers = forms.ModelMultipleChoiceField(
        label="Organisateurs", queryset=None, widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Sélectionnez au moins un organisateur."},
    )
    permissions = forms.ChoiceField(label="Permissions", choices=EventOrganizer.Permission.choices)
    task = forms.CharField(label="Tâche (optionnel)", max_length=200, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = assignable_events()
        self.fields["organizers"].queryset = assignable_organizers()
        self.fields["organizers"].widget.attrs["class"] = "check-list"
        self.already_assigned = []

    def clean(self):
        cleaned = super().clean()
        event, organizers = cleaned.get("event"), cleaned.get("organizers")
        if event and organizers:
            assigned = set(
                EventOrganizer.objects.filter(event=event, user__in=organizers).values_list("user_id", flat=True)
            )
            self.already_assigned = [u for u in organizers if u.pk in assigned]
            cleaned["new_organizers"] = [u for u in organizers if u.pk not in assigned]
            if not cleaned["new_organizers"]:
                raise forms.ValidationError("Tous les organisateurs sélectionnés sont déjà affectés à cet événement.")
        return cleaned


class EventOrganizerUpdateForm(FannFlowModelForm):
    """Modifier les permissions, le statut et la tâche d'une affectation."""

    class Meta:
        model = EventOrganizer
        fields = ["permissions", "status", "task", "task_status"]
