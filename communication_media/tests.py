from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import MediaContact


def make_event(title="Festival des Arts", days=30, **fields):
    """Événement réel du module Événements (events_program.Event)."""
    from django.utils import timezone as tz
    from datetime import timedelta as td

    from events_program.models import Event

    start = tz.now() + td(days=days)
    return Event.objects.create(
        title=title,
        description="Événement de test.",
        event_type="festival",
        start_date=start,
        end_date=start + td(days=2),
        registration_deadline=start - td(days=5),
        capacity=100,
        location="Tunis",
        **fields,
    )


class ManagementTestCase(TestCase):
    """Le back-office exige un compte de l'équipe (core.access) :
    chaque test se connecte avec un organisateur."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.staff = get_user_model().objects.create_user(
            email="organisateur@test.tn",
            password="FannFlow@2026",
            first_name="Sana",
            last_name="Organisatrice",
            business_role="organisateur",
        )
        cls.event = make_event()
        cls.other_event = make_event("Rencontres du cinéma", days=60)

    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)


VALID_DATA = {
    "name": "Amira Ben Salah",
    "organization": "Radio Culture",
    "role": MediaContact.Role.JOURNALIST,
    "email": "amira.bensalah@radioculture.tn",
    "phone": "+216 71 000 000",
}


def make_contact(**overrides):
    data = {**VALID_DATA, **overrides}
    return MediaContact.objects.create(**data)


class MediaContactAccessTests(TestCase):
    def test_visitor_is_redirected_to_login(self):
        url = reverse("communication_media:media_contact_list")
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('users_teams:login')}?next={url}", fetch_redirect_response=False)

    def test_participant_is_forbidden(self):
        participant = get_user_model().objects.create_user(
            email="participant@test.tn", password="test-password", first_name="P", last_name="T",
        )
        self.client.force_login(participant)
        self.assertEqual(self.client.get(reverse("communication_media:media_contact_list")).status_code, 403)


class MediaContactRoutesTests(ManagementTestCase):
    def test_generic_entity_route_leads_to_directory(self):
        url = reverse("communication_media:entity_list", args=["media-contacts"])
        self.assertEqual(url, reverse("communication_media:media_contact_list"))
        response = self.client.get(url)
        self.assertTemplateUsed(response, "communication_media/media_contacts/list.html")

    def test_module_home_links_to_directory(self):
        response = self.client.get(reverse("communication_media:home"))
        self.assertContains(response, reverse("communication_media:media_contact_list"))

    def test_other_entities_no_longer_use_the_placeholder(self):
        for slug in ("communications", "media", "press-kits", "publications"):
            response = self.client.get(reverse("communication_media:entity_list", args=[slug]))
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("placeholder", response.context)


class MediaContactListTests(ManagementTestCase):
    def test_empty_directory_offers_add_button(self):
        response = self.client.get(reverse("communication_media:media_contact_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Annuaire presse")
        self.assertContains(response, "L’annuaire est vide")
        self.assertContains(response, reverse("communication_media:media_contact_create"), count=2)

    def test_list_shows_name_organization_and_role(self):
        contact = make_contact()
        response = self.client.get(reverse("communication_media:media_contact_list"))
        self.assertContains(response, "Amira Ben Salah")
        self.assertContains(response, "Radio Culture")
        self.assertContains(response, "press-badge--journaliste")
        self.assertContains(response, contact.get_absolute_url())


class MediaContactCreateTests(ManagementTestCase):
    url = reverse("communication_media:media_contact_create")

    def test_form_page_groups_fields(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<legend>Identité</legend>", html=True)
        self.assertContains(response, "<legend>Coordonnées</legend>", html=True)

    def test_blank_name_is_refused_and_other_values_are_kept(self):
        for blank in ("", "    "):
            with self.subTest(name=repr(blank)):
                response = self.client.post(self.url, {**VALID_DATA, "name": blank})
                self.assertEqual(response.status_code, 200)
                self.assertFormError(response.context["form"], "name", "Indiquez le nom du contact.")
                self.assertContains(response, 'value="Radio Culture"')
                self.assertContains(response, 'value="amira.bensalah@radioculture.tn"')
        self.assertEqual(MediaContact.objects.count(), 0)

    def test_malformed_email_is_refused(self):
        response = self.client.post(self.url, {**VALID_DATA, "email": "amira@"})
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "email",
            "Saisissez une adresse e-mail valide, par exemple prenom.nom@media.fr.",
        )
        self.assertContains(response, 'value="Amira Ben Salah"')
        self.assertContains(response, 'value="amira@"')
        self.assertEqual(MediaContact.objects.count(), 0)

    def test_invalid_phone_is_refused(self):
        response = self.client.post(self.url, {**VALID_DATA, "phone": "appelez-moi"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("phone", response.context["form"].errors)
        self.assertEqual(MediaContact.objects.count(), 0)

    def test_optional_contact_details_may_be_empty(self):
        response = self.client.post(self.url, {**VALID_DATA, "email": "", "phone": "", "organization": ""})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MediaContact.objects.get().email, "")

    def test_valid_contact_is_saved_and_redirects_to_detail(self):
        response = self.client.post(self.url, {**VALID_DATA, "name": "  Amira   Ben Salah ", "email": "Amira.BenSalah@RadioCulture.tn"})
        contact = MediaContact.objects.get()
        self.assertRedirects(response, contact.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(contact.name, "Amira Ben Salah")
        self.assertEqual(contact.email, "amira.bensalah@radioculture.tn")

        # Actualisation de la page de consultation : simple GET, aucune nouvelle création.
        page = self.client.get(contact.get_absolute_url())
        self.assertContains(page, "a été ajouté")
        refreshed = self.client.get(contact.get_absolute_url())
        self.assertContains(refreshed, "Amira Ben Salah")
        self.assertNotContains(refreshed, "a été ajouté")
        self.assertEqual(MediaContact.objects.count(), 1)


class MediaContactDetailTests(ManagementTestCase):
    def test_detail_shows_mail_and_phone_links(self):
        contact = make_contact()
        response = self.client.get(contact.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h1>Amira Ben Salah</h1>", html=True)
        self.assertContains(response, 'href="mailto:amira.bensalah@radioculture.tn"')
        self.assertContains(response, 'href="tel:+21671000000"')

    def test_detail_without_contact_details(self):
        contact = make_contact(email="", phone="")
        response = self.client.get(contact.get_absolute_url())
        self.assertNotContains(response, "mailto:")
        self.assertNotContains(response, "tel:")
        self.assertContains(response, "Non renseignée")

    def test_unknown_contact_returns_404(self):
        for name in ("detail", "update", "delete"):
            with self.subTest(view=name):
                response = self.client.get(reverse(f"communication_media:media_contact_{name}", args=[999]))
                self.assertEqual(response.status_code, 404)


class MediaContactUpdateTests(ManagementTestCase):
    def setUp(self):
        super().setUp()
        self.contact = make_contact()
        self.url = reverse("communication_media:media_contact_update", args=[self.contact.pk])

    def test_form_is_prefilled(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'value="Amira Ben Salah"')

    def test_valid_update_is_saved(self):
        response = self.client.post(self.url, {**VALID_DATA, "organization": "Culture Hebdo", "role": "redaction"})
        self.assertRedirects(response, self.contact.get_absolute_url(), fetch_redirect_response=False)
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.organization, "Culture Hebdo")
        self.assertEqual(self.contact.role, "redaction")
        self.assertContains(self.client.get(response.url), "a été modifié")

    def test_invalid_update_keeps_original(self):
        response = self.client.post(self.url, {**VALID_DATA, "name": " "})
        self.assertEqual(response.status_code, 200)
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.name, "Amira Ben Salah")


class MediaContactDeleteTests(ManagementTestCase):
    def setUp(self):
        super().setUp()
        self.contact = make_contact()
        self.url = reverse("communication_media:media_contact_delete", args=[self.contact.pk])

    def test_confirmation_page_shows_name_and_deletes_nothing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<strong>Amira Ben Salah</strong>", html=True)
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, f'href="{self.contact.get_absolute_url()}"')
        self.assertTrue(MediaContact.objects.filter(pk=self.contact.pk).exists())

    def test_cancel_link_deletes_nothing(self):
        response = self.client.get(self.contact.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(MediaContact.objects.filter(pk=self.contact.pk).exists())

    def test_post_deletes_and_redirects_to_list(self):
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, reverse("communication_media:media_contact_list"))
        self.assertContains(response, "« Amira Ben Salah » a été supprimé")
        self.assertFalse(MediaContact.objects.exists())

    def test_post_without_csrf_token_is_rejected(self):
        client = self.client_class(enforce_csrf_checks=True)
        response = client.post(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(MediaContact.objects.filter(pk=self.contact.pk).exists())


# ===========================================================================
# Communication, Média, Dossier de presse, Publication
# ===========================================================================

import os
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from .models import Communication, Media, PressKit, Publication

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF_BYTES = b"%PDF-1.7\n%demo\n" + b"0" * 64
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def png(name="affiche.png", content=PNG_BYTES):
    return SimpleUploadedFile(name, content, content_type="image/png")


def local_dt(days=0, hours=0):
    """Date au format du champ datetime-local (heure locale)."""
    value = timezone.localtime() + timedelta(days=days, hours=hours)
    return value.strftime("%Y-%m-%dT%H:%M")


class EntityCrudContract:
    """Scénario CRUD commun, rejoué pour chaque entité.

    Une sous-classe fournit : ``prefix`` (préfixe des noms d'URL), ``model``,
    ``valid_data()``, ``create_item()``, ``required_text_field`` (champ texte
    obligatoire), ``kept_field`` (autre champ dont la valeur doit être
    conservée en cas d'erreur), ``choice_field`` et ``label``.
    """

    prefix = model = required_text_field = kept_field = choice_field = None
    label = ""

    def url(self, action, *args):
        return reverse(f"communication_media:{self.prefix}_{action}", args=args)

    def post_data(self, **overrides):
        return {"event": self.event.pk, **self.valid_data(), **overrides}

    # --- Accès ------------------------------------------------------------

    def test_visitor_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(self.url("list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users_teams:login"), response.url)

    def test_participant_is_refused(self):
        participant = get_user_model().objects.create_user(
            email="participant@test.tn", password="x", first_name="Y", last_name="P"
        )
        self.client.force_login(participant)
        self.assertEqual(self.client.get(self.url("list")).status_code, 403)
        self.assertEqual(self.client.post(self.url("create"), self.post_data()).status_code, 403)
        self.assertFalse(self.model.objects.exists())

    # --- Liste ------------------------------------------------------------

    def test_empty_list_offers_add_action(self):
        response = self.client.get(self.url("list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.url("create"), count=2)  # en-tête + état vide
        self.assertContains(response, "empty-state")

    def test_list_shows_item_with_links(self):
        item = self.create_item()
        response = self.client.get(self.url("list"))
        self.assertContains(response, item.get_absolute_url())
        self.assertContains(response, self.url("update", item.pk))
        self.assertNotContains(response, "empty-state")

    # --- Création ---------------------------------------------------------

    def test_create_form_is_displayed(self):
        response = self.client.get(self.url("create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, "Enregistrer")

    def test_valid_creation_is_saved_and_redirects_to_detail(self):
        response = self.client.post(self.url("create"), self.post_data())
        self.assertEqual(self.model.objects.count(), 1)
        item = self.model.objects.get()
        self.assertRedirects(response, item.get_absolute_url(), fetch_redirect_response=False)
        page = self.client.get(response.url)
        self.assertContains(page, "a été ajouté")
        # Relecture depuis la base : la donnée persiste au-delà de la requête.
        self.assertEqual(self.model.objects.filter(pk=item.pk).count(), 1)

    def test_whitespace_only_required_field_is_refused_and_values_kept(self):
        field = self.required_text_field
        response = self.client.post(self.url("create"), self.post_data(**{field: "   "}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.model.objects.exists())
        form = response.context["form"]
        self.assertIn(field, form.errors)
        # Le récapitulatif nomme le champ fautif.
        self.assertContains(response, f'href="#id_{field}">{form.fields[field].label}</a>')
        kept_value = self.valid_data()[self.kept_field]
        self.assertEqual(form[self.kept_field].value(), kept_value)

    def test_unknown_choice_is_refused(self):
        response = self.client.post(
            self.url("create"), self.post_data(**{self.choice_field: "inconnu"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.choice_field, response.context["form"].errors)
        self.assertFalse(self.model.objects.exists())

    # --- Événement --------------------------------------------------------

    def test_event_is_required(self):
        response = self.client.post(self.url("create"), self.post_data(event=""))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors["event"], ["Choisissez l’événement concerné."]
        )
        self.assertFalse(self.model.objects.exists())

    def test_unknown_event_is_refused(self):
        response = self.client.post(self.url("create"), self.post_data(event=9999))
        self.assertIn("n’existe pas", response.context["form"].errors["event"][0])
        self.assertFalse(self.model.objects.exists())

    def test_created_item_is_linked_to_the_chosen_event(self):
        self.client.post(self.url("create"), self.post_data(event=self.other_event.pk))
        self.assertEqual(self.model.objects.get().event, self.other_event)

    def test_list_can_be_filtered_by_event(self):
        item = self.create_item()
        response = self.client.get(self.url("list"), {"evenement": self.other_event.pk})
        self.assertNotContains(response, item.get_absolute_url())
        self.assertContains(response, "Aucun élément pour cet événement")
        response = self.client.get(self.url("list"), {"evenement": self.event.pk})
        self.assertContains(response, item.get_absolute_url())

    def test_unknown_event_filter_returns_404(self):
        self.assertEqual(self.client.get(self.url("list"), {"evenement": 9999}).status_code, 404)
        self.assertEqual(self.client.get(self.url("list"), {"evenement": "abc"}).status_code, 404)

    def test_deleting_the_event_keeps_the_item(self):
        item = self.create_item()
        self.event.__class__.objects.filter(pk=self.event.pk).delete()
        item.refresh_from_db()
        self.assertIsNone(item.event)
        response = self.client.get(item.get_absolute_url())
        self.assertContains(response, "Événement non renseigné")

    def test_item_without_event_must_get_one_when_edited(self):
        item = self.create_item()
        self.model.objects.filter(pk=item.pk).update(event=None)
        response = self.client.get(self.url("update", item.pk))
        self.assertContains(response, "créé avant le lien avec les événements")

    # --- Consultation ------------------------------------------------------

    def test_detail_page(self):
        item = self.create_item()
        response = self.client.get(item.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.url("update", item.pk))
        self.assertContains(response, self.url("delete", item.pk))

    def test_unknown_item_returns_404(self):
        for action in ("detail", "update", "delete"):
            self.assertEqual(self.client.get(self.url(action, 9999)).status_code, 404)

    # --- Modification ------------------------------------------------------

    def test_update_form_is_prefilled_and_saves(self):
        item = self.create_item()
        response = self.client.get(self.url("update", item.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].instance.pk, item.pk)

        response = self.client.post(self.url("update", item.pk), self.update_data())
        self.assertRedirects(response, item.get_absolute_url(), fetch_redirect_response=False)
        self.assertContains(self.client.get(response.url), "a été modifié")
        item.refresh_from_db()
        self.check_updated(item)

    def test_invalid_update_keeps_original(self):
        item = self.create_item()
        original = getattr(item, self.required_text_field)
        response = self.client.post(
            self.url("update", item.pk), self.post_data(**{self.required_text_field: " "})
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(getattr(item, self.required_text_field), original)

    # --- Suppression -------------------------------------------------------

    def test_delete_confirmation_deletes_nothing_and_cancels_to_detail(self):
        item = self.create_item()
        response = self.client.get(self.url("delete", item.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, 'method="post"')
        self.assertContains(response, f'href="{item.get_absolute_url()}"')  # Annuler
        self.assertTrue(self.model.objects.filter(pk=item.pk).exists())

    def test_post_deletes_and_redirects_to_list(self):
        item = self.create_item()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url("delete", item.pk), follow=True)
        self.assertRedirects(response, self.url("list"))
        self.assertContains(response, "a été supprimé")
        self.assertFalse(self.model.objects.filter(pk=item.pk).exists())

    def test_delete_without_csrf_token_is_rejected(self):
        item = self.create_item()
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.staff)
        self.assertEqual(client.post(self.url("delete", item.pk)).status_code, 403)
        self.assertTrue(self.model.objects.filter(pk=item.pk).exists())


# --- Communication ---------------------------------------------------------


class CommunicationCrudTests(EntityCrudContract, ManagementTestCase):
    prefix = "communication"
    model = Communication
    required_text_field = "title"
    kept_field = "content"
    choice_field = "language"

    def valid_data(self):
        return {
            "title": "Ouverture de la billetterie",
            "type": "communique",
            "content": "La billetterie du Festival des Arts ouvre le 1er décembre.",
            "language": "fr",
            "status": "brouillon",
            "publication_date": "",
        }

    def create_item(self):
        return Communication.objects.create(
            title="Programme dévoilé", content="Le programme complet est en ligne.", event=self.event
        )

    def update_data(self):
        return self.post_data(title="Programme  complet   dévoilé", status="valide")

    def check_updated(self, item):
        self.assertEqual(item.title, "Programme complet dévoilé")
        self.assertEqual(item.status, "valide")

    def test_new_communication_is_a_draft_by_default(self):
        response = self.client.get(self.url("create"))
        self.assertEqual(response.context["form"]["status"].value(), "brouillon")

    def test_published_communication_requires_a_date(self):
        response = self.client.post(self.url("create"), self.post_data(status="publie"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("publication_date", response.context["form"].errors)
        response = self.client.post(
            self.url("create"), self.post_data(status="publie", publication_date=local_dt())
        )
        self.assertEqual(response.status_code, 302)

    def test_invalid_date_is_refused(self):
        response = self.client.post(self.url("create"), self.post_data(publication_date="32/13/2026"))
        self.assertIn("publication_date", response.context["form"].errors)

    def test_whitespace_only_content_is_refused(self):
        response = self.client.post(self.url("create"), self.post_data(content="  \n  "))
        self.assertIn("content", response.context["form"].errors)


# --- Média -----------------------------------------------------------------


class TemporaryMediaRootMixin:
    """Les fichiers des tests sont écrits dans un dossier temporaire."""

    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix="fannflow-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)


class MediaCrudTests(TemporaryMediaRootMixin, EntityCrudContract, ManagementTestCase):
    prefix = "media"
    model = Media
    required_text_field = "name"
    kept_field = "media_type"
    choice_field = "media_type"

    def valid_data(self):
        return {"name": "Affiche officielle", "media_type": "image", "communication": "", "file": png()}

    def post_data(self, **overrides):
        data = super().post_data(**overrides)
        if self.choice_field in overrides and overrides[self.choice_field] == "inconnu":
            data["file"] = png()
        return data

    def create_item(self, **overrides):
        data = {"name": "Visuel du festival", "media_type": "image", "file": png("visuel.png"), "event": self.event, **overrides}
        return Media.objects.create(**data)

    def update_data(self):
        data = self.post_data(name="Visuel principal")
        data.pop("file")  # aucun nouveau fichier : l'actuel est conservé
        return data

    def check_updated(self, item):
        self.assertEqual(item.name, "Visuel principal")
        self.assertTrue(item.file.storage.exists(item.file.name))

    def stored_path(self, item):
        return Path(item.file.path)

    def test_upload_stores_the_real_file_and_metadata(self):
        response = self.client.post(self.url("create"), self.post_data())
        self.assertEqual(response.status_code, 302)
        item = Media.objects.get()
        path = self.stored_path(item)
        self.assertTrue(path.is_file())
        self.assertTrue(str(path).startswith(self._media_root))
        self.assertEqual(path.read_bytes(), PNG_BYTES)
        self.assertEqual(item.original_filename, "affiche.png")
        self.assertEqual(item.format, "PNG")
        self.assertEqual(item.size, len(PNG_BYTES))
        self.assertNotIn("affiche", path.name)  # nom aléatoire sur le disque

    def test_metadata_is_set_when_file_is_saved_programmatically(self):
        from django.core.files.base import ContentFile

        media = Media(name="Import", media_type="document")
        media.file.save("note.pdf", ContentFile(PDF_BYTES), save=False)
        media.save()
        self.assertEqual((media.format, media.size), ("PDF", len(PDF_BYTES)))

    def test_seed_command_creates_real_files_once(self):
        from django.core.management import call_command

        call_command("seed_communication_media", stdout=open(os.devnull, "w"))
        call_command("seed_communication_media", stdout=open(os.devnull, "w"))
        self.assertEqual(Media.objects.count(), 3)
        for media in Media.objects.all():
            self.assertTrue(Path(media.file.path).is_file())
            self.assertIn(media.format, {"PNG", "PDF"})
            self.assertGreater(media.size, 0)

    def test_file_is_served_by_the_module(self):
        item = self.create_item()
        response = self.client.get(item.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), PNG_BYTES)
        self.client.logout()
        self.assertEqual(self.client.get(item.url).status_code, 302)

    def test_missing_file_on_disk_returns_404(self):
        item = self.create_item()
        self.stored_path(item).unlink()
        self.assertEqual(self.client.get(item.url).status_code, 404)

    def test_file_is_required_on_creation(self):
        data = self.post_data()
        data.pop("file")
        response = self.client.post(self.url("create"), data)
        self.assertIn("file", response.context["form"].errors)

    def test_extension_must_match_media_type(self):
        data = self.post_data(media_type="video", file=png())
        response = self.client.post(self.url("create"), data)
        self.assertIn("Format non accepté", response.context["form"].errors["file"][0])
        self.assertFalse(Media.objects.exists())

    def test_disguised_file_is_refused(self):
        fake = SimpleUploadedFile("photo.png", b"<?php echo 1; ?>" * 4, content_type="image/png")
        response = self.client.post(self.url("create"), self.post_data(file=fake))
        self.assertIn("ne correspond pas", response.context["form"].errors["file"][0])

    def test_oversized_file_is_refused(self):
        big = png("grande.png", PNG_BYTES + b"\x00" * (5 * 1024 * 1024))
        response = self.client.post(self.url("create"), self.post_data(file=big))
        self.assertIn("limite", response.context["form"].errors["file"][0])
        self.assertFalse(Media.objects.exists())

    def test_pdf_poster_and_video_are_accepted(self):
        pdf = SimpleUploadedFile("affiche.pdf", PDF_BYTES, content_type="application/pdf")
        mp4 = SimpleUploadedFile("teaser.mp4", MP4_BYTES, content_type="video/mp4")
        self.client.post(self.url("create"), self.post_data(name="Affiche PDF", media_type="affiche", file=pdf))
        self.client.post(self.url("create"), self.post_data(name="Teaser", media_type="video", file=mp4))
        self.assertEqual(sorted(Media.objects.values_list("format", flat=True)), ["MP4", "PDF"])

    def test_replacing_the_file_deletes_the_old_one(self):
        item = self.create_item()
        old_path = self.stored_path(item)
        data = self.post_data(file=png("nouvelle.png"))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url("update", item.pk), data)
        item.refresh_from_db()
        self.assertEqual(item.original_filename, "nouvelle.png")
        self.assertTrue(self.stored_path(item).is_file())
        self.assertFalse(old_path.exists())

    def test_changing_type_must_stay_compatible_with_current_file(self):
        item = self.create_item()
        data = self.update_data()
        data["media_type"] = "video"
        response = self.client.post(self.url("update", item.pk), data)
        self.assertIn("media_type", response.context["form"].errors)

    def test_deleting_removes_the_file_from_disk(self):
        item = self.create_item()
        path = self.stored_path(item)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url("delete", item.pk))
        self.assertFalse(path.exists())

    def test_media_can_be_linked_to_a_communication(self):
        communication = Communication.objects.create(title="Communiqué", content="Texte", event=self.event)
        self.client.post(self.url("create"), self.post_data(communication=communication.pk))
        media = Media.objects.get()
        self.assertEqual(media.communication, communication)
        page = self.client.get(communication.get_absolute_url())
        self.assertContains(page, media.get_absolute_url())

    def test_unknown_communication_is_refused(self):
        response = self.client.post(self.url("create"), self.post_data(communication=9999))
        self.assertIn("communication", response.context["form"].errors)


# --- Dossier de presse -----------------------------------------------------


class PressKitCrudTests(EntityCrudContract, ManagementTestCase):
    prefix = "press_kit"
    model = PressKit
    required_text_field = "title"
    kept_field = "description"
    choice_field = None

    def valid_data(self):
        return {
            "title": "Dossier de presse — Festival des Arts 2026",
            "description": "Programme, artistes invités et informations pratiques.",
        }

    def create_item(self):
        return PressKit.objects.create(title="Dossier Jazz", description="Présentation du festival.", event=self.event)

    def update_data(self):
        return self.post_data(title="Dossier Jazz 2026")

    def check_updated(self, item):
        self.assertEqual(item.title, "Dossier Jazz 2026")

    def test_unknown_choice_is_refused(self):
        # Le dossier de presse n'a pas de liste de choix : on vérifie la description.
        response = self.client.post(self.url("create"), self.post_data(description="   "))
        self.assertIn("description", response.context["form"].errors)


# --- Publication -----------------------------------------------------------


class PublicationCrudTests(EntityCrudContract, ManagementTestCase):
    prefix = "publication"
    model = Publication
    required_text_field = "content"
    kept_field = "platform"
    choice_field = "platform"

    def valid_data(self):
        return {
            "platform": "instagram",
            "content": "J-7 avant le Festival des Arts ! #FannFlow",
            "publication_date": local_dt(days=7),
            "status": "programmee",
        }

    def create_item(self, **overrides):
        data = {
            "platform": "facebook",
            "content": "Merci à tous les participants !",
            "publication_date": timezone.now() - timedelta(days=1),
            "status": "publiee",
            "event": self.event,
            **overrides,
        }
        return Publication.objects.create(**data)

    def update_data(self):
        return {
            "event": self.event.pk,
            "platform": "linkedin",
            "content": "Merci aux 1 200 participants !",
            "publication_date": local_dt(days=-1),
            "status": "publiee",
        }

    def check_updated(self, item):
        self.assertEqual(item.platform, "linkedin")
        self.assertEqual(item.content, "Merci aux 1 200 participants !")

    def test_date_is_required(self):
        response = self.client.post(self.url("create"), self.post_data(publication_date=""))
        self.assertIn("publication_date", response.context["form"].errors)

    def test_x_content_is_limited_to_280_characters(self):
        response = self.client.post(self.url("create"), self.post_data(platform="x", content="a" * 281))
        self.assertIn("280", response.context["form"].errors["content"][0])
        response = self.client.post(self.url("create"), self.post_data(platform="x", content="a" * 280))
        self.assertEqual(response.status_code, 302)

    def test_scheduled_publication_needs_a_future_date(self):
        response = self.client.post(self.url("create"), self.post_data(publication_date=local_dt(days=-1)))
        self.assertIn("publication_date", response.context["form"].errors)

    def test_published_publication_cannot_be_in_the_future(self):
        response = self.client.post(self.url("create"), self.post_data(status="publiee"))
        self.assertIn("publication_date", response.context["form"].errors)

    def test_past_scheduled_publication_stays_editable(self):
        item = self.create_item(status="programmee")
        data = {
            "event": self.event.pk,
            "platform": item.platform,
            "content": "Texte corrigé",
            "publication_date": timezone.localtime(item.publication_date).strftime("%Y-%m-%dT%H:%M"),
            "status": "programmee",
        }
        response = self.client.post(self.url("update", item.pk), data)
        self.assertEqual(response.status_code, 302)


# --- Cohérence des événements ---------------------------------------------


class EventConsistencyTests(TemporaryMediaRootMixin, ManagementTestCase):
    """Dossier de presse, médias et communications d'un même événement."""

    def setUp(self):
        super().setUp()
        self.comm = Communication.objects.create(title="Communique festival", content="Texte", event=self.event)
        self.other_comm = Communication.objects.create(title="Communique cinema", content="Texte", event=self.other_event)
        self.media = Media.objects.create(name="Affiche festival", media_type="image", file=png(), event=self.event)
        self.other_media = Media.objects.create(name="Affiche cinema", media_type="image", file=png(), event=self.other_event)

    def kit_data(self, **overrides):
        return {
            "event": self.event.pk,
            "title": "Dossier festival",
            "description": "Presentation.",
            "communications": [self.comm.pk],
            "media": [self.media.pk],
            **overrides,
        }

    def test_press_kit_keeps_items_of_its_event(self):
        response = self.client.post(reverse("communication_media:press_kit_create"), self.kit_data())
        self.assertEqual(response.status_code, 302)
        kit = PressKit.objects.get()
        self.assertEqual(list(kit.communications.all()), [self.comm])
        self.assertEqual(list(kit.media.all()), [self.media])
        page = self.client.get(kit.get_absolute_url())
        self.assertContains(page, self.comm.get_absolute_url())
        self.assertContains(page, self.media.get_absolute_url())

    def test_press_kit_refuses_items_of_another_event(self):
        data = self.kit_data(communications=[self.comm.pk, self.other_comm.pk], media=[self.other_media.pk])
        response = self.client.post(reverse("communication_media:press_kit_create"), data)
        self.assertEqual(response.status_code, 200)
        errors = response.context["form"].errors
        self.assertIn("Communique cinema", errors["communications"][0])
        self.assertIn("Affiche cinema", errors["media"][0])
        self.assertFalse(PressKit.objects.exists())
        # Les choix déjà cochés restent cochés pour être corrigés.
        self.assertEqual(
            sorted(int(v) for v in response.context["form"]["communications"].value()),
            sorted([self.comm.pk, self.other_comm.pk]),
        )

    def test_press_kit_checkboxes_carry_their_event(self):
        response = self.client.get(reverse("communication_media:press_kit_create"))
        self.assertContains(response, f'data-event="{self.other_event.pk}"')
        self.assertContains(response, "event_choices.js")

    def test_press_kit_refuses_unknown_item(self):
        response = self.client.post(reverse("communication_media:press_kit_create"), self.kit_data(media=[9999]))
        self.assertIn("media", response.context["form"].errors)

    def test_media_communication_must_share_the_event(self):
        url = reverse("communication_media:media_create")
        data = {"event": self.event.pk, "name": "Photo", "media_type": "image", "file": png(), "communication": self.other_comm.pk}
        response = self.client.post(url, data)
        self.assertIn("autre événement", response.context["form"].errors["communication"][0])
        data.update(communication=self.comm.pk, file=png())
        self.assertEqual(self.client.post(url, data).status_code, 302)

    def test_item_in_a_press_kit_cannot_move_to_another_event(self):
        kit = PressKit.objects.create(title="Dossier", description="x", event=self.event)
        kit.communications.add(self.comm)
        url = reverse("communication_media:communication_update", args=[self.comm.pk])
        data = {"event": self.other_event.pk, "title": "Communique festival", "type": "communique",
                "content": "Texte", "language": "fr", "status": "brouillon", "publication_date": ""}
        response = self.client.post(url, data)
        self.assertIn("dossier de presse", response.context["form"].errors["event"][0])
        self.comm.refresh_from_db()
        self.assertEqual(self.comm.event, self.event)

    def test_communication_with_media_cannot_move_to_another_event(self):
        self.media.communication = self.comm
        self.media.save()
        url = reverse("communication_media:communication_update", args=[self.comm.pk])
        data = {"event": self.other_event.pk, "title": "Communique festival", "type": "communique",
                "content": "Texte", "language": "fr", "status": "brouillon", "publication_date": ""}
        response = self.client.post(url, data)
        self.assertIn("médias liés", response.context["form"].errors["event"][0])


class SeedCommandSafetyTests(TestCase):
    def test_seed_refuses_the_main_database(self):
        from unittest import mock

        from django.core.management import CommandError, call_command

        with mock.patch(
            "communication_media.management.commands.seed_communication_media.is_main_database",
            return_value=True,
        ):
            with self.assertRaises(CommandError):
                call_command("seed_communication_media")
        self.assertFalse(Communication.objects.exists())
