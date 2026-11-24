from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
import base64
from datetime import timedelta

from .models import AccessPoint, Attendance, Registration, Ticket


class RegistrationAccessCrudTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="participant",
            password="test-password",
        )
        self.registration = Registration.objects.create(
            user=self.user,
            event_id=12,
            status=Registration.STATUS_CONFIRMED,
            ticket_type="Standard",
            payment_status=Registration.PAYMENT_PAID,
        )
        self.ticket = Ticket.objects.create(
            registration=self.registration,
            qr_code="QR-TEST-001",
            price="25.00",
        )
        self.attendance = Attendance.objects.create(
            ticket=self.ticket,
            gate="Portail A",
        )
        self.access_point = AccessPoint.objects.create(
            event_id=12,
            name="Entrée principale",
            location="Hall Nord",
            capacity=250,
        )

    def test_registration_access_homepage_uses_module_template_and_brand(self):
        response = self.client.get(reverse("registration_access:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "registration_access/home.html",
        )
        self.assertContains(response, "De l’inscription à l’entrée")
        self.assertContains(response, "Inscriptions")
        self.assertContains(response, "Points d’accès")

    def test_lists_and_details_use_model_templates(self):
        pages = [
            ("registrations", self.registration.pk),
            ("tickets", self.ticket.pk),
            ("attendances", self.attendance.pk),
            ("access-points", self.access_point.pk),
        ]
        for entity, pk in pages:
            with self.subTest(entity=entity):
                list_url = reverse(
                    "registration_access:entity_list",
                    args=[entity],
                )
                detail_url = reverse(
                    "registration_access:entity_detail",
                    args=[entity, pk],
                )
                self.assertEqual(self.client.get(list_url).status_code, 200)
                detail_response = self.client.get(detail_url)
                self.assertEqual(detail_response.status_code, 200)
                self.assertContains(detail_response, "detail-grid")
                self.assertContains(detail_response, "detail-item")

    def test_registration_search_status_and_payment_filters(self):
        confirmed = Registration.objects.create(
            user=self.user,
            event_id=13,
            status=Registration.STATUS_CONFIRMED,
            ticket_type="VIP",
            payment_status=Registration.PAYMENT_PAID,
        )
        response = self.client.get(
            reverse("registration_access:entity_list", args=["registrations"]),
            {"q": "13", "status": Registration.STATUS_CONFIRMED, "payment": Registration.PAYMENT_PAID},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["registrations"]), [confirmed])
        self.assertEqual(response.context["registration_stats"]["total"], 2)
        self.assertContains(response, "status-pill--success")
        self.assertContains(response, "Filtres actifs")

    def test_ticket_list_search_and_filters(self):
        used_ticket = Ticket.objects.create(
            registration=self.registration,
            qr_code="QR-USED-002",
            price="40.00",
            category=Ticket.CATEGORY_VIP,
            status=Ticket.STATUS_USED,
        )
        response = self.client.get(
            reverse("registration_access:entity_list", args=["tickets"]),
            {
                "q": "QR-USED",
                "category": Ticket.CATEGORY_VIP,
                "status": Ticket.STATUS_USED,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["tickets"]), [used_ticket])
        self.assertEqual(response.context["ticket_stats"]["total"], 2)
        self.assertContains(response, "Filtres actifs")

    def test_attendance_list_search_and_state_filter(self):
        checked_in = Attendance.objects.create(
            ticket=self.ticket,
            gate="Portail B",
            check_in=timezone.now(),
        )
        response = self.client.get(
            reverse("registration_access:entity_list", args=["attendances"]),
            {"q": "Portail B", "state": "checked_in"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["attendances"]), [checked_in])
        self.assertEqual(response.context["attendance_stats"]["on_site"], 1)

    def test_access_point_list_search_and_capacity_summary(self):
        response = self.client.get(
            reverse("registration_access:entity_list", args=["access-points"]),
            {"q": "Hall Nord"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["access_points"]), [self.access_point])
        self.assertEqual(response.context["access_point_stats"]["total"], 1)
        self.assertEqual(response.context["access_point_stats"]["capacity"], 250)

    def test_create_update_and_delete_registration(self):
        create_url = reverse(
            "registration_access:entity_create",
            args=["registrations"],
        )
        response = self.client.post(create_url, {
            "user": self.user.pk,
            "event_id": 45,
            "status": Registration.STATUS_CONFIRMED,
            "ticket_type": "VIP",
            "payment_status": Registration.PAYMENT_PAID,
        })
        created = Registration.objects.get(event_id=45)
        self.assertRedirects(
            response,
            reverse("registration_access:entity_list", args=["registrations"]),
        )
        issued_ticket = Ticket.objects.get(registration=created)
        self.assertEqual(issued_ticket.price, 0)
        self.assertEqual(issued_ticket.category, Ticket.CATEGORY_VIP)
        self.assertEqual(issued_ticket.status, Ticket.STATUS_AVAILABLE)

        update_url = reverse(
            "registration_access:entity_update",
            args=["registrations", created.pk],
        )
        response = self.client.post(update_url, {
            "user": self.user.pk,
            "event_id": 45,
            "status": Registration.STATUS_CANCELLED,
            "ticket_type": "VIP",
            "payment_status": Registration.PAYMENT_REFUNDED,
        })
        created.refresh_from_db()
        self.assertEqual(created.status, Registration.STATUS_CANCELLED)
        issued_ticket.refresh_from_db()
        self.assertEqual(issued_ticket.status, Ticket.STATUS_CANCELLED)
        self.assertEqual(response.status_code, 302)

        delete_url = reverse(
            "registration_access:entity_delete",
            args=["registrations", created.pk],
        )
        response = self.client.post(delete_url)
        self.assertRedirects(
            response,
            reverse("registration_access:entity_list", args=["registrations"]),
        )
        self.assertFalse(Registration.objects.filter(pk=created.pk).exists())

    def test_registration_ticket_qr_is_unlocked_after_confirmation_and_payment(self):
        create_url = reverse(
            "registration_access:entity_create",
            args=["registrations"],
        )
        self.client.post(create_url, {
            "user": self.user.pk,
            "event_id": 46,
            "status": Registration.STATUS_PENDING,
            "ticket_type": "VIP",
            "payment_status": Registration.PAYMENT_PENDING,
        })
        registration = Registration.objects.get(event_id=46)
        ticket = Ticket.objects.get(registration=registration)
        self.assertEqual(ticket.status, Ticket.STATUS_PENDING)

        ticket_detail_url = reverse(
            "registration_access:entity_detail",
            args=["tickets", ticket.pk],
        )
        pending_response = self.client.get(ticket_detail_url)
        self.assertNotContains(pending_response, "data:image/svg+xml;base64,")
        self.assertContains(pending_response, "Le QR sera disponible")

        update_url = reverse(
            "registration_access:entity_update",
            args=["registrations", registration.pk],
        )
        response = self.client.post(update_url, {
            "user": self.user.pk,
            "event_id": 46,
            "status": Registration.STATUS_CONFIRMED,
            "ticket_type": "VIP",
            "payment_status": Registration.PAYMENT_PENDING,
        })
        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.STATUS_AVAILABLE)
        available_response = self.client.get(ticket_detail_url)
        self.assertContains(available_response, "data:image/svg+xml;base64,")
        self.assertContains(available_response, "<img")
        qr_svg = base64.b64decode(
            available_response.context["qr_code_image"].partition(",")[2]
        )
        self.assertIn(b"<svg", qr_svg)

    def test_paid_ticket_waits_for_payment_even_after_confirmation(self):
        registration = Registration.objects.create(
            user=self.user,
            event_id=47,
            ticket_type="Standard",
        )
        ticket = Ticket.objects.create(
            registration=registration,
            qr_code="QR-PAID-003",
            price="25.00",
            status=Ticket.STATUS_PENDING,
        )
        update_url = reverse(
            "registration_access:entity_update",
            args=["registrations", registration.pk],
        )
        payload = {
            "user": self.user.pk,
            "event_id": 47,
            "status": Registration.STATUS_CONFIRMED,
            "ticket_type": "Standard",
            "payment_status": Registration.PAYMENT_PENDING,
        }
        self.client.post(update_url, payload)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.STATUS_PENDING)

        payload["payment_status"] = Registration.PAYMENT_PAID
        self.client.post(update_url, payload)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.STATUS_AVAILABLE)

    def test_ticket_form_rejects_availability_before_registration_confirmation(self):
        registration = Registration.objects.create(
            user=self.user,
            event_id=48,
            ticket_type="Standard",
        )
        response = self.client.post(
            reverse("registration_access:entity_create", args=["tickets"]),
            {
                "registration": registration.pk,
                "qr_code": "QR-EARLY-004",
                "price": "0.00",
                "category": Ticket.CATEGORY_STANDARD,
                "status": Ticket.STATUS_AVAILABLE,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Ticket.objects.filter(qr_code="QR-EARLY-004").exists())
        self.assertContains(response, "avant la confirmation")

    def test_create_update_and_delete_related_records(self):
        cases = [
            (
                "tickets",
                {
                    "registration": self.registration.pk,
                    "qr_code": "QR-NEW-02",
                    "price": "40.00",
                    "category": Ticket.CATEGORY_VIP,
                    "status": Ticket.STATUS_AVAILABLE,
                },
                Ticket,
                "qr_code",
                "QR-NEW-02",
                "QR-UPDATED-02",
            ),
            (
                "attendances",
                {
                    "ticket": self.ticket.pk,
                    "check_in": "",
                    "check_out": "",
                    "gate": "Portail B",
                },
                Attendance,
                "gate",
                "Portail B",
                "Portail C",
            ),
            (
                "access-points",
                {
                    "event_id": 12,
                    "name": "Entrée secondaire",
                    "location": "Hall Sud",
                    "capacity": 100,
                },
                AccessPoint,
                "name",
                "Entrée secondaire",
                "Entrée mise à jour",
            ),
        ]

        for entity, payload, model, changed_field, initial_value, updated_value in cases:
            with self.subTest(entity=entity):
                create_url = reverse(
                    "registration_access:entity_create",
                    args=[entity],
                )
                response = self.client.post(create_url, payload)
                self.assertEqual(response.status_code, 302)
                record = model.objects.get(**{changed_field: initial_value})

                update_payload = dict(payload)
                update_payload[changed_field] = updated_value
                update_url = reverse(
                    "registration_access:entity_update",
                    args=[entity, record.pk],
                )
                response = self.client.post(update_url, update_payload)
                self.assertEqual(response.status_code, 302)
                record.refresh_from_db()
                self.assertEqual(getattr(record, changed_field), updated_value)

                delete_url = reverse(
                    "registration_access:entity_delete",
                    args=[entity, record.pk],
                )
                response = self.client.post(delete_url)
                self.assertEqual(response.status_code, 302)
                self.assertFalse(model.objects.filter(pk=record.pk).exists())

    def test_create_views_are_accessible_without_authentication(self):
        for entity in ("registrations", "tickets", "attendances", "access-points"):
            with self.subTest(entity=entity):
                response = self.client.get(
                    reverse("registration_access:entity_create", args=[entity])
                )
                self.assertEqual(response.status_code, 200)

    def test_attendance_rejects_checkout_before_checkin(self):
        attendance = Attendance(
            ticket=self.ticket,
            gate="Portail A",
            check_in=timezone.now(),
            check_out=timezone.now() - timedelta(hours=1),
        )
        with self.assertRaisesMessage(ValidationError, "sortie"):
            attendance.full_clean()
