from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events_program.models import Event
from .forms import VenueForm
from .models import Venue


class VenueCRUDTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.organizer = user_model.objects.create_user(
            email="venue-organizer@example.test",
            first_name="Nour",
            last_name="Organisateur",
            password="test-password",
            business_role=user_model.BusinessRole.ORGANIZER,
        )
        self.client.force_login(self.organizer)

    def venue_payload(self, **overrides):
        payload = {
            "name": "Cité de la Culture",
            "venue_type": Venue.VenueType.CULTURAL_CENTER,
            "address": "Avenue Mohamed V",
            "city": "Tunis",
            "latitude": "",
            "longitude": "",
            "capacity": "1200",
            "surface": "",
            "parking_capacity": "",
            "accessibility": "",
        }
        payload.update(overrides)
        return payload

    def test_create_and_list_venue_without_coordinates(self):
        response = self.client.post(
            reverse("resources_operations:entity_create", args=["venues"]),
            self.venue_payload(),
        )
        self.assertEqual(response.status_code, 302)
        venue = Venue.objects.get(name="Cité de la Culture")
        self.assertIsNone(venue.latitude)
        self.assertIsNone(venue.longitude)

        response = self.client.get(
            reverse("resources_operations:entity_list", args=["venues"]),
            {"q": "Tunis"},
        )
        self.assertContains(response, venue.name)
        self.assertContains(response, "Non renseignées")

    def test_coordinates_must_be_a_valid_pair(self):
        form = VenueForm(
            data=self.venue_payload(latitude="36.8000"),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("longitude", form.errors)

        form = VenueForm(
            data=self.venue_payload(latitude="91", longitude="10"),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("latitude", form.errors)

    def test_venue_associated_to_an_event_cannot_be_deleted(self):
        venue = Venue.objects.create(
            name="Amphithéâtre de Carthage",
            address="Carthage",
            city="Tunis",
        )
        now = timezone.now()
        Event.objects.create(
            title="Festival de Carthage",
            description="Événement culturel.",
            event_type=Event.EventType.FESTIVAL,
            category=Event.Category.CULTURAL,
            start_date=now + timedelta(days=5),
            end_date=now + timedelta(days=6),
            registration_deadline=now + timedelta(days=4),
            capacity=500,
            location=venue.name,
            venue=venue,
            director=self.organizer,
            status=Event.Status.DRAFT,
        )

        response = self.client.post(
            reverse(
                "resources_operations:entity_delete",
                args=["venues", venue.pk],
            )
        )
        self.assertRedirects(
            response,
            reverse(
                "resources_operations:entity_detail",
                args=["venues", venue.pk],
            ),
        )
        self.assertTrue(Venue.objects.filter(pk=venue.pk).exists())
        self.assertContains(
            self.client.get(
                reverse(
                    "resources_operations:entity_delete",
                    args=["venues", venue.pk],
                )
            ),
            "associé à un ou plusieurs événements",
        )
