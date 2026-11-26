from io import BytesIO
import os
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from registration_access.forms import ParticipantRegistrationForm
from registration_access.models import Registration
from .forms import ActivityForm, EventForm
from .models import Activity, Event, Speaker


class EventProgramTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.organizer = user_model.objects.create_user(
            email="organizer@example.test",
            first_name="Ada",
            last_name="Organizer",
            password="test-password",
            business_role=user_model.BusinessRole.ORGANIZER,
        )
        self.participant = user_model.objects.create_user(
            email="participant@example.test",
            first_name="Sam",
            last_name="Participant",
            password="test-password",
        )
        self.client.force_login(self.organizer)
        self.now = timezone.now()
        self.media_dir = tempfile.TemporaryDirectory()
        self.media_settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.addCleanup(self.media_dir.cleanup)

    def make_event(self, **kwargs):
        defaults = {
            "title": "Festival de printemps",
            "description": "Un rendez-vous culturel.",
            "event_type": Event.EventType.FESTIVAL,
            "category": Event.Category.MUSIC,
            "start_date": self.now + timedelta(days=5),
            "end_date": self.now + timedelta(days=6),
            "registration_deadline": self.now + timedelta(days=4),
            "capacity": 250,
            "ticket_price": Decimal("12.50"),
            "location": "Tunis",
            "director": self.organizer,
            "status": Event.Status.PUBLISHED,
        }
        defaults.update(kwargs)
        return Event.objects.create(**defaults)

    def uploaded_image(self, name="poster.png", color=(65, 110, 150)):
        image_buffer = BytesIO()
        Image.new("RGB", (4, 3), color=color).save(image_buffer, format="PNG")
        return SimpleUploadedFile(name, image_buffer.getvalue(), content_type="image/png")

    def event_form_payload(self, title="Nouvel événement"):
        start = timezone.localtime(self.now + timedelta(days=4))
        end = timezone.localtime(self.now + timedelta(days=5))
        deadline = timezone.localtime(self.now + timedelta(days=3))
        return {
            "title": title,
            "description": "Description complète.",
            "event_type": Event.EventType.CONCERT,
            "category": Event.Category.HACKATHON,
            "start_date": start.strftime("%Y-%m-%dT%H:%M"),
            "end_date": end.strftime("%Y-%m-%dT%H:%M"),
            "registration_deadline": deadline.strftime("%Y-%m-%dT%H:%M"),
            "capacity": 100,
            "ticket_price": "5.00",
            "vip_ticket_price": "15.00",
            "location": "Salle principale",
            "director": self.organizer.pk,
            "status": Event.Status.PUBLISHED,
        }

    def test_event_crud_is_connected_to_active_users_and_validates_dates(self):
        self.assertIn(
            self.organizer,
            EventForm().fields["director"].queryset,
        )
        self.assertNotIn(
            self.participant,
            EventForm().fields["director"].queryset,
        )

        invalid = EventForm(
            data={
                "title": "Dates incohérentes",
                "description": "Description",
                "event_type": Event.EventType.CONCERT,
                "category": "",
                "start_date": (self.now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                "end_date": (self.now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "registration_deadline": (self.now + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
                "capacity": 10,
                "ticket_price": "0.00",
                "location": "Tunis",
                "director": self.organizer.pk,
                "status": Event.Status.DRAFT,
            }
        )
        self.assertFalse(invalid.is_valid())
        self.assertIn("end_date", invalid.errors)
        self.assertIn("registration_deadline", invalid.errors)

        self.assertEqual(self.client.get(reverse("events_program:entity_list", args=["events"])).status_code, 200)
        event = self.make_event()
        detail = self.client.get(
            reverse("events_program:entity_detail", args=["events", event.pk])
        )
        self.assertContains(detail, "Festival de printemps")
        delete_url = reverse("events_program:entity_delete", args=["events", event.pk])
        self.assertEqual(self.client.post(delete_url).status_code, 302)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())

    def test_event_can_be_created_through_the_crud_form(self):
        response = self.client.post(
            reverse("events_program:entity_create", args=["events"]),
            self.event_form_payload(),
        )
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title="Nouvel événement")
        self.assertEqual(event.director, self.organizer)
        self.assertEqual(event.ticket_price, Decimal("5.00"))
        self.assertEqual(event.vip_ticket_price, Decimal("15.00"))

    def test_event_image_upload_default_fallback_and_public_card(self):
        create_url = reverse("events_program:entity_create", args=["events"])
        response = self.client.post(
            create_url,
            {**self.event_form_payload("Hackathon illustré"), "image": self.uploaded_image()},
        )
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title="Hackathon illustré")
        self.assertTrue(event.image)
        self.assertTrue(os.path.exists(event.image.path))
        self.assertIn("events/hackathon/", event.image.name)

        no_image_event = self.make_event(
            title="Sans image importée",
            category=Event.Category.CINEMA,
        )
        self.assertFalse(no_image_event.image)
        self.assertEqual(
            no_image_event.display_image_url,
            "/static/events_program/images/cinema.svg",
        )
        response = self.client.get(reverse("core:events"))
        self.assertContains(response, "/static/events_program/images/cinema.svg")
        self.assertContains(response, "Hackathon illustré")
        self.assertContains(response, "Voir les détails")

    def test_event_image_can_be_replaced_and_is_deleted_with_event(self):
        event = self.make_event(category=Event.Category.WORKSHOP)
        event.image = self.uploaded_image("first.png")
        event.save()
        old_image_path = event.image.path
        edit_url = reverse("events_program:entity_update", args=["events", event.pk])

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                edit_url,
                {
                    **self.event_form_payload(event.title),
                    "image": self.uploaded_image("replacement.png", color=(150, 70, 50)),
                },
            )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertTrue(os.path.exists(event.image.path))
        self.assertFalse(os.path.exists(old_image_path))

        image_path = event.image.path
        delete_url = reverse("events_program:entity_delete", args=["events", event.pk])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(os.path.exists(image_path))

    def test_event_image_upload_rejects_non_image_files(self):
        response = self.client.post(
            reverse("events_program:entity_create", args=["events"]),
            {
                **self.event_form_payload("Fichier invalide"),
                "image": SimpleUploadedFile(
                    "not-an-image.png",
                    b"not an image",
                    content_type="image/png",
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "image")
        self.assertFalse(Event.objects.filter(title="Fichier invalide").exists())

    def test_event_delete_is_blocked_when_registration_references_it(self):
        event = self.make_event()
        Registration.objects.create(
            user=self.participant,
            event_id=event.pk,
            ticket_type=Registration.TICKET_TYPE_STANDARD,
        )
        delete_url = reverse("events_program:entity_delete", args=["events", event.pk])
        response = self.client.get(delete_url)
        self.assertContains(response, "Des inscriptions sont liées")
        self.client.post(delete_url)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())

    def test_activities_can_be_added_to_events_and_link_multiple_speakers(self):
        event = self.make_event()
        speakers = [
            Speaker.objects.create(name="Nour Haddad"),
            Speaker.objects.create(name="Youssef Ben Ali"),
        ]
        start = event.start_date + timedelta(hours=1)
        end = start + timedelta(hours=2)
        response = self.client.post(
            reverse("events_program:entity_create", args=["activities"]),
            {
                "event": event.pk,
                "title": "Atelier de musique",
                "description": "Initiation et pratique.",
                "activity_type": "Atelier",
                "start_time": timezone.localtime(start).strftime("%Y-%m-%dT%H:%M"),
                "end_time": timezone.localtime(end).strftime("%Y-%m-%dT%H:%M"),
                "capacity": 30,
                "room": "Salle A",
                "speakers": [speaker.pk for speaker in speakers],
            },
        )
        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(title="Atelier de musique")
        selected_ids = {speaker.pk for speaker in speakers}
        self.assertEqual(set(activity.speakers.values_list("pk", flat=True)), selected_ids)
        self.assertEqual(activity.event, event)

    def test_activity_date_must_fit_inside_parent_event(self):
        event = self.make_event()
        activity = Activity(
            event=event,
            title="Hors programme",
            activity_type="Conférence",
            start_time=event.end_date + timedelta(hours=1),
            end_time=event.end_date + timedelta(hours=2),
        )
        form = ActivityForm(
            data={
                "event": event.pk,
                "title": activity.title,
                "description": "",
                "activity_type": activity.activity_type,
                "start_time": timezone.localtime(activity.start_time).strftime("%Y-%m-%dT%H:%M"),
                "end_time": timezone.localtime(activity.end_time).strftime("%Y-%m-%dT%H:%M"),
                "capacity": "",
                "room": "",
                "speakers": [],
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("start_time", form.errors)

    def test_public_catalog_exposes_only_published_events_and_registration_prefills_event(self):
        event = self.make_event()
        draft = self.make_event(title="Événement privé", status=Event.Status.DRAFT)

        response = self.client.get(event.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, event.title)
        self.assertContains(response, reverse("registration_access:registration_request"))
        self.assertEqual(
            self.client.get(draft.get_absolute_url()).status_code,
            404,
        )

        self.client.force_login(self.participant)
        registration_page = self.client.get(
            reverse("registration_access:registration_request"),
            {"event_id": event.pk},
        )
        self.assertEqual(registration_page.context["form"].initial["event_id"], event.pk)

    def test_dashboard_counts_events_by_published_lifecycle_state(self):
        self.make_event(title="À venir")
        self.make_event(
            title="En cours",
            start_date=self.now - timedelta(hours=1),
            end_date=self.now + timedelta(hours=1),
            registration_deadline=self.now - timedelta(hours=2),
        )
        self.make_event(
            title="Terminé",
            start_date=self.now - timedelta(days=2),
            end_date=self.now - timedelta(days=1),
            registration_deadline=self.now - timedelta(days=3),
        )
        self.make_event(title="Brouillon", status=Event.Status.DRAFT)
        self.client.get(reverse("events_program:home"))
        from .views import event_dashboard

        counts = event_dashboard()["counts"]
        self.assertEqual(counts["total"], 4)
        self.assertEqual(counts["upcoming"], 1)
        self.assertEqual(counts["ongoing"], 1)
        self.assertEqual(counts["completed"], 1)
        self.assertEqual(counts["draft"], 1)

    def test_registration_ticket_uses_event_price(self):
        event = self.make_event()
        registration = Registration.objects.create(
            user=self.participant,
            event_id=event.pk,
            ticket_type=Registration.TICKET_TYPE_STANDARD,
        )
        from registration_access.services import create_registration_ticket

        ticket = create_registration_ticket(registration)
        self.assertEqual(ticket.price, event.ticket_price)

    def test_vip_registration_uses_vip_event_price(self):
        event = self.make_event(vip_ticket_price=Decimal("29.90"))
        registration = Registration.objects.create(
            user=self.participant,
            event_id=event.pk,
            ticket_type=Registration.TICKET_TYPE_VIP,
        )
        from registration_access.services import create_registration_ticket

        ticket = create_registration_ticket(registration)
        self.assertEqual(ticket.price, Decimal("29.90"))
        self.assertEqual(ticket.category, "vip")

    def test_age_restriction_is_displayed_and_blocks_ineligible_registrations(self):
        event = self.make_event(
            minimum_age=18,
            maximum_age=30,
            vip_ticket_price=Decimal("29.90"),
        )
        event_day = timezone.localtime(event.start_date).date()
        self.assertEqual(event.age_requirement_display, "De 18 à 30 ans")
        form_without_birth_date = ParticipantRegistrationForm(
            data={
                "event_id": event.pk,
                "ticket_type": Registration.TICKET_TYPE_STANDARD,
            },
            user=self.participant,
        )
        self.assertFalse(form_without_birth_date.is_valid())
        self.assertIn("event_id", form_without_birth_date.errors)
        self.assertContains(
            self.client.get(event.get_absolute_url()),
            "De 18 à 30 ans",
        )

        self.participant.birth_date = event_day.replace(year=event_day.year - 17)
        self.participant.save(update_fields=["birth_date"])
        underage_form = ParticipantRegistrationForm(
            data={
                "event_id": event.pk,
                "ticket_type": Registration.TICKET_TYPE_STANDARD,
            },
            user=self.participant,
        )
        self.assertFalse(underage_form.is_valid())
        self.assertIn("réservé aux personnes de 18 ans", str(underage_form.errors))

        self.client.force_login(self.participant)
        blocked_response = self.client.post(
            reverse("registration_access:registration_request"),
            {
                "event_id": event.pk,
                "ticket_type": Registration.TICKET_TYPE_STANDARD,
            },
        )
        self.assertEqual(blocked_response.status_code, 200)
        self.assertFalse(
            Registration.objects.filter(user=self.participant, event_id=event.pk).exists()
        )

        self.participant.birth_date = event_day.replace(year=event_day.year - 20)
        self.participant.save(update_fields=["birth_date"])
        eligible_form = ParticipantRegistrationForm(
            data={
                "event_id": event.pk,
                "ticket_type": Registration.TICKET_TYPE_VIP,
            },
            user=self.participant,
        )
        self.assertTrue(eligible_form.is_valid(), eligible_form.errors)
        response = self.client.post(
            reverse("registration_access:registration_request"),
            {
                "event_id": event.pk,
                "ticket_type": Registration.TICKET_TYPE_VIP,
            },
        )
        self.assertEqual(response.status_code, 302)
        registration = Registration.objects.get(user=self.participant, event_id=event.pk)
        self.assertEqual(registration.tickets.get().price, Decimal("29.90"))

    def test_participant_registration_obeys_event_capacity(self):
        event = self.make_event(capacity=1)
        Registration.objects.create(
            user=self.participant,
            event_id=event.pk,
            ticket_type=Registration.TICKET_TYPE_STANDARD,
        )
        form = ParticipantRegistrationForm(
            data={
                "event_id": event.pk,
                "ticket_type": Registration.TICKET_TYPE_STANDARD,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("event_id", form.errors)
        self.assertIn("capacité maximale", str(form.errors))

    def test_public_event_pagination_handles_invalid_and_out_of_range_pages(self):
        for index in range(11):
            self.make_event(
                title=f"Concert {index:02d}",
                start_date=self.now + timedelta(days=index + 1),
                end_date=self.now + timedelta(days=index + 1, hours=2),
                registration_deadline=self.now + timedelta(days=index),
            )

        first_page = self.client.get(reverse("core:events"))
        self.assertEqual(first_page.context["result_count"], 11)
        self.assertEqual(first_page.context["page_obj"].number, 1)
        self.assertEqual(len(first_page.context["events"]["items"]), 9)
        self.assertContains(first_page, "Suivant")

        second_page = self.client.get(reverse("core:events"), {"page": 2})
        self.assertEqual(second_page.context["page_obj"].number, 2)
        self.assertEqual(len(second_page.context["events"]["items"]), 2)
        self.assertContains(second_page, "Précédent")

        invalid_page = self.client.get(reverse("core:events"), {"page": "abc"})
        self.assertEqual(invalid_page.context["page_obj"].number, 1)
        missing_page = self.client.get(reverse("core:events"), {"page": 100})
        self.assertEqual(missing_page.context["page_obj"].number, 2)

    def test_event_search_and_filters_are_applied_before_pagination_and_preserved(self):
        for index in range(10):
            start = self.now + timedelta(days=1, hours=index)
            self.make_event(
                title=f"Concert {index:02d}",
                description="Un programme musical.",
                location="Salle A",
                category=Event.Category.MUSIC,
                start_date=start,
                end_date=start + timedelta(hours=2),
                registration_deadline=start - timedelta(hours=1),
            )
        self.make_event(
            title="Conférence différente",
            category=Event.Category.CONFERENCE,
            location="Salle B",
        )

        filters = {
            "q": "concert",
            "salle": "Salle A",
            "date": "semaine",
            "categorie": Event.Category.MUSIC,
            "status": "upcoming",
            "sort": "title",
        }
        first_page = self.client.get(reverse("core:events"), filters)
        self.assertEqual(first_page.context["result_count"], 10)
        self.assertEqual(first_page.context["page_obj"].number, 1)
        self.assertEqual(first_page.context["events"]["items"][0]["title"], "Concert 00")
        self.assertContains(first_page, "q=concert")
        self.assertContains(first_page, "categorie=music_festival")
        self.assertContains(first_page, "status=upcoming")

        next_page_query = {**filters, "page": 2}
        second_page = self.client.get(reverse("core:events"), next_page_query)
        self.assertEqual(second_page.context["page_obj"].number, 2)
        self.assertEqual(
            [event["title"] for event in second_page.context["events"]["items"]],
            ["Concert 09"],
        )

        changed_criteria = self.client.get(
            reverse("core:events"),
            {**filters, "q": "introuvable", "page": 1},
        )
        self.assertEqual(changed_criteria.context["result_count"], 0)
        self.assertContains(changed_criteria, "Aucun événement ne correspond")
