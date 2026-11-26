from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import EventRequirements, Resource, ResourceAllocation, Venue
from .reports import WEEK, week_start
from .tests import create_event, create_user


class OperationsPlanningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = create_user("planning-admin", admin=True)
        cls.director = create_user("planning-director", director=True)
        cls.resource = Resource.objects.create(
            name="Projecteur", type="Lumière", quantity=4, unit_cost="25.00", location="Régie",
        )
        cls.event = create_event(cls.director, pk=7, title="Festival Lumière", capacity=80)

    def url(self, name, *args):
        return reverse(f"resources_operations:{name}", args=args)

    def test_director_manages_event_needs_and_compares_venue_without_inventory_access(self):
        self.client.force_login(self.director)
        event = create_event(self.director, pk=12, title="Rencontres", capacity=120)
        venue = Venue.objects.create(
            name="Salle des Arts", type="Salle", address="Tunis", capacity=100, parking_capacity=12,
        )
        requirements = self.url("event_requirements")
        edit = self.url("event_requirements_edit", event.pk)
        self.assertRedirects(self.client.post(edit, {
            "event_id": 999, "name": "Nom ignoré", "attendees": 90, "minimum_surface": "100",
            "parking_spaces": 8, "needs_accessibility": "on", "venue": venue.pk,
        }), requirements)
        profile = EventRequirements.objects.get(program_event=event)
        self.assertEqual(profile.attendees, 90)
        self.assertEqual(profile.venue, venue)
        self.assertEqual(profile.name, event.title)
        self.assertTrue(profile.needs_accessibility)

        view = self.url("entity_detail", "venues", venue.pk)
        response = self.client.get(view, {"event_id": 12})
        self.assertContains(response, "Incompatible", status_code=200)
        self.assertEqual([criterion["status"] for criterion in response.context["criteria"]],
                         ["pass", "unknown", "pass", "fail"])

        allocation = self.url("entity_create", "resource-allocations")
        self.assertContains(self.client.get(allocation), "Rencontres (#12)")
        self.assertEqual(self.client.get(self.url("inventory")).status_code, 403)
        self.assertEqual(self.client.get(self.url("inventory_pdf")).status_code, 403)
        self.assertEqual(self.client.post(self.url("entity_update", "resources", self.resource.pk), {
            "quantity": 100, "unit_cost": "1.00",
        }).status_code, 403)
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.quantity, 4)

    def test_planning_chooses_available_periods_and_compares_cost(self):
        self.client.force_login(self.director)
        start = timezone.localtime().replace(second=0, microsecond=0) + timedelta(days=1)
        duration = timedelta(hours=2)
        premium = Resource.objects.create(
            name="Projecteur mobile", type=self.resource.type, quantity=4, unit_cost="50.00", location="Scène",
        )
        ResourceAllocation.objects.create(
            resource=self.resource, event_id=7, quantity=4, start_time=start, end_time=start + duration,
        )
        query = {
            "event_id": 7, "resource_type": self.resource.type, "quantity": 3,
            "start_time": start.isoformat(), "end_time": (start + duration).isoformat(),
        }
        planner = self.url("allocation_planning")
        fixed = self.client.get(planner, query)
        self.assertEqual([row["resource"].pk for row in fixed.context["options"]], [premium.pk])

        flexible = self.client.get(planner, {**query, "latest_start": (start + duration).isoformat()})
        self.assertNotContains(flexible, "Coût estimé")
        first = flexible.context["options"][0]
        self.assertEqual(first["resource"], self.resource)
        self.assertEqual(first["start"], start + duration)
        self.assertEqual(first["end"] - first["start"], duration)
        self.assertEqual(self.client.get(first["url"]).context["form"]["event_id"].value(), "7")

    def test_usage_and_status_keep_inventory_consistent(self):
        now = timezone.localtime().replace(second=0, microsecond=0)
        start, end = now - timedelta(hours=1), now + timedelta(hours=1)
        allocation = ResourceAllocation.objects.create(
            resource=self.resource, program_event=self.event, event_id=7, quantity=4, start_time=start, end_time=end,
        )
        data = {
            "event_id": 7, "resource": self.resource.pk, "quantity": 4,
            "start_time": start.isoformat(), "end_time": end.isoformat(),
        }
        self.client.force_login(self.director)
        update = self.url("entity_update", "resource-allocations", allocation.pk)
        excessive = self.client.post(update, {**data, "used_quantity": 5})
        self.assertTrue(excessive.context["form"].has_error("used_quantity"))
        self.assertRedirects(
            self.client.post(update, {**data, "used_quantity": 2}),
            self.url("entity_detail", "resource-allocations", allocation.pk),
        )
        allocation.refresh_from_db()
        self.assertEqual(allocation.used_quantity, 2)

        self.client.force_login(self.admin)
        response = self.client.post(self.url("entity_update", "resources", self.resource.pk), {
            "name": self.resource.name, "type": self.resource.type, "quantity": 4,
            "unit_cost": "25.00", "location": self.resource.location, "status": Resource.Status.MAINTENANCE,
        })
        self.assertTrue(response.context["form"].has_error("status"))

    def test_admin_inventory_detects_low_stock_and_forecasts_from_usage(self):
        now = timezone.now()
        monday = week_start(now)
        self.resource.low_stock_threshold = 5
        self.resource.save()
        for index in range(8):
            start = monday - (8 - index) * WEEK + timedelta(hours=10)
            ResourceAllocation.objects.create(
                resource=self.resource, event_id=7, quantity=10, used_quantity=index + 1,
                start_time=start, end_time=start + timedelta(hours=2),
            )

        self.client.force_login(self.admin)
        response = self.client.get(self.url("inventory"))
        self.assertContains(response, "Risque de rupture")
        row = response.context["rows"][0]
        self.assertTrue(row["low"])
        self.assertEqual(row["used"], 36)
        self.assertEqual(row["model"]["method"], "Régression linéaire")
        self.assertEqual(row["periods"][0]["estimated"], 9)
        self.assertEqual(row["periods"][0]["shortage"], 5)

        export = self.client.get(self.url("inventory_pdf"))
        self.assertEqual(export["Content-Type"], "application/pdf")
        self.assertIn("inventaire-fannflow.pdf", export["Content-Disposition"])
        self.assertTrue(b"".join(export.streaming_content).startswith(b"%PDF-"))

    def test_foreign_allocations_are_hidden_and_forbidden_to_director(self):
        other = create_user("other-director", director=True)
        foreign = create_event(other, title="Événement tiers")
        start = timezone.now() + timedelta(days=3)
        end = start + timedelta(hours=1)
        allocation = ResourceAllocation.objects.create(
            resource=self.resource, program_event=foreign, event_id=foreign.pk, quantity=1,
            start_time=start, end_time=end,
        )
        self.client.force_login(self.director)
        slug = "resource-allocations"
        listing = self.url("entity_list", slug)
        self.assertNotContains(self.client.get(listing), foreign.title)
        self.assertNotContains(self.client.get(self.url("entity_create", slug)), foreign.title)
        self.assertEqual(self.client.get(self.url("entity_detail", slug, allocation.pk)).status_code, 403)
        endpoints = (
            self.url("entity_update", slug, allocation.pk),
            self.url("entity_delete", slug, allocation.pk),
            self.url("event_requirements_edit", foreign.pk),
        )
        for url in endpoints:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertEqual(self.client.get(self.url("allocation_planning"), {"event_id": foreign.pk}).status_code, 403)
        data = {
            "resource": self.resource.pk, "quantity": 1, "event_id": foreign.pk,
            "start_time": start.isoformat(), "end_time": end.isoformat(),
        }
        self.assertEqual(self.client.post(self.url("entity_create", slug), data).status_code, 403)
        self.assertEqual(ResourceAllocation.objects.count(), 1)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(listing), foreign.title)

    def test_event_deleted_from_program_leaves_allocation_editable_by_admin(self):
        self.client.force_login(self.admin)
        start = timezone.now() + timedelta(days=1)
        slug = "resource-allocations"
        data = {
            "resource": self.resource.pk, "quantity": 1, "event_id": self.event.pk,
            "start_time": start.isoformat(), "end_time": (start + timedelta(hours=1)).isoformat(),
        }
        self.assertEqual(self.client.post(self.url("entity_create", slug), data).status_code, 302)
        allocation = ResourceAllocation.objects.get()
        self.assertEqual(allocation.program_event_id, self.event.pk)

        event_id = self.event.pk
        self.event.delete()
        allocation.refresh_from_db()
        self.assertIsNone(allocation.program_event_id)
        self.assertEqual(allocation.event_id, event_id)
        update = self.url("entity_update", slug, allocation.pk)
        self.assertContains(self.client.get(update), "Référence historique")
        self.assertEqual(self.client.post(update, {**data, "event_id": 0, "quantity": 2}).status_code, 302)
        allocation.refresh_from_db()
        self.assertEqual(allocation.event_id, event_id)
        self.assertEqual(allocation.quantity, 2)

    def test_non_operations_roles_have_no_navigation_or_protected_endpoints(self):
        from django.contrib.auth.models import Group

        participant = create_user("participant-planning")
        team_member = create_user("team-member", organizer=True)
        communications = create_user("communications")
        communications.groups.add(Group.objects.create(name="Responsable Communication"))
        module = self.url("home")
        for person in (participant, team_member, communications):
            with self.subTest(person=person.pk):
                self.client.force_login(person)
                self.assertNotContains(self.client.get(reverse("core:home")), f'href="{module}"')
                self.assertEqual(self.client.get(module).status_code, 403)
                self.assertEqual(self.client.get(self.url("inventory_pdf")).status_code, 403)
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("core:home")), f'href="{module}"')
        self.assertRedirects(
            self.client.get(module), f"{reverse('users_teams:login')}?next={module}", fetch_redirect_response=False,
        )
