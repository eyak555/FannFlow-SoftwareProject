from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
import base64
from datetime import timedelta
from decimal import Decimal

from .models import AccessPoint, Attendance, Registration, Ticket


class RegistrationAccessCrudTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = get_user_model().objects.create_user(
            email="participant@example.test",
            first_name="Ada",
            last_name="Participant",
            password="test-password",
        )
        self.admin = user_model.objects.create_superuser(
            email="admin@example.test",
            first_name="Admin",
            last_name="FannFlow",
            password="admin-password",
        )
        self.client.force_login(self.admin)
        self.registration = Registration.objects.create(
            user=self.user,
            event_id=12,
            status=Registration.STATUS_CONFIRMED,
            ticket_type=Registration.TICKET_TYPE_STANDARD,
            payment_status=Registration.PAYMENT_PAID,
        )
        self.ticket = Ticket.objects.create(
            registration=self.registration,
            price="25.00",
        )
        self.access_point = AccessPoint.objects.create(
            event_id=12,
            name="Entrée principale",
            location="Hall Nord",
            capacity=250,
        )
        self.attendance = Attendance.objects.create(
            ticket=self.ticket,
            access_point=self.access_point,
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

    def test_module_navigation_has_simple_previous_page_arrow(self):
        tickets_url = reverse(
            "registration_access:entity_list",
            args=["tickets"],
        )
        response = self.client.get(tickets_url)
        self.assertContains(response, 'aria-label="Retour à la page précédente"')
        self.assertContains(response, 'class="access-page-navigation__back"')
        self.assertContains(response, 'href="/registration/"')
        self.assertNotContains(response, 'class="access-page-navigation__steps"')

    def test_registration_form_shows_server_side_errors_next_to_invalid_fields(self):
        create_url = reverse(
            "registration_access:entity_create",
            args=["registrations"],
        )
        response = self.client.post(
            create_url,
            {
                "user": self.user.pk,
                "event_id": "",
                "status": Registration.STATUS_PENDING,
                "ticket_type": Registration.TICKET_TYPE_STANDARD,
                "payment_status": Registration.PAYMENT_PENDING,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "novalidate")
        self.assertContains(
            response,
            "Veuillez saisir le numéro de l’événement.",
        )
        self.assertContains(response, 'aria-invalid="true"')

    def test_registration_type_is_a_choice_and_ticket_code_is_generated(self):
        registration_form_response = self.client.get(
            reverse("registration_access:entity_create", args=["registrations"])
        )
        self.assertContains(registration_form_response, 'name="ticket_type"')
        self.assertContains(registration_form_response, 'value="standard"')
        self.assertContains(registration_form_response, 'value="vip"')
        self.assertContains(registration_form_response, 'value="group"')

        self.assertEqual(self.ticket.code, f"FF-{self.ticket.pk:06d}")
        second_ticket = Ticket.objects.create(
            registration=self.registration,
            price="15.00",
        )
        self.assertGreater(second_ticket.pk, self.ticket.pk)
        self.assertEqual(second_ticket.code, f"FF-{second_ticket.pk:06d}")

        ticket_form_response = self.client.get(
            reverse("registration_access:entity_create", args=["tickets"])
        )
        self.assertNotContains(ticket_form_response, 'name="code"')
        self.assertNotContains(ticket_form_response, "attribué automatiquement")

        update_response = self.client.get(
            reverse(
                "registration_access:entity_update",
                args=["tickets", self.ticket.pk],
            )
        )
        self.assertContains(update_response, self.ticket.code)

    def test_ticket_category_tracks_registration_type_changes(self):
        response = self.client.post(
            reverse(
                "registration_access:entity_update",
                args=["registrations", self.registration.pk],
            ),
            {
                "user": self.user.pk,
                "event_id": 12,
                "status": Registration.STATUS_CONFIRMED,
                "ticket_type": Registration.TICKET_TYPE_VIP,
                "payment_status": Registration.PAYMENT_PAID,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.category, Ticket.CATEGORY_VIP)

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
            ticket_type=Registration.TICKET_TYPE_VIP,
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
            price="40.00",
            category=Ticket.CATEGORY_VIP,
            status=Ticket.STATUS_USED,
        )
        response = self.client.get(
            reverse("registration_access:entity_list", args=["tickets"]),
            {
                "q": used_ticket.code,
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
            access_point=self.access_point,
            check_in=timezone.now(),
        )
        response = self.client.get(
            reverse("registration_access:entity_list", args=["attendances"]),
            {"q": "Entrée principale", "state": "checked_in"},
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

    def test_entity_lists_paginate_and_keep_search_filters(self):
        for entity in ("registrations", "tickets", "attendances", "access-points"):
            with self.subTest(entity=entity):
                response = self.client.get(
                    reverse("registration_access:entity_list", args=[entity])
                )
                self.assertEqual(response.context["paginator"].per_page, 25)
                self.assertEqual(
                    response.context["page_size_options"],
                    (10, 25, 50, 75, 100),
                )

        for event_id in range(100, 120):
            Registration.objects.create(
                user=self.user,
                event_id=event_id,
                ticket_type=Registration.TICKET_TYPE_STANDARD,
            )

        list_url = reverse("registration_access:entity_list", args=["registrations"])
        first_page = self.client.get(
            list_url,
            {"q": "participant@example.test", "per_page": 10},
        )
        self.assertEqual(first_page.context["paginator"].count, 21)
        self.assertEqual(first_page.context["paginator"].per_page, 10)
        self.assertEqual(first_page.context["page_obj"].number, 1)
        self.assertContains(
            first_page,
            '?page=2&amp;q=participant%40example.test&amp;per_page=10',
        )
        self.assertContains(first_page, 'aria-label="Page suivante"')

        second_page = self.client.get(
            list_url,
            {"q": "participant@example.test", "per_page": 10, "page": 2},
        )
        self.assertEqual(second_page.context["page_obj"].number, 2)
        self.assertEqual(len(second_page.context["registrations"]), 10)

    def test_create_update_and_delete_registration(self):
        create_url = reverse(
            "registration_access:entity_create",
            args=["registrations"],
        )
        response = self.client.post(create_url, {
            "user": self.user.pk,
            "event_id": 45,
            "status": Registration.STATUS_CONFIRMED,
            "ticket_type": Registration.TICKET_TYPE_VIP,
            "payment_status": Registration.PAYMENT_PAID,
        })
        created = Registration.objects.get(event_id=45)
        self.assertRedirects(
            response,
            reverse("registration_access:entity_list", args=["registrations"]),
        )
        issued_ticket = Ticket.objects.get(registration=created)
        self.assertEqual(issued_ticket.price, Decimal("10.00"))
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
            "ticket_type": Registration.TICKET_TYPE_VIP,
            "payment_status": Registration.PAYMENT_REFUNDED,
        })
        created.refresh_from_db()
        self.assertEqual(created.status, Registration.STATUS_CANCELLED)
        issued_ticket.refresh_from_db()
        self.assertEqual(issued_ticket.status, Ticket.STATUS_REFUND)
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
            "ticket_type": Registration.TICKET_TYPE_VIP,
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
            "ticket_type": Registration.TICKET_TYPE_VIP,
            "payment_status": Registration.PAYMENT_PENDING,
        })
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.STATUS_PENDING)

        response = self.client.post(update_url, {
            "user": self.user.pk,
            "event_id": 46,
            "status": Registration.STATUS_PENDING,
            "ticket_type": Registration.TICKET_TYPE_VIP,
            "payment_status": Registration.PAYMENT_PAID,
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

    def test_admin_cannot_confirm_a_paid_registration_before_prototype_payment(self):
        registration = Registration.objects.create(
            user=self.user,
            event_id=47,
            ticket_type=Registration.TICKET_TYPE_STANDARD,
        )
        ticket = Ticket.objects.create(
            registration=registration,
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
            "ticket_type": Registration.TICKET_TYPE_STANDARD,
            "payment_status": Registration.PAYMENT_PENDING,
        }
        response = self.client.post(update_url, payload)
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.STATUS_PENDING)

        payload["status"] = Registration.STATUS_PENDING
        payload["payment_status"] = Registration.PAYMENT_PAID
        response = self.client.post(update_url, payload)
        self.assertEqual(response.status_code, 302)
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.STATUS_CONFIRMED)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.STATUS_AVAILABLE)

    def test_ticket_form_rejects_availability_before_registration_confirmation(self):
        registration = Registration.objects.create(
            user=self.user,
            event_id=48,
            ticket_type=Registration.TICKET_TYPE_STANDARD,
        )
        response = self.client.post(
            reverse("registration_access:entity_create", args=["tickets"]),
            {
                "registration": registration.pk,
                "price": "0.00",
                "category": Ticket.CATEGORY_STANDARD,
                "status": Ticket.STATUS_AVAILABLE,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Ticket.objects.filter(registration=registration).exists())
        self.assertContains(response, "avant la confirmation")

    def test_ticket_price_validation_is_server_side_and_clear(self):
        create_url = reverse("registration_access:entity_create", args=["tickets"])
        base_payload = {
            "registration": self.registration.pk,
            "category": Ticket.CATEGORY_STANDARD,
            "status": Ticket.STATUS_AVAILABLE,
        }
        free_ticket_response = self.client.post(
            create_url,
            {**base_payload, "price": "0.00"},
        )
        self.assertEqual(free_ticket_response.status_code, 302)
        self.assertTrue(
            Ticket.objects.filter(
                registration=self.registration,
                price="0.00",
            ).exists()
        )

        cases = [
            ("-1.00", "Le prix du billet ne peut pas être négatif."),
            ("not-a-price", "Saisissez un montant valide, par exemple 25,00."),
        ]
        initial_count = Ticket.objects.count()

        for price, expected_error in cases:
            with self.subTest(price=price):
                response = self.client.post(
                    create_url,
                    {**base_payload, "price": price},
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected_error)
                self.assertEqual(Ticket.objects.count(), initial_count)

    def test_create_update_and_delete_related_records(self):
        attendance_registration = Registration.objects.create(
            user=self.user,
            event_id=12,
            status=Registration.STATUS_CONFIRMED,
            ticket_type=Registration.TICKET_TYPE_STANDARD,
            payment_status=Registration.PAYMENT_PAID,
        )
        attendance_ticket = Ticket.objects.create(
            registration=attendance_registration,
            price="10.00",
            status=Ticket.STATUS_AVAILABLE,
        )
        replacement_ticket = Ticket.objects.create(
            registration=attendance_registration,
            price="10.00",
            status=Ticket.STATUS_AVAILABLE,
        )
        cases = [
            (
                "tickets",
                {
                    "registration": self.registration.pk,
                    "price": "40.00",
                    "category": Ticket.CATEGORY_VIP,
                    "status": Ticket.STATUS_AVAILABLE,
                },
                Ticket,
                "category",
                Ticket.CATEGORY_VIP,
                Ticket.CATEGORY_GROUP,
            ),
            (
                "attendances",
                {
                    "ticket": attendance_ticket.pk,
                    "access_point": self.access_point.pk,
                    "check_in": "",
                    "check_out": "",
                },
                Attendance,
                "ticket",
                attendance_ticket,
                replacement_ticket,
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
                update_payload[changed_field] = (
                    updated_value.pk
                    if hasattr(updated_value, "pk")
                    else updated_value
                )
                update_url = reverse(
                    "registration_access:entity_update",
                    args=[entity, record.pk],
                )
                response = self.client.post(update_url, update_payload)
                self.assertEqual(response.status_code, 302)
                record.refresh_from_db()
                actual_value = (
                    getattr(record, f"{changed_field}_id")
                    if hasattr(updated_value, "pk")
                    else getattr(record, changed_field)
                )
                expected_value = (
                    updated_value.pk
                    if hasattr(updated_value, "pk")
                    else updated_value
                )
                self.assertEqual(actual_value, expected_value)

                delete_url = reverse(
                    "registration_access:entity_delete",
                    args=[entity, record.pk],
                )
                response = self.client.post(delete_url)
                self.assertEqual(response.status_code, 302)
                self.assertFalse(model.objects.filter(pk=record.pk).exists())

    def test_admin_crud_requires_an_administrator(self):
        self.client.logout()
        for entity in ("registrations", "tickets", "attendances", "access-points"):
            with self.subTest(entity=entity):
                response = self.client.get(
                    reverse("registration_access:entity_create", args=[entity])
                )
                self.assertEqual(response.status_code, 302)

        self.client.force_login(self.user)
        for entity in ("registrations", "tickets", "attendances", "access-points"):
            with self.subTest(entity=entity):
                response = self.client.get(
                    reverse("registration_access:entity_create", args=[entity])
                )
                self.assertEqual(response.status_code, 403)

        self.client.force_login(self.admin)
        for entity in ("registrations", "tickets", "attendances", "access-points"):
            with self.subTest(entity=entity):
                response = self.client.get(
                    reverse("registration_access:entity_create", args=[entity])
                )
                self.assertEqual(response.status_code, 200)

    def test_participant_registration_uses_logged_in_user_and_pending_states(self):
        another_user = get_user_model().objects.create_user(
            email="other@example.test",
            first_name="Other",
            last_name="Participant",
            password="test-password",
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("registration_access:registration_request"),
            {
                "event_id": 72,
                "ticket_type": Registration.TICKET_TYPE_VIP,
                "user": another_user.pk,
                "status": Registration.STATUS_CONFIRMED,
                "payment_status": Registration.PAYMENT_PAID,
            },
        )
        self.assertRedirects(response, reverse("registration_access:my_registrations"))
        registration = Registration.objects.get(event_id=72)
        self.assertEqual(registration.user, self.user)
        self.assertEqual(registration.status, Registration.STATUS_PENDING)
        self.assertEqual(registration.payment_status, Registration.PAYMENT_PENDING)
        ticket = Ticket.objects.get(registration=registration)
        self.assertEqual(ticket.category, Ticket.CATEGORY_VIP)
        self.assertEqual(ticket.status, Ticket.STATUS_PENDING)
        self.assertEqual(ticket.price, Decimal("10.00"))
        form_response = self.client.get(
            reverse("registration_access:registration_request")
        )
        self.assertContains(form_response, "Le paiement en ligne sera intégré au Sprint 2")

    def test_participant_lists_and_ticket_details_are_scoped_to_their_account(self):
        another_user = get_user_model().objects.create_user(
            email="other@example.test",
            first_name="Other",
            last_name="Participant",
            password="test-password",
        )
        other_registration = Registration.objects.create(
            user=another_user,
            event_id=73,
            ticket_type=Registration.TICKET_TYPE_STANDARD,
        )
        other_ticket = Ticket.objects.create(
            registration=other_registration,
            price="10.00",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("registration_access:my_registrations"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Événement 73")
        self.assertContains(response, "Événement 12")
        self.assertEqual(response.context["paginator"].count, 1)

        response = self.client.get(reverse("registration_access:my_tickets"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, other_ticket.code)
        self.assertEqual(response.context["paginator"].count, 1)

        response = self.client.get(
            reverse("registration_access:my_ticket_detail", args=[other_ticket.pk])
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse(
                "registration_access:registration_cancel",
                args=[other_registration.pk],
            )
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse(
                "registration_access:registration_confirm",
                args=[other_registration.pk],
            )
        )
        self.assertEqual(response.status_code, 404)
        other_registration.refresh_from_db()
        self.assertEqual(other_registration.status, Registration.STATUS_PENDING)

    def test_participant_can_confirm_a_free_ticket_and_view_its_qr(self):
        registration = Registration.objects.create(
            user=self.user,
            event_id=75,
            ticket_type=Registration.TICKET_TYPE_STANDARD,
        )
        ticket = Ticket.objects.create(
            registration=registration,
            price="0.00",
            status=Ticket.STATUS_PENDING,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("registration_access:my_tickets"))
        self.assertContains(response, "Confirmer")

        checkout_url = reverse(
            "registration_access:registration_confirm",
            args=[registration.pk],
        )
        response = self.client.get(checkout_url)
        self.assertContains(response, "Le montant est nul")
        self.assertNotContains(response, "Nom du payeur")

        response = self.client.post(
            checkout_url,
            {"confirmation": "on"},
            follow=True,
        )
        self.assertContains(response, "Votre billet gratuit est confirmé.")
        registration.refresh_from_db()
        ticket.refresh_from_db()
        self.assertEqual(registration.status, Registration.STATUS_CONFIRMED)
        self.assertEqual(
            registration.payment_status,
            Registration.PAYMENT_NOT_REQUIRED,
        )
        self.assertEqual(ticket.status, Ticket.STATUS_AVAILABLE)

        response = self.client.get(
            reverse("registration_access:my_ticket_detail", args=[ticket.pk])
        )
        self.assertContains(response, "data:image/svg+xml;base64,")

    def test_participant_simulates_payment_for_a_paid_ticket_without_real_charge(self):
        registration = Registration.objects.create(
            user=self.user,
            event_id=76,
            ticket_type=Registration.TICKET_TYPE_VIP,
        )
        ticket = Ticket.objects.create(
            registration=registration,
            price="25.00",
            status=Ticket.STATUS_PENDING,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("registration_access:my_tickets"))
        self.assertContains(response, "Payer")
        self.assertNotContains(response, "Simulation, sans débit réel")

        checkout_url = reverse(
            "registration_access:registration_confirm",
            args=[registration.pk],
        )
        response = self.client.get(checkout_url)
        self.assertContains(response, "Nom du titulaire")
        self.assertContains(response, "Numéro de carte")
        self.assertContains(response, "Date d’expiration")
        self.assertContains(response, "Cryptogramme visuel (CVV)")
        self.assertContains(response, "leur contenu n’est ni transmis ni enregistré")
        self.assertContains(response, 'autocomplete="off"')
        self.assertNotContains(response, 'name="card-number"')
        self.assertNotContains(response, 'name="card-security-code"')
        self.assertNotContains(response, "Je confirme le paiement de test")
        self.assertEqual(set(response.context["form"].fields), set())

        response = self.client.post(
            checkout_url,
            {
                "card-number": "anything",
                "card-expiration": "any date",
                "card-security-code": "anything",
            },
            follow=True,
        )
        self.assertContains(response, "Votre paiement de test est confirmé.")
        registration.refresh_from_db()
        ticket.refresh_from_db()
        self.assertEqual(registration.status, Registration.STATUS_CONFIRMED)
        self.assertEqual(registration.payment_status, Registration.PAYMENT_PAID)
        self.assertEqual(ticket.status, Ticket.STATUS_AVAILABLE)

    def test_participant_can_cancel_only_their_pending_request(self):
        self.client.force_login(self.user)
        home_response = self.client.get(reverse("registration_access:home"))
        self.assertContains(home_response, "Mes inscriptions")
        self.assertNotContains(home_response, "Gérer les inscriptions")

        response = self.client.post(
            reverse("registration_access:registration_request"),
            {
                "event_id": 74,
                "ticket_type": Registration.TICKET_TYPE_STANDARD,
            },
        )
        self.assertEqual(response.status_code, 302)
        registration = Registration.objects.get(event_id=74)
        response = self.client.post(
            reverse("registration_access:registration_cancel", args=[registration.pk])
        )
        self.assertRedirects(response, reverse("registration_access:my_registrations"))
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.STATUS_CANCELLED)
        self.assertEqual(registration.tickets.get().status, Ticket.STATUS_CANCELLED)

    def test_attendance_rejects_checkout_before_checkin(self):
        attendance = Attendance(
            ticket=self.ticket,
            access_point=self.access_point,
            check_in=timezone.now(),
            check_out=timezone.now() - timedelta(hours=1),
        )
        with self.assertRaisesMessage(ValidationError, "sortie"):
            attendance.full_clean()

    def test_check_in_and_check_out_validate_ticket_and_access_point(self):
        response = self.client.post(
            reverse("registration_access:attendance_check_in"),
            {
                "code": self.ticket.code,
                "access_point": self.access_point.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        attendance = Attendance.objects.get(
            ticket=self.ticket,
            check_in__isnull=False,
        )
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.STATUS_USED)
        self.assertEqual(self.access_point.current_occupancy, 1)

        response = self.client.post(
            reverse("registration_access:attendance_check_out", args=[attendance.pk])
        )
        self.assertEqual(response.status_code, 302)
        attendance.refresh_from_db()
        self.ticket.refresh_from_db()
        self.assertIsNotNone(attendance.check_out)
        self.assertEqual(self.ticket.status, Ticket.STATUS_USED)
        self.assertEqual(self.access_point.current_occupancy, 0)

        response = self.client.post(
            reverse("registration_access:attendance_check_in"),
            {
                "code": self.ticket.code,
                "access_point": self.access_point.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "n’est pas valide")
        self.assertEqual(
            Attendance.objects.filter(ticket=self.ticket, check_in__isnull=False).count(),
            1,
        )

    def test_check_in_enforces_event_match_and_point_capacity(self):
        other_event_point = AccessPoint.objects.create(
            event_id=99,
            name="Entrée autre événement",
            location="Hall Sud",
            capacity=2,
        )
        response = self.client.post(
            reverse("registration_access:attendance_check_in"),
            {
                "code": self.ticket.code,
                "access_point": other_event_point.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "autre événement")

        self.access_point.capacity = 1
        self.access_point.save()
        response = self.client.post(
            reverse("registration_access:attendance_check_in"),
            {
                "code": self.ticket.code,
                "access_point": self.access_point.pk,
            },
        )
        self.assertEqual(response.status_code, 302)

        second_registration = Registration.objects.create(
            user=self.user,
            event_id=12,
            status=Registration.STATUS_CONFIRMED,
            ticket_type=Registration.TICKET_TYPE_STANDARD,
            payment_status=Registration.PAYMENT_PAID,
        )
        second_ticket = Ticket.objects.create(
            registration=second_registration,
            price="10.00",
            status=Ticket.STATUS_AVAILABLE,
        )
        response = self.client.post(
            reverse("registration_access:attendance_check_in"),
            {
                "code": second_ticket.code,
                "access_point": self.access_point.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "capacité maximale")
        self.assertFalse(Attendance.objects.filter(ticket=second_ticket).exists())

    def test_checked_in_attendance_cannot_be_deleted_or_registration_cancelled(self):
        attendance = Attendance.objects.create(
            ticket=self.ticket,
            access_point=self.access_point,
            check_in=timezone.now(),
        )
        self.ticket.status = Ticket.STATUS_USED
        self.ticket.save(update_fields=["status"])

        response = self.client.post(
            reverse(
                "registration_access:entity_delete",
                args=["attendances", attendance.pk],
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Attendance.objects.filter(pk=attendance.pk).exists())

        response = self.client.post(
            reverse(
                "registration_access:entity_update",
                args=["registrations", self.registration.pk],
            ),
            {
                "user": self.user.pk,
                "event_id": 12,
                "status": Registration.STATUS_CANCELLED,
                "ticket_type": Registration.TICKET_TYPE_STANDARD,
                "payment_status": Registration.PAYMENT_REFUNDED,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.STATUS_CONFIRMED)
