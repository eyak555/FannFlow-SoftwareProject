from django.test import TestCase
from django.urls import reverse

from events_program.models import Event
from registration_access.models import Registration, Ticket
from users_teams.models import User

PASSWORD = "Str0ng-Pass!2026"


def make_user(email, **extra):
    extra.setdefault("first_name", "Test")
    extra.setdefault("last_name", "User")
    return User.objects.create_user(email=email, password=PASSWORD, **extra)


class CorePagesTests(TestCase):
    def test_home_page(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Communication &amp; Media", html=True)
        self.assertContains(response, "Découvrir les événements")
        self.assertContains(response, "Organiser un événement")
        self.assertContains(response, reverse("users_teams:register"))

    def test_home_shows_real_counts(self):
        participant = make_user("p@test.tn")
        Registration.objects.create(user=participant, event_id=1, ticket_type="standard")
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.context["snapshot"]["registrations"], 1)

    def test_home_shows_empty_event_catalog_when_no_events_are_published(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Aucun événement à venir")

    def test_public_events_page(self):
        response = self.client.get(reverse("core:events"))
        self.assertEqual(response.status_code, 200)

    def test_module_placeholder_page(self):
        self.client.force_login(make_user("orga@test.tn", business_role=User.BusinessRole.ORGANIZER))
        response = self.client.get(reverse("events_program:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Événement")
        self.assertContains(response, "bo-sidebar")


class BackOfficeAccessTests(TestCase):
    MODULE_URLS = [
        "events_program:home",
        "registration_access:home",
        "resources_operations:home",
        "sponsors_finance:home",
        "communication_media:home",
        "users_teams:home",
    ]

    def test_visitor_is_redirected_to_login(self):
        for name in self.MODULE_URLS:
            with self.subTest(name=name):
                url = reverse(name)
                self.assertRedirects(
                    self.client.get(url), f"{reverse('users_teams:login')}?next={url}", fetch_redirect_response=False
                )

    def test_participant_is_forbidden(self):
        self.client.force_login(make_user("p@test.tn"))
        for name in self.MODULE_URLS:
            if name == "registration_access:home":
                continue  # page d'accueil commune participants / équipe
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        listing = reverse("registration_access:entity_list", args=["registrations"])
        self.assertEqual(self.client.get(listing).status_code, 403)

    def test_participant_reaches_registration_participant_pages(self):
        self.client.force_login(make_user("p@test.tn"))
        for name in ("registration_access:home", "registration_access:my_registrations", "registration_access:my_tickets"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "bo-sidebar")  # affichées dans le site public

    def test_team_members_reach_backoffice(self):
        for role in (User.BusinessRole.DIRECTOR, User.BusinessRole.ORGANIZER):
            self.client.force_login(make_user(f"{role}@test.tn", business_role=role))
            for name in self.MODULE_URLS:
                with self.subTest(role=role, name=name):
                    self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_auth_pages_stay_public(self):
        for name in ("users_teams:login", "users_teams:register", "users_teams:password_forgotten"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)


class DashboardTests(TestCase):
    def test_director_dashboard_shows_finance(self):
        self.client.force_login(make_user("dir@test.tn", business_role=User.BusinessRole.DIRECTOR))
        response = self.client.get(reverse("users_teams:home"))
        self.assertEqual(response.status_code, 200)
        labels = [kpi["label"] for kpi in response.context["dashboard"]["kpis"]]
        self.assertIn("Recettes billetterie", labels)
        self.assertNotIn("Utilisateurs", labels)
        self.assertContains(response, "Évolution des inscriptions")

    def test_organizer_does_not_see_finance_or_users(self):
        self.client.force_login(make_user("orga@test.tn", business_role=User.BusinessRole.ORGANIZER))
        response = self.client.get(reverse("users_teams:home"))
        labels = [kpi["label"] for kpi in response.context["dashboard"]["kpis"]]
        self.assertNotIn("Utilisateurs", labels)
        self.assertNotIn("Recettes billetterie", labels)
        self.assertContains(response, "Billets par catégorie")

    def test_pending_registration_raises_alert(self):
        participant = make_user("p@test.tn")
        Registration.objects.create(user=participant, event_id=3, ticket_type="vip")
        self.client.force_login(make_user("dir@test.tn", business_role=User.BusinessRole.DIRECTOR))
        response = self.client.get(reverse("users_teams:home"))
        titles = [alert["title"] for alert in response.context["dashboard"]["alerts"]]
        self.assertTrue(any("en attente" in title for title in titles))
        self.assertEqual(response.context["dashboard"]["charts"]["evolution"][-1]["value"], 1)


class MySpaceTests(TestCase):
    def test_requires_login(self):
        url = reverse("core:my_space")
        self.assertRedirects(self.client.get(url), f"{reverse('users_teams:login')}?next={url}")

    def test_participant_sees_only_own_registrations(self):
        me = make_user("me@test.tn")
        other = make_user("other@test.tn")
        mine = Registration.objects.create(
            user=me, event_id=7, ticket_type="standard", status="confirmed", payment_status="paid"
        )
        Ticket.objects.create(registration=mine, price="10.00")
        Registration.objects.create(user=other, event_id=99, ticket_type="standard")
        self.client.force_login(me)
        response = self.client.get(reverse("core:my_space"))
        self.assertContains(response, "Événement n° 7")
        self.assertNotContains(response, "Événement n° 99")

    def test_team_member_is_sent_to_dashboard(self):
        self.client.force_login(make_user("orga@test.tn", business_role=User.BusinessRole.ORGANIZER))
        self.assertRedirects(self.client.get(reverse("core:my_space")), reverse("users_teams:home"))


class EventSearchTests(TestCase):
    """Filtres de la barre de recherche (mot clé, salle, période)."""

    def items(self):
        from datetime import timedelta
        from django.utils import timezone

        today = timezone.localdate()
        base = {"description": "", "category": "", "event_type": "", "image": "", "url": "", "pk": 0}
        return [
            {**base, "title": "Concert de jazz", "location": "Salle A", "start": today},
            {**base, "title": "Exposition photo", "location": "Galerie", "start": today + timedelta(days=40)},
        ]

    def test_keyword_venue_and_period(self):
        from core.views import filter_events

        items = self.items()
        self.assertEqual([i["title"] for i in filter_events(items, {"q": "JAZZ"})], ["Concert de jazz"])
        self.assertEqual([i["title"] for i in filter_events(items, {"salle": "Galerie"})], ["Exposition photo"])
        self.assertEqual([i["title"] for i in filter_events(items, {"date": "aujourdhui"})], ["Concert de jazz"])
        self.assertEqual(len(filter_events(items, {})), 2)

    def test_search_bar_on_home_and_events_page(self):
        for name in ("core:home", "core:events"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name), {"q": "x", "date": "semaine"})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="event-search"')

    def test_public_event_catalog_uses_database_pagination_and_filters(self):
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        for index in range(10):
            start = now + timedelta(days=index + 1)
            Event.objects.create(
                title=f"Concert {index:02d}",
                description="Musique et scène.",
                event_type=Event.EventType.CONCERT,
                category=Event.Category.MUSIC,
                start_date=start,
                end_date=start + timedelta(hours=2),
                registration_deadline=start - timedelta(days=1),
                capacity=100,
                location="Salle principale",
                status=Event.Status.PUBLISHED,
            )
        Event.objects.create(
            title="Conférence",
            description="Une autre catégorie.",
            event_type=Event.EventType.CONFERENCE,
            category=Event.Category.CONFERENCE,
            start_date=now + timedelta(days=2),
            end_date=now + timedelta(days=2, hours=2),
            registration_deadline=now + timedelta(days=1),
            capacity=100,
            location="Autre salle",
            status=Event.Status.PUBLISHED,
        )
        Event.objects.create(
            title="Brouillon caché",
            description="Non public.",
            event_type=Event.EventType.OTHER,
            category=Event.Category.OTHER,
            start_date=now + timedelta(days=2),
            end_date=now + timedelta(days=2, hours=2),
            registration_deadline=now + timedelta(days=1),
            capacity=100,
            location="Salle principale",
            status=Event.Status.DRAFT,
        )

        filters = {
            "q": "concert",
            "salle": "Salle principale",
            "categorie": Event.Category.MUSIC,
            "status": "upcoming",
            "sort": "title",
        }
        page_one = self.client.get(reverse("core:events"), filters)
        self.assertEqual(page_one.context["result_count"], 10)
        self.assertEqual(len(page_one.context["events"]["items"]), 9)
        self.assertEqual(page_one.context["events"]["items"][0]["title"], "Concert 00")
        self.assertContains(page_one, 'name="categorie"')
        self.assertContains(page_one, 'name="status"')
        self.assertContains(page_one, "status=upcoming")

        page_two = self.client.get(reverse("core:events"), {**filters, "page": 2})
        self.assertEqual(page_two.context["page_obj"].number, 2)
        self.assertEqual(
            [item["title"] for item in page_two.context["events"]["items"]],
            ["Concert 09"],
        )

        empty_result = self.client.get(reverse("core:events"), {**filters, "q": "aucun"})
        self.assertEqual(empty_result.context["result_count"], 0)
        self.assertContains(empty_result, "Aucun événement ne correspond")


class AccountSelfServiceTests(TestCase):
    """Fenêtre « Mon profil » : modification et suppression du compte par l'utilisateur."""

    def setUp(self):
        self.me = make_user("me@test.tn", first_name="Khadija", last_name="Test")
        self.client.force_login(self.me)

    def test_header_opens_profile_dialog(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'id="profile-dialog"')
        self.assertContains(response, 'data-dialog-open="profile-dialog"')
        self.assertContains(response, reverse("core:delete_account"))

    def test_profile_update(self):
        response = self.client.post(reverse("core:profile"), {
            "first_name": "Khadija", "last_name": "Nouveau", "phone": "+216 20 111 222",
            "birth_date": "1999-01-02", "next": reverse("core:events"),
            "role": User.Role.ADMIN,  # ignoré : non modifiable
        })
        self.assertRedirects(response, reverse("core:events"))
        self.me.refresh_from_db()
        self.assertEqual(self.me.last_name, "Nouveau")
        self.assertEqual(self.me.role, User.Role.PARTICIPANT)

    def test_profile_errors_render_page(self):
        response = self.client.post(reverse("core:profile"), {"first_name": "", "last_name": "X", "birth_date": "2999-01-01"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "La date de naissance doit être dans le passé.", status_code=400)

    def test_external_next_is_ignored(self):
        response = self.client.post(reverse("core:profile"), {
            "first_name": "K", "last_name": "T", "next": "https://evil.example/",
        })
        self.assertRedirects(response, reverse("core:my_space"))

    def test_password_change(self):
        response = self.client.post(reverse("core:password"), {
            "old_password": PASSWORD, "new_password1": "Autre-Mot!2026x", "new_password2": "Autre-Mot!2026x",
        })
        self.assertRedirects(response, reverse("core:my_space"))
        self.me.refresh_from_db()
        self.assertTrue(self.me.check_password("Autre-Mot!2026x"))

    def test_delete_requires_password_and_confirmation(self):
        url = reverse("core:delete_account")
        self.client.post(url, {"password": PASSWORD})
        self.client.post(url, {"password": "faux", "confirm": "1"})
        self.assertTrue(User.objects.filter(pk=self.me.pk).exists())

    def test_delete_own_account(self):
        Registration.objects.create(user=self.me, event_id=4, ticket_type="standard")
        response = self.client.post(reverse("core:delete_account"), {"password": PASSWORD, "confirm": "1"})
        self.assertRedirects(response, reverse("core:home"))
        self.assertFalse(User.objects.filter(pk=self.me.pk).exists())
        self.assertFalse(Registration.objects.filter(event_id=4).exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        from users_teams.models import AccountActivity
        self.assertEqual(AccountActivity.objects.get().target_label, "Khadija Test")

    def test_last_admin_cannot_delete_self(self):
        admin = make_user("admin@test.tn", role=User.Role.ADMIN)
        self.client.force_login(admin)
        self.client.post(reverse("core:delete_account"), {"password": PASSWORD, "confirm": "1"})
        self.assertTrue(User.objects.filter(pk=admin.pk).exists())

    def test_attendance_blocks_deletion(self):
        from registration_access.models import AccessPoint, Attendance

        reg = Registration.objects.create(user=self.me, event_id=5, ticket_type="standard",
                                          status="confirmed", payment_status="paid")
        ticket = Ticket.objects.create(registration=reg, price="0.00")
        point = AccessPoint.objects.create(event_id=5, name="Porte", location="Hall", capacity=10)
        Attendance.objects.create(ticket=ticket, access_point=point)
        response = self.client.post(reverse("core:delete_account"), {"password": PASSWORD, "confirm": "1"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.me.pk).exists())
        self.assertIn("_auth_user_id", self.client.session)
