from django import forms
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone

from core.forms import FannFlowFormMixin, FannFlowModelForm
from .models import User

PROFILE_FIELDS = ["first_name", "last_name", "email", "phone", "birth_date", "profile_picture"]
ADMIN_FIELDS = PROFILE_FIELDS + ["role", "business_role", "status"]


class UserFormBase(FannFlowModelForm):
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
