"""Module 1 — Users & Organization Teams.

``User`` remplace le modèle utilisateur de Django (``AUTH_USER_MODEL``) :
l'email sert d'identifiant et le mot de passe est haché par Django
(colonne ``password_hash``).
"""

import os
import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db import models
from django.utils import timezone

PROFILE_PICTURE_MAX_SIZE = 2 * 1024 * 1024  # 2 Mo
PROFILE_PICTURE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]


def profile_picture_upload_to(instance, filename):
    """Nom de fichier aléatoire : on ne conserve jamais le nom fourni."""
    extension = os.path.splitext(filename)[1].lower()
    return f"users/profile_pictures/{uuid.uuid4().hex}{extension}"


def validate_profile_picture_size(file):
    if file.size > PROFILE_PICTURE_MAX_SIZE:
        raise ValidationError("La photo de profil ne doit pas dépasser 2 Mo.")


phone_validator = RegexValidator(
    regex=r"^\+?[0-9 ]{8,20}$",
    message="Numéro invalide : 8 à 20 chiffres, espaces et « + » initial autorisés.",
)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("L’email est obligatoire.")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.PARTICIPANT)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields["role"] = User.Role.ADMIN
        extra_fields["is_superuser"] = True
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        PARTICIPANT = "participant", "Participant"
        ADMIN = "administrateur", "Administrateur"

    class BusinessRole(models.TextChoices):
        DIRECTOR = "directeur", "Directeur"
        ORGANIZER = "organisateur", "Organisateur"
        SPONSOR_MANAGER = "responsable_sponsors", "Responsable Sponsors"

    class Status(models.TextChoices):
        ACTIVE = "actif", "Actif"
        INACTIVE = "inactif", "Inactif"

    # Id_user : clé primaire automatique (BigAutoField).
    first_name = models.CharField("prénom", max_length=100)
    last_name = models.CharField("nom", max_length=100)
    email = models.EmailField("email", unique=True)
    # Password_hash : le champ ``password`` d'AbstractBaseUser, stocké haché.
    password = models.CharField("mot de passe", max_length=128, db_column="password_hash")
    phone = models.CharField("téléphone", max_length=20, blank=True, validators=[phone_validator])
    birth_date = models.DateField("date de naissance", null=True, blank=True)
    profile_picture = models.FileField(
        "photo de profil",
        upload_to=profile_picture_upload_to,
        blank=True,
        validators=[
            FileExtensionValidator(PROFILE_PICTURE_EXTENSIONS),
            validate_profile_picture_size,
        ],
        help_text="JPG, PNG ou WEBP, 2 Mo maximum.",
    )
    # Face_encoding : réservé à un sprint ultérieur, jamais affiché ni édité.
    face_encoding = models.BinaryField("encodage facial", null=True, blank=True, editable=False)
    role = models.CharField("rôle", max_length=20, choices=Role.choices, default=Role.PARTICIPANT)
    business_role = models.CharField(
        "rôle métier", max_length=20, choices=BusinessRole.choices, blank=True
    )
    status = models.CharField("statut", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField("créé le", default=timezone.now, editable=False)
    # Last_login : hérité d'AbstractBaseUser (nullable, mis à jour à la connexion).

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.get_full_name() or self.email

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.email.strip().lower()

    # --- Accès -----------------------------------------------------------
    @property
    def is_active(self):
        """Utilisé par le backend d'authentification : un compte inactif ne se connecte pas."""
        return self.status == self.Status.ACTIVE

    @is_active.setter
    def is_active(self, value):
        self.status = self.Status.ACTIVE if value else self.Status.INACTIVE

    @property
    def is_staff(self):
        """Accès à l'administration Django réservé aux administrateurs."""
        return self.role == self.Role.ADMIN

    @property
    def is_administrator(self):
        return self.role == self.Role.ADMIN

    @property
    def has_management_access(self):
        """Administrateur, directeur ou organisateur : accès à l'espace de gestion."""
        return self.is_administrator or bool(self.business_role)

    # --- Affichage -------------------------------------------------------
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    @property
    def initials(self):
        return (self.first_name[:1] + self.last_name[:1]).upper() or self.email[:1].upper()


class AccountActivity(models.Model):
    """Journal des opérations d'administration sur les comptes.

    Alimenté par les vues d'administration (modification, changement de rôle,
    activation, suppression). Les créations de comptes se lisent directement
    dans ``User.created_at``.
    """

    class Action(models.TextChoices):
        UPDATED = "updated", "Compte modifié"
        ROLE_CHANGED = "role_changed", "Rôle modifié"
        ACTIVATED = "activated", "Compte activé"
        DEACTIVATED = "deactivated", "Compte désactivé"
        DELETED = "deleted", "Compte supprimé"
        PROFILE_UPDATED = "profile_updated", "Profil mis à jour"

    action = models.CharField("action", max_length=20, choices=Action.choices)
    actor = models.ForeignKey(
        User, verbose_name="auteur", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    target = models.ForeignKey(
        User, verbose_name="compte concerné", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="account_activities",
    )
    # Nom conservé même après suppression du compte.
    target_label = models.CharField("compte", max_length=210)
    details = models.CharField("détails", max_length=255, blank=True)
    created_at = models.DateTimeField("date", default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "activité de compte"
        verbose_name_plural = "activités de comptes"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} — {self.target_label}"


class EventOrganizer(models.Model):
    """Affectation d'un organisateur à un événement (entité « Event Organizer »)."""

    class Permission(models.TextChoices):
        VIEW = "consultation", "Consultation"
        REGISTRATIONS = "inscriptions", "Gestion des inscriptions"
        ACCESS = "acces", "Contrôle des accès"
        FULL = "complet", "Gestion complète"

    class Status(models.TextChoices):
        ACTIVE = "actif", "Actif"
        SUSPENDED = "suspendu", "Suspendu"

    class TaskStatus(models.TextChoices):
        TODO = "a_faire", "À faire"
        IN_PROGRESS = "en_cours", "En cours"
        DONE = "terminee", "Terminée"

    # Id_event_organizer : clé primaire automatique.
    user = models.ForeignKey(
        User, verbose_name="organisateur", on_delete=models.CASCADE,
        related_name="event_assignments",
        limit_choices_to={"business_role": User.BusinessRole.ORGANIZER},
    )
    event = models.ForeignKey(
        "events_program.Event", verbose_name="événement", on_delete=models.CASCADE,
        related_name="organizer_assignments",
    )
    permissions = models.CharField(
        "permissions", max_length=20, choices=Permission.choices, default=Permission.VIEW
    )
    assigned_by = models.ForeignKey(
        User, verbose_name="affecté par", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    assigned_at = models.DateTimeField("affecté le", default=timezone.now, editable=False)
    status = models.CharField("statut", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    task = models.CharField("tâche", max_length=200, blank=True)
    task_status = models.CharField(
        "avancement de la tâche", max_length=10, choices=TaskStatus.choices, default=TaskStatus.TODO
    )

    class Meta:
        verbose_name = "affectation d’organisateur"
        verbose_name_plural = "affectations d’organisateurs"
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "event"], name="unique_organizer_per_event"),
        ]

    def __str__(self):
        return f"{self.user} — {self.event}"
