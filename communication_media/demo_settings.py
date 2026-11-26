"""Réglages de démonstration du Module 6 : base et fichiers séparés.

    python manage.py migrate --settings=communication_media.demo_settings
    python manage.py runserver --settings=communication_media.demo_settings

Tout est écrit dans ``demo_data/`` à la racine du projet, jamais dans
``db.sqlite3`` ni dans ``media/``. Ce dossier est ignoré par Git grâce aux
règles existantes du .gitignore (``db.sqlite3`` et ``media/``).
Supprimer ``demo_data/`` remet la démonstration à zéro.
"""

from fannflow.settings import *  # noqa: F401,F403
from fannflow.settings import BASE_DIR

DEMO_DIR = BASE_DIR / "demo_data"
DEMO_DIR.mkdir(exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DEMO_DIR / "db.sqlite3",
    }
}

MEDIA_ROOT = DEMO_DIR / "media"
