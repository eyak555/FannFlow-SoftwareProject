"""Comptes de démonstration du Sprint 1.

    python manage.py seed_users

Idempotent : un compte existant (même email) est mis à jour, mot de passe compris.
"""

from django.core.management.base import BaseCommand

from users_teams.models import User

DEMO_PASSWORD = "FannFlow@2026"

DEMO_USERS = [
    {"email": "admin@fannflow.tn", "first_name": "Amira", "last_name": "Admin",
     "role": User.Role.ADMIN, "business_role": "", "is_superuser": True},
    {"email": "directeur@fannflow.tn", "first_name": "Karim", "last_name": "Directeur",
     "role": User.Role.PARTICIPANT, "business_role": User.BusinessRole.DIRECTOR},
    {"email": "organisateur@fannflow.tn", "first_name": "Sana", "last_name": "Organisatrice",
     "role": User.Role.PARTICIPANT, "business_role": User.BusinessRole.ORGANIZER},
    {"email": "participant@fannflow.tn", "first_name": "Youssef", "last_name": "Participant",
     "role": User.Role.PARTICIPANT, "business_role": ""},
    {"email": "inactif@fannflow.tn", "first_name": "Lina", "last_name": "Inactive",
     "role": User.Role.PARTICIPANT, "business_role": "", "status": User.Status.INACTIVE},
]


class Command(BaseCommand):
    help = "Crée ou met à jour les comptes de démonstration du Module 1."

    def handle(self, *args, **options):
        for data in DEMO_USERS:
            data = dict(data)
            email = data.pop("email")
            data.setdefault("status", User.Status.ACTIVE)
            data.setdefault("is_superuser", False)
            user, created = User.objects.update_or_create(email=email, defaults=data)
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
            label = "créé" if created else "mis à jour"
            self.stdout.write(f"  {email} ({user.get_role_display()}) {label}")
        self.stdout.write(self.style.SUCCESS(
            f"{len(DEMO_USERS)} comptes prêts. Mot de passe commun : {DEMO_PASSWORD}"
        ))
