from django.test import TestCase
from django.urls import reverse

from .models import MediaContact


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


class MediaContactRoutesTests(TestCase):
    def test_generic_entity_route_leads_to_directory(self):
        url = reverse("communication_media:entity_list", args=["media-contacts"])
        self.assertEqual(url, reverse("communication_media:media_contact_list"))
        response = self.client.get(url)
        self.assertTemplateUsed(response, "communication_media/media_contacts/list.html")

    def test_module_home_links_to_directory(self):
        response = self.client.get(reverse("communication_media:home"))
        self.assertContains(response, reverse("communication_media:media_contact_list"))

    def test_other_entities_keep_their_placeholder(self):
        response = self.client.get(reverse("communication_media:entity_list", args=["publications"]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["placeholder"])


class MediaContactListTests(TestCase):
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


class MediaContactCreateTests(TestCase):
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


class MediaContactDetailTests(TestCase):
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


class MediaContactUpdateTests(TestCase):
    def setUp(self):
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


class MediaContactDeleteTests(TestCase):
    def setUp(self):
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
