"""Données fictives de démonstration du Module 6 (Sprint 1).

    python manage.py seed_communication_media --settings=communication_media.demo_settings

Crée deux événements fictifs (modèle réel ``events_program.Event``) puis,
pour chacun, des communications, médias, un dossier de presse et des
publications. Idempotent : un élément déjà présent (même titre ou même nom)
n'est pas recréé. Les fichiers des médias sont générés ici (PNG et PDF
valides) et enregistrés réellement dans MEDIA_ROOT/communication_media/.

Par sécurité, la commande refuse d'écrire dans la base principale
``db.sqlite3`` sauf avec l'option ``--base-principale``.
"""

import struct
import zlib
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from communication_media.models import Communication, Media, MediaContact, PressKit, Publication
from events_program.models import Event


def make_png(width, height, top, bottom):
    """PNG valide : dégradé vertical entre deux couleurs RVB."""

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    rows = bytearray()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        pixel = bytes(round(a + (b - a) * ratio) for a, b in zip(top, bottom))
        rows += b"\x00" + pixel * width
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


def make_pdf(title):
    """PDF d'une page avec un titre (structure minimale valide)."""
    text = title.encode("latin-1", "replace")
    stream = b"BT /F1 24 Tf 72 720 Td (" + text + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(output)


def is_main_database():
    """Vrai si la connexion vise la base principale du projet (db.sqlite3)."""
    name = str(connection.settings_dict.get("NAME") or "")
    try:
        return Path(name).resolve() == (Path(settings.BASE_DIR) / "db.sqlite3").resolve()
    except (OSError, ValueError):
        return False


class Command(BaseCommand):
    help = "Crée des données fictives de démonstration pour Communication & Media."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-principale",
            action="store_true",
            help="Autorise l'écriture dans db.sqlite3 (déconseillé : utilisez la base de démo).",
        )

    def handle(self, *args, **options):
        if is_main_database() and not options["base_principale"]:
            raise CommandError(
                "Refus d’écrire des données fictives dans db.sqlite3. Lancez la commande avec "
                "--settings=communication_media.demo_settings (base de démonstration séparée)."
            )
        with transaction.atomic():
            created = self.seed()
        self.stdout.write(self.style.SUCCESS(f"Données de démonstration prêtes ({created} élément(s) créé(s))."))

    def get_or_create(self, model, lookup, defaults):
        obj, new = model.objects.get_or_create(**lookup, defaults=defaults)
        self.created += new
        return obj

    def event(self, title, **fields):
        event = Event.objects.filter(title=title).first()
        if event is None:
            event = Event(title=title, **fields)
            event.full_clean()  # règles du module Événements
            event.save()
            self.created += 1
        return event

    def media(self, name, content, filename, **fields):
        media = Media.objects.filter(name=name).first()
        if media is None:
            media = Media(name=name, **fields)
            media.file = ContentFile(content, name=filename)
            media.save()
            self.created += 1
        return media

    def seed(self):
        self.created = 0
        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        festival = self.event(
            "Festival des Arts (démo)",
            description="Événement fictif de démonstration : concerts, expositions et ateliers.",
            event_type=Event.EventType.FESTIVAL,
            category=Event.Category.MUSIC,
            start_date=now + timedelta(days=30),
            end_date=now + timedelta(days=32),
            registration_deadline=now + timedelta(days=25),
            capacity=500,
            location="Théâtre municipal (fictif)",
            status=Event.Status.PUBLISHED,
        )
        cinema = self.event(
            "Rencontres du cinéma (démo)",
            description="Événement fictif de démonstration : projections et débats.",
            event_type=Event.EventType.CONFERENCE,
            category=Event.Category.CINEMA,
            start_date=now + timedelta(days=60),
            end_date=now + timedelta(days=61),
            registration_deadline=now + timedelta(days=55),
            capacity=200,
            location="Cinémathèque (fictive)",
            status=Event.Status.DRAFT,
        )

        self.get_or_create(MediaContact, {"name": "Amira Ben Salah (démo)"}, {
            "organization": "Radio Culture (fictive)",
            "role": MediaContact.Role.JOURNALIST,
            "email": "amira.bensalah@radioculture.example",
            "phone": "+216 71 000 000",
        })

        communique = self.get_or_create(Communication, {"title": "Ouverture de la billetterie du Festival des Arts"}, {
            "event": festival,
            "type": Communication.Type.PRESS_RELEASE,
            "language": Communication.Language.FRENCH,
            "status": Communication.Status.PUBLISHED,
            "publication_date": now - timedelta(days=2),
            "content": (
                "La billetterie du Festival des Arts (édition fictive) est ouverte.\n\n"
                "Trois jours de concerts, d’expositions et d’ateliers sont proposés au "
                "public. Les journalistes peuvent demander leur accréditation auprès du "
                "service presse."
            ),
        })
        self.get_or_create(Communication, {"title": "Annonce du programme jeunesse"}, {
            "event": festival,
            "type": Communication.Type.ANNOUNCEMENT,
            "language": Communication.Language.FRENCH,
            "status": Communication.Status.DRAFT,
            "content": "Brouillon : liste des ateliers jeunesse à confirmer.",
        })
        cinema_note = self.get_or_create(Communication, {"title": "Sélection officielle des Rencontres du cinéma"}, {
            "event": cinema,
            "type": Communication.Type.INFORMATION,
            "language": Communication.Language.ENGLISH,
            "status": Communication.Status.VALIDATED,
            "content": "Draft list of the films selected for the (fictional) film meetings.",
        })

        poster = self.media(
            "Affiche officielle (démo)",
            make_png(480, 640, (30, 58, 95), (230, 162, 60)),
            "affiche-festival.png",
            media_type=Media.Type.POSTER,
            event=festival,
            communication=communique,
        )
        presentation = self.media(
            "Présentation presse (démo)",
            make_pdf("Festival des Arts - dossier presse"),
            "presentation-presse.pdf",
            media_type=Media.Type.DOCUMENT,
            event=festival,
        )
        self.media(
            "Visuel des Rencontres (démo)",
            make_png(640, 360, (46, 125, 138), (30, 58, 95)),
            "visuel-cinema.png",
            media_type=Media.Type.IMAGE,
            event=cinema,
            communication=cinema_note,
        )

        kit = PressKit.objects.filter(title="Dossier de presse — Festival des Arts (démo)").first()
        if kit is None:
            kit = PressKit.objects.create(
                title="Dossier de presse — Festival des Arts (démo)",
                event=festival,
                description=(
                    "Présentation du festival, artistes invités, chiffres clés et contacts "
                    "du service presse. Données fictives pour la démonstration."
                ),
            )
            kit.communications.set([communique])
            kit.media.set([poster, presentation])
            self.created += 1

        self.get_or_create(Publication, {
            "platform": Publication.Platform.INSTAGRAM,
            "content": "J-7 avant le Festival des Arts ! Réservez vos places. #FannFlow",
        }, {"event": festival, "publication_date": now + timedelta(days=7), "status": Publication.Status.SCHEDULED})
        self.get_or_create(Publication, {
            "platform": Publication.Platform.FACEBOOK,
            "content": "La billetterie est ouverte : retrouvez le programme complet sur le site.",
        }, {"event": festival, "publication_date": now - timedelta(days=1), "status": Publication.Status.PUBLISHED})
        self.get_or_create(Publication, {
            "platform": Publication.Platform.LINKEDIN,
            "content": "Appel à films pour les Rencontres du cinéma (événement fictif).",
        }, {"event": cinema, "publication_date": now + timedelta(days=14), "status": Publication.Status.DRAFT})
        return self.created


